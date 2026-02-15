"""
state_tracker.py
Tracks aircraft and runway states during operation
"""
from dataclasses import dataclass, field
from typing import Dict, Optional, List
from datetime import datetime, timezone


@dataclass
class AircraftRecord:
    """Tracked state of a single aircraft."""
    aircraft_id: str
    current_state: Dict = field(default_factory=dict)
    assigned_runway: Optional[str] = None
    operation: Optional[str] = None  # 'landing' or 'takeoff'
    confidence: float = 0.0
    decision_time: Optional[float] = None
    last_update: Optional[float] = None
    degraded: bool = False
    safety_flags: List[str] = field(default_factory=list)
    clearance_issued: bool = False


class StateTracker:
    """Tracks all aircraft and runway states."""
    
    def __init__(self):
        """Initialize tracker."""
        self.aircraft: Dict[str, AircraftRecord] = {}
        self.runway_last_operation: Dict[str, Dict] = {}  # runway_id -> {timestamp, aircraft_id, operation}
    
    def update_or_create_aircraft(
        self,
        aircraft_id: str,
        state: Dict
    ) -> AircraftRecord:
        """Update or create aircraft record."""
        if aircraft_id not in self.aircraft:
            self.aircraft[aircraft_id] = AircraftRecord(aircraft_id=aircraft_id)
        
        rec = self.aircraft[aircraft_id]
        rec.current_state = state
        rec.last_update = state.get('timestamp')
        
        return rec
    
    def set_assignment(
        self,
        aircraft_id: str,
        runway: str,
        operation: str,
        confidence: float,
        decision_time: float
    ) -> AircraftRecord:
        """Record a runway assignment decision."""
        if aircraft_id not in self.aircraft:
            self.aircraft[aircraft_id] = AircraftRecord(aircraft_id=aircraft_id)
        
        rec = self.aircraft[aircraft_id]
        rec.assigned_runway = runway
        rec.operation = operation
        rec.confidence = confidence
        rec.decision_time = decision_time
        
        return rec
    
    def set_degraded(self, aircraft_id: str, degraded: bool, reason: str = ""):
        """Mark aircraft as degraded."""
        if aircraft_id in self.aircraft:
            self.aircraft[aircraft_id].degraded = degraded
            if degraded and reason:
                self.aircraft[aircraft_id].safety_flags.append(f"DEGRADED: {reason}")
    
    def add_safety_flag(self, aircraft_id: str, flag: str):
        """Add safety flag to aircraft."""
        if aircraft_id in self.aircraft:
            if flag not in self.aircraft[aircraft_id].safety_flags:
                self.aircraft[aircraft_id].safety_flags.append(flag)
    
    def issue_clearance(self, aircraft_id: str):
        """Mark that clearance was issued."""
        if aircraft_id in self.aircraft:
            self.aircraft[aircraft_id].clearance_issued = True
    
    def record_runway_operation(
        self,
        runway_id: str,
        aircraft_id: str,
        operation: str,
        timestamp: float
    ):
        """Record operation completed on runway."""
        self.runway_last_operation[runway_id] = {
            'timestamp': timestamp,
            'aircraft_id': aircraft_id,
            'operation': operation
        }
    
    def get_aircraft(self, aircraft_id: str) -> Optional[AircraftRecord]:
        """Get aircraft record."""
        return self.aircraft.get(aircraft_id)
    
    def get_all_aircraft(self) -> List[AircraftRecord]:
        """Get all aircraft records."""
        return list(self.aircraft.values())
    
    def get_aircraft_on_runway(self, runway_id: str) -> List[AircraftRecord]:
        """Get all aircraft assigned to runway."""
        return [a for a in self.aircraft.values() if a.assigned_runway == runway_id]
    
    def get_snapshot(self) -> Dict:
        """Get snapshot of all tracked states for logging."""
        return {
            'aircraft_count': len(self.aircraft),
            'degraded_aircraft': [a.aircraft_id for a in self.aircraft.values() if a.degraded],
            'assigned_aircraft': {
                a.aircraft_id: {
                    'runway': a.assigned_runway,
                    'operation': a.operation,
                    'confidence': a.confidence,
                    'cleared': a.clearance_issued
                }
                for a in self.aircraft.values()
                if a.assigned_runway
            },
            'safety_alerts': {
                a.aircraft_id: a.safety_flags
                for a in self.aircraft.values()
                if a.safety_flags
            }
        }
    
    def cleanup_old_aircraft(self, max_age_sec: float, current_time: float):
        """Remove old aircraft records."""
        to_remove = []
        for aid, rec in self.aircraft.items():
            if rec.last_update and (current_time - rec.last_update) > max_age_sec:
                to_remove.append(aid)
        
        for aid in to_remove:
            del self.aircraft[aid]
