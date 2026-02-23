"""
controller_engine.py
Main inference engine for ATC decision-making
"""
import torch
import torch.nn as nn
import numpy as np
from typing import Dict, List, Optional, Tuple
from pathlib import Path
import json

from feature_builder import FeatureBuilder
from runway_manager import RunwayManager, Operation
from safety_validator import SafetyValidator
from state_tracker import StateTracker
from runtime_logger import RuntimeLogger


class ControllerNN(nn.Module):
    """Neural network model for runway prediction."""
    def __init__(self, in_dim: int, out_dim: int):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(in_dim, 64), nn.ReLU(),
            nn.Linear(64, 32), nn.ReLU(),
            nn.Linear(32, out_dim)
        )
    
    def forward(self, x):
        return self.net(x)


class ControllerEngine:
    """Main ATC control engine."""
    
    def __init__(
        self,
        models_dir: str = "models",
        logs_dir: str = "logs",
        debug: bool = False,
        mode: str = "simulation"  # 'simulation' or 'assistant'
    ):
        """Initialize the control engine."""
        self.models_dir = Path(models_dir)
        self.logs_dir = Path(logs_dir)
        self.debug = debug
        self.mode = mode  # simulation or assistant
        
        # Load configuration
        config_path = self.models_dir / "feature_config.json"
        if not config_path.exists():
            raise FileNotFoundError(f"Feature config not found: {config_path}")
        
        with open(config_path, 'r') as f:
            self.config = json.load(f)
        
        # Validate feature order if it exists
        feature_order_path = self.models_dir / "feature_order.json"
        if feature_order_path.exists():
            with open(feature_order_path, 'r') as f:
                feature_order_config = json.load(f)
            expected_features = feature_order_config.get('feature_cols', [])
            actual_features = self.config.get('feature_cols', [])
            if expected_features and actual_features != expected_features:
                raise ValueError(
                    f"Feature order mismatch!\n"
                    f"Expected: {expected_features}\n"
                    f"Actual: {actual_features}\n"
                    "Runtime MUST use exact feature order from training."
                )
            if self.debug:
                print(f"[OK] Feature order validated: {len(actual_features)} features in correct order")
        
        # Initialize components
        self.feature_builder = FeatureBuilder(str(config_path))
        self.runway_manager = RunwayManager()
        self.safety_validator = SafetyValidator()
        self.state_tracker = StateTracker()
        self.logger = RuntimeLogger(output_dir=str(self.logs_dir), debug=debug)
        
        # Load model
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.model = self._load_model()
        self.model.eval()
        
        # Initialize runways
        self.runway_manager.initialize_runways(self.config['runway_ids'])
        
        # Confidence threshold
        self.base_confidence_threshold = self.config['confidence_threshold']
        
        if self.debug:
            print(f"[OK] ControllerEngine initialized (mode={mode}, device={self.device})")
            print(f"[OK] Model loaded with {self.config['num_runways']} runways")
    
    def _load_model(self) -> ControllerNN:
        """Load the trained model."""
        model_path = self.models_dir / "phx_local_controller.pt"
        if not model_path.exists():
            raise FileNotFoundError(f"Model not found: {model_path}")
        
        num_features = len(self.config['feature_cols'])
        num_runways = self.config['num_runways']
        
        model = ControllerNN(num_features, num_runways).to(self.device)
        state_dict = torch.load(model_path, map_location=self.device)
        
        # Handle both "net.X.Y" and "X.Y" format state dicts
        if all(k.startswith('net.') for k in state_dict.keys()):
            # Already in correct format
            model.load_state_dict(state_dict)
        else:
            # Need to add "net." prefix
            new_state_dict = {f'net.{k}': v for k, v in state_dict.items()}
            model.load_state_dict(new_state_dict)
        
        return model
    
    def process_tick(
        self,
        timestamp: float,
        aircraft_list: List[Dict],
        weather: Optional[Dict] = None,
        runway_info: Optional[Dict] = None
    ) -> Dict:
        """
        Process one second of simulation.
        
        Args:
            timestamp: Current simulation time (Unix seconds)
            aircraft_list: List of aircraft state dicts
            weather: Optional weather dict
            runway_info: Optional runway metadata
        
        Returns:
            Structured decision dict
        """
        decisions = []
        runway_states = self.runway_manager.get_all_runway_states(timestamp)
        safety_alerts = []
        system_flags = {'degraded_mode': False}
        
        # Update runway occupancy
        self.runway_manager.clear_old_occupancy(timestamp)
        
        # Process each aircraft
        for ac_data in aircraft_list:
            ac_id = ac_data.get('aircraft_id', ac_data.get('id', 'UNKNOWN'))
            
            # Build features
            feature_vector, degradation_info = self.feature_builder.build_feature_vector(
                ac_id, ac_data, weather, runway_info
            )
            
            if feature_vector is None:
                # Critical data missing - cannot process
                self.state_tracker.update_or_create_aircraft(ac_id, ac_data)
                decision = {
                    'aircraft_id': ac_id,
                    'decision': 'HOLD',
                    'reason': 'Missing critical position data',
                    'confidence': 0.0,
                    'assigned_runway': None,
                    'operation': None
                }
                decisions.append(decision)
                continue
            
            # Log degradation
            if degradation_info['missing_features']:
                self.logger.log_missing_data(
                    timestamp, ac_id,
                    degradation_info['missing_features'],
                    degradation_info['imputed_features']
                )
            
            # Run inference
            with torch.no_grad():
                tensor = torch.tensor(feature_vector, dtype=torch.float32).unsqueeze(0).to(self.device)
                logits = self.model(tensor)
                probs = torch.softmax(logits, dim=1)
                confidence, predicted_idx = torch.max(probs, dim=1)
                
                confidence = confidence.item()
                predicted_runway = self.config['runway_ids'][predicted_idx.item()]
            
            # Log inference
            self.logger.log_inference(
                timestamp, ac_id,
                feature_vector.tolist(),
                logits[0].tolist(),
                confidence,
                predicted_runway,
                degradation_info['degradation_percent']
            )
            
            # Determine operation
            operation = ac_data.get('operation', 'landing')
            
            # Degrade confidence if feature quality poor
            effective_confidence = confidence
            effective_threshold = self.base_confidence_threshold
            
            if degradation_info['degradation_percent'] > 30:
                system_flags['degraded_mode'] = True
                effective_threshold *= 1.5  # Raise threshold
                self.logger.log_degraded_mode(
                    timestamp, ac_id,
                    f"Feature degradation: {degradation_info['degradation_percent']:.1f}%",
                    effective_threshold,
                    self.base_confidence_threshold
                )
            
            # Make decision
            if effective_confidence < effective_threshold:
                # Uncertain - HOLD
                decision = {
                    'aircraft_id': ac_id,
                    'decision': 'HOLD',
                    'reason': f'Low confidence: {confidence:.3f}',
                    'confidence': float(confidence),
                    'assigned_runway': None,
                    'operation': operation
                }
                self.logger.log_hold_decision(
                    timestamp, ac_id,
                    f'Confidence {confidence:.3f} < threshold {effective_threshold:.3f}',
                    confidence
                )
                decisions.append(decision)
                continue
            
            # Check safety
            other_aircraft = {
                a.aircraft_id: a.current_state
                for a in self.state_tracker.get_all_aircraft()
                if a.aircraft_id != ac_id
            }
            
            is_safe, violations = self.safety_validator.validate_runway_assignment(
                ac_id,
                predicted_runway,
                operation,
                ac_data,
                other_aircraft,
                self.config['runway_ids'],
                timestamp
            )
            
            if violations:
                for v in violations:
                    self.logger.log_safety_violation(
                        timestamp, ac_id, v.violation_type, v.severity, v.message, v.involved_aircraft
                    )
                    safety_alerts.append({
                        'aircraft_id': ac_id,
                        'violation_type': v.violation_type,
                        'severity': v.severity,
                        'message': v.message
                    })
                
                # Reject unsafe decision
                decision = {
                    'aircraft_id': ac_id,
                    'decision': 'HOLD',
                    'reason': violations[0].message,
                    'confidence': float(confidence),
                    'assigned_runway': None,
                    'operation': operation
                }
                decisions.append(decision)
                self.state_tracker.add_safety_flag(ac_id, violations[0].violation_type)
                continue
            
            # Verify runway can accept
            if operation == 'landing':
                can_clear, reason = self.runway_manager.can_clear_for_landing(
                    predicted_runway, ac_id, timestamp
                )
            else:
                can_clear, reason = self.runway_manager.can_clear_for_takeoff(
                    predicted_runway, ac_id, timestamp
                )
            
            if not can_clear:
                # Add to queue
                if operation == 'landing':
                    self.runway_manager.add_to_landing_queue(predicted_runway, ac_id)
                else:
                    self.runway_manager.add_to_takeoff_queue(predicted_runway, ac_id)
                
                decision = {
                    'aircraft_id': ac_id,
                    'decision': 'HOLD',
                    'reason': reason,
                    'confidence': float(confidence),
                    'assigned_runway': predicted_runway,
                    'operation': operation,
                    'queued': True
                }
                decisions.append(decision)
                continue
            
            # CLEARED!
            if operation == 'landing':
                self.runway_manager.mark_landing(predicted_runway, ac_id, timestamp, touched_down=True)
            else:
                self.runway_manager.mark_takeoff(predicted_runway, ac_id, timestamp, airborne=True)
            
            self.safety_validator.record_operation(predicted_runway, operation, timestamp, ac_id)
            
            decision = {
                'aircraft_id': ac_id,
                'decision': 'CLEARED',
                'operation': operation,
                'assigned_runway': predicted_runway,
                'confidence': float(confidence),
                'reason': f'Runway available, safety checks passed'
            }
            decisions.append(decision)
            
            self.logger.log_clearance(timestamp, ac_id, predicted_runway, operation)
            
            # Update state
            self.state_tracker.update_or_create_aircraft(ac_id, ac_data)
            self.state_tracker.set_assignment(ac_id, predicted_runway, operation, confidence, timestamp)
            self.state_tracker.issue_clearance(ac_id)
        
        # In assistant mode, don't mutate runway states
        if self.mode == 'assistant':
            # Rollback runway changes
            self.runway_manager.initialize_runways(self.config['runway_ids'])
        
        # Update runway snapshot
        runway_states = self.runway_manager.get_all_runway_states(timestamp)
        
        result = {
            'timestamp': int(timestamp),
            'datetime': self._timestamp_to_iso(timestamp),
            'mode': self.mode,
            'decisions': decisions,
            'runway_states': runway_states,
            'safety_alerts': safety_alerts,
            'system_flags': system_flags
        }
        
        return result
    
    def _timestamp_to_iso(self, timestamp: float) -> str:
        """Convert Unix timestamp to ISO string."""
        from datetime import datetime, timezone
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
    
    def reset(self):
        """Reset engine state while preserving model and config.
        
        This reinitializes:
        - runway_manager
        - state_tracker
        - safety_validator
        - logger
        
        Preserves:
        - loaded model
        - config
        - mode
        """
        # Reinitialize components
        self.runway_manager = RunwayManager()
        self.state_tracker = StateTracker()
        self.safety_validator = SafetyValidator()
        self.logger = RuntimeLogger(output_dir=str(self.logs_dir), debug=self.debug)
        
        # Reinitialize runways
        self.runway_manager.initialize_runways(self.config['runway_ids'])
        
        if self.debug:
            print(f"[OK] Engine reset complete")
    
    def save_logs(self):
        """Save all logged events."""
        self.logger.save_to_file()
        if self.debug:
            print(f"✓ Logs saved to {self.logs_dir}")
