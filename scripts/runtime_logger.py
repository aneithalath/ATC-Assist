"""
runtime_logger.py
Structured logging for the ATC runtime engine
"""
import json
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from pathlib import Path


class RuntimeLogger:
    """Structured event logging."""
    
    def __init__(self, output_dir: str = "logs", debug: bool = False):
        """Initialize logger."""
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.debug = debug
        self.events: List[Dict[str, Any]] = []
    
    def log_event(
        self,
        event_type: str,
        timestamp: float,
        data: Dict[str, Any],
        severity: str = "INFO"
    ):
        """Log a structured event."""
        event = {
            'timestamp': timestamp,
            'datetime': datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat(),
            'event_type': event_type,
            'severity': severity,
            'data': data
        }
        self.events.append(event)
        
        if self.debug:
            self._print_event(event)
    
    def log_inference(
        self,
        timestamp: float,
        aircraft_id: str,
        features_vector: List[float],
        raw_logits: List[float],
        confidence: float,
        predicted_runway: str,
        feature_degradation: float = 0.0
    ):
        """Log inference details."""
        self.log_event(
            'inference',
            timestamp,
            {
                'aircraft_id': aircraft_id,
                'feature_vector_shape': len(features_vector),
                'raw_logits': [float(x) for x in raw_logits[:3]],  # Top 3
                'confidence': float(confidence),
                'predicted_runway': predicted_runway,
                'feature_degradation_percent': float(feature_degradation)
            },
            severity='DEBUG'
        )
    
    def log_decision(
        self,
        timestamp: float,
        aircraft_id: str,
        runway: str,
        operation: str,
        confidence: float,
        reason: str = ""
    ):
        """Log runway assignment decision."""
        self.log_event(
            'decision',
            timestamp,
            {
                'aircraft_id': aircraft_id,
                'assigned_runway': runway,
                'operation': operation,
                'confidence': float(confidence),
                'reason': reason
            },
            severity='INFO'
        )
    
    def log_clearance(
        self,
        timestamp: float,
        aircraft_id: str,
        runway: str,
        operation: str
    ):
        """Log when clearance is issued."""
        self.log_event(
            'clearance_issued',
            timestamp,
            {
                'aircraft_id': aircraft_id,
                'runway': runway,
                'operation': operation
            },
            severity='INFO'
        )
    
    def log_safety_violation(
        self,
        timestamp: float,
        aircraft_id: str,
        violation_type: str,
        severity: str,
        message: str,
        involved_aircraft: List[str]
    ):
        """Log safety violation."""
        self.log_event(
            'safety_violation',
            timestamp,
            {
                'aircraft_id': aircraft_id,
                'violation_type': violation_type,
                'message': message,
                'involved_aircraft': involved_aircraft
            },
            severity=severity
        )
    
    def log_missing_data(
        self,
        timestamp: float,
        aircraft_id: str,
        missing_fields: List[str],
        imputed_fields: List[str]
    ):
        """Log missing data and imputation."""
        self.log_event(
            'missing_data',
            timestamp,
            {
                'aircraft_id': aircraft_id,
                'missing_fields': missing_fields,
                'imputed_fields': imputed_fields,
                'missing_count': len(missing_fields)
            },
            severity='WARNING' if missing_fields else 'DEBUG'
        )
    
    def log_runway_state(
        self,
        timestamp: float,
        runway_states: Dict[str, Dict]
    ):
        """Log snapshot of all runway states."""
        self.log_event(
            'runway_states',
            timestamp,
            runway_states,
            severity='DEBUG'
        )
    
    def log_degraded_mode(
        self,
        timestamp: float,
        aircraft_id: str,
        reason: str,
        adjusted_threshold: float,
        original_threshold: float
    ):
        """Log entry into degraded mode."""
        self.log_event(
            'degraded_mode_active',
            timestamp,
            {
                'aircraft_id': aircraft_id,
                'reason': reason,
                'original_confidence_threshold': float(original_threshold),
                'adjusted_confidence_threshold': float(adjusted_threshold)
            },
            severity='WARNING'
        )
    
    def log_hold_decision(
        self,
        timestamp: float,
        aircraft_id: str,
        reason: str,
        confidence: float
    ):
        """Log HOLD decision."""
        self.log_event(
            'decision_hold',
            timestamp,
            {
                'aircraft_id': aircraft_id,
                'reason': reason,
                'confidence': float(confidence)
            },
            severity='INFO'
        )
    
    def save_to_file(self, filename: str = "atc_runtime.json"):
        """Save all logged events to JSON file."""
        output_path = self.output_dir / filename
        with open(output_path, 'w') as f:
            json.dump(self.events, f, indent=2, default=str)
        
        if self.debug:
            print(f"Logged {len(self.events)} events to {output_path}")
    
    def _print_event(self, event: Dict[str, Any]):
        """Print event to console (debug mode)."""
        print(f"[{event['severity']}] {event['event_type']}: {event['data']}")
