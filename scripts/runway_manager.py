"""
runway_manager.py
Manages runway occupancy, queues, and locking
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import Enum
from datetime import datetime, timezone, timedelta


class Operation(Enum):
    """Runway operation types."""
    LANDING = "landing"
    TAKEOFF = "takeoff"


@dataclass
class RunwayState:
    """Current state of a single runway."""
    runway_id: str
    current_operation: Optional[Operation] = None
    occupied_until: Optional[float] = None  # Unix timestamp
    landing_queue: List[str] = field(default_factory=list)  # Aircraft IDs
    takeoff_queue: List[str] = field(default_factory=list)
    locked: bool = True  # Locked by default
    emergency_override: bool = False
    
    def is_occupied(self, current_time: float) -> bool:
        """Check if runway is currently occupied."""
        if self.occupied_until is None:
            return False
        return current_time < self.occupied_until
    
    def get_occupancy_remaining_sec(self, current_time: float) -> float:
        """Seconds remaining in occupancy."""
        if not self.is_occupied(current_time):
            return 0.0
        return self.occupied_until - current_time


@dataclass
class RunwayManager:
    """Manages all runways at the airport."""
    runways: Dict[str, RunwayState] = field(default_factory=dict)
    rollout_time_sec: int = 50  # Landing rollout duration
    separation_time_sec: int = 60  # Minimum time between operations
    
    def initialize_runways(self, runway_ids: List[str]):
        """Initialize runway states and unlock all runways for testing."""
        for rid in runway_ids:
            self.runways[rid] = RunwayState(runway_id=rid, locked=False)
    
    def get_runway(self, runway_id: str) -> Optional[RunwayState]:
        """Get runway state."""
        return self.runways.get(runway_id)
    
    def can_clear_for_landing(
        self,
        runway_id: str,
        aircraft_id: str,
        current_time: float,
        next_landing_time: float = 0
    ) -> Tuple[bool, str]:
        """
        Check if runway can accept landing clearance.
        
        Returns:
            (can_clear, reason)
        """
        rwy = self.get_runway(runway_id)
        if not rwy:
            return False, "Runway does not exist"
        
        if rwy.locked and not rwy.emergency_override:
            return False, "Runway locked"
        
        if rwy.is_occupied(current_time):
            return False, f"Runway occupied for {rwy.get_occupancy_remaining_sec(current_time):.1f}s more"
        
        # Check if operation type is compatible
        if rwy.current_operation == Operation.TAKEOFF:
            # Wait for separation
            if rwy.occupied_until and current_time < rwy.occupied_until + self.separation_time_sec:
                return False, "Insufficient separation from previous takeoff"
        
        return True, "Cleared to land"
    
    def can_clear_for_takeoff(
        self,
        runway_id: str,
        aircraft_id: str,
        current_time: float
    ) -> Tuple[bool, str]:
        """Check if runway can accept takeoff clearance."""
        rwy = self.get_runway(runway_id)
        if not rwy:
            return False, "Runway does not exist"
        
        if rwy.locked and not rwy.emergency_override:
            return False, "Runway locked"
        
        if rwy.is_occupied(current_time):
            return False, f"Runway occupied for {rwy.get_occupancy_remaining_sec(current_time):.1f}s more"
        
        # Check if any landing arrivals are in queue
        if rwy.landing_queue:
            return False, "Landing aircraft in queue"
        
        return True, "Cleared for takeoff"
    
    def mark_landing(
        self,
        runway_id: str,
        aircraft_id: str,
        current_time: float,
        touched_down: bool = False
    ):
        """Mark aircraft as landing on runway."""
        rwy = self.get_runway(runway_id)
        if not rwy:
            return
        
        if touched_down:
            # Runway occupied for rollout time
            rwy.occupied_until = current_time + self.rollout_time_sec
            rwy.current_operation = Operation.LANDING
        
        # Remove from queue
        if aircraft_id in rwy.landing_queue:
            rwy.landing_queue.remove(aircraft_id)
    
    def mark_takeoff(
        self,
        runway_id: str,
        aircraft_id: str,
        current_time: float,
        airborne: bool = False
    ):
        """Mark aircraft as taking off from runway."""
        rwy = self.get_runway(runway_id)
        if not rwy:
            return
        
        if airborne:
            # Runway occupied for separation time
            rwy.occupied_until = current_time + self.separation_time_sec
            rwy.current_operation = Operation.TAKEOFF
        
        # Remove from queue
        if aircraft_id in rwy.takeoff_queue:
            rwy.takeoff_queue.remove(aircraft_id)
    
    def add_to_landing_queue(self, runway_id: str, aircraft_id: str):
        """Add aircraft to landing queue."""
        rwy = self.get_runway(runway_id)
        if rwy and aircraft_id not in rwy.landing_queue:
            rwy.landing_queue.append(aircraft_id)
    
    def add_to_takeoff_queue(self, runway_id: str, aircraft_id: str):
        """Add aircraft to takeoff queue."""
        rwy = self.get_runway(runway_id)
        if rwy and aircraft_id not in rwy.takeoff_queue:
            rwy.takeoff_queue.append(aircraft_id)
    
    def get_next_in_queue(self, runway_id: str) -> Optional[Tuple[str, str]]:
        """Get next aircraft in queue (prioritize landings)."""
        rwy = self.get_runway(runway_id)
        if not rwy:
            return None
        
        if rwy.landing_queue:
            return (rwy.landing_queue[0], "landing")
        elif rwy.takeoff_queue:
            return (rwy.takeoff_queue[0], "takeoff")
        
        return None
    
    def unlock_runway(self, runway_id: str):
        """Unlock runway for operations."""
        rwy = self.get_runway(runway_id)
        if rwy:
            rwy.locked = False
    
    def lock_runway(self, runway_id: str):
        """Lock runway (no operations allowed)."""
        rwy = self.get_runway(runway_id)
        if rwy:
            rwy.locked = True
    
    def set_emergency_override(self, runway_id: str, override: bool):
        """Enable/disable emergency override on locked runway."""
        rwy = self.get_runway(runway_id)
        if rwy:
            rwy.emergency_override = override
    
    def get_all_runway_states(self, current_time: float) -> Dict[str, dict]:
        """Get snapshot of all runway states."""
        states = {}
        for rid, rwy in self.runways.items():
            states[rid] = {
                'occupied': rwy.is_occupied(current_time),
                'occupancy_remaining_sec': rwy.get_occupancy_remaining_sec(current_time),
                'current_operation': rwy.current_operation.value if rwy.current_operation else None,
                'landing_queue_count': len(rwy.landing_queue),
                'takeoff_queue_count': len(rwy.takeoff_queue),
                'locked': rwy.locked,
                'emergency_override': rwy.emergency_override
            }
        return states
    
    def clear_old_occupancy(self, current_time: float):
        """Clear occupancy flags for runways that are no longer needed."""
        for rwy in self.runways.values():
            if rwy.occupied_until and current_time >= rwy.occupied_until:
                rwy.occupied_until = None
                # Only unlock if no more queued aircraft
                if not rwy.landing_queue and not rwy.takeoff_queue:
                    rwy.current_operation = None
