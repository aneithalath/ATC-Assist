"""
safety_validator.py
Validates runway assignments and detects safety violations
"""
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import math


@dataclass
class SafetyViolation:
    """Represents a detected safety violation."""
    violation_type: str  # wake, time, distance, runway_overlap, etc.
    severity: str  # critical, warning
    message: str
    involved_aircraft: List[str]


class SafetyValidator:
    """Validates runway decisions against safety constraints."""
    
    # Wake turbulence separation rules (minutes)
    WAKE_SEPARATION_MIN = {
        ('H', 'L'): 8.0,  # Heavy-to-Light
        ('H', 'M'): 6.0,  # Heavy-to-Medium
        ('H', 'H'): 4.0,  # Heavy-to-Heavy
        ('M', 'L'): 5.0,  # Medium-to-Light
        ('M', 'M'): 3.0,  # Medium-to-Medium
        ('M', 'H'): 2.0,  # Medium-to-Heavy
        ('L', 'L'): 3.0,  # Light-to-Light
        ('L', 'M'): 3.0,  # Light-to-Medium
        ('L', 'H'): 3.0,  # Light-to-Heavy
    }
    
    # Minimum time separation (seconds) for same runway, same direction
    TIME_SEPARATION_SEC = 120  # 2 minutes
    
    # Minimum horizontal distance (nm) for approach
    HORIZONTAL_SEPARATION_NM = 1.0
    
    def __init__(self):
        """Initialize validator."""
        self.violations: List[SafetyViolation] = []
        self.last_landings: Dict[str, float] = {}  # runway -> timestamp
        self.last_takeoffs: Dict[str, float] = {}
        self.last_operations: Dict[str, Tuple[str, float]] = {}
    
    def validate_runway_assignment(
        self,
        aircraft_id: str,
        requested_runway: str,
        operation: str,  # 'landing' or 'takeoff'
        aircraft_state: Dict,
        other_aircraft: Dict[str, Dict],
        runway_list: List[str],
        current_time: float
    ) -> Tuple[bool, List[SafetyViolation]]:
        """
        Validate a proposed runway assignment.
        
        Args:
            aircraft_id: Requesting aircraft
            requested_runway: Requested runway ID
            operation: 'landing' or 'takeoff'
            aircraft_state: State dict of requesting aircraft
            other_aircraft: Dict of all other aircraft in airspace
            runway_list: List of valid runway IDs
            current_time: Current timestamp
        
        Returns:
            (is_valid, violations_list)
        """
        violations = []
        
        # Check runway exists
        if requested_runway not in runway_list:
            violations.append(SafetyViolation(
                violation_type='nonexistent_runway',
                severity='critical',
                message=f"Runway {requested_runway} does not exist",
                involved_aircraft=[aircraft_id]
            ))
            return False, violations
        
        # Check wake separation with other aircraft on same runway
        for other_id, other_state in other_aircraft.items():
            if other_id == aircraft_id:
                continue
            
            other_runway = other_state.get('assigned_runway')
            other_operation = other_state.get('operation', 'landing')
            
            if other_runway != requested_runway:
                continue
            
            # Same runway
            if operation == 'landing' and other_operation == 'landing':
                violation = self._check_wake_separation_landing(
                    aircraft_id, other_id, aircraft_state, other_state
                )
                if violation:
                    violations.append(violation)
            
            elif operation == 'takeoff' and other_operation == 'takeoff':
                violation = self._check_wake_separation_takeoff(
                    aircraft_id, other_id, aircraft_state, other_state
                )
                if violation:
                    violations.append(violation)
            
            elif operation == 'landing' and other_operation == 'takeoff':
                # Opposite direction - check for conflict
                violation = SafetyViolation(
                    violation_type='opposite_direction',
                    severity='critical',
                    message=f"Cannot land on {requested_runway} - {other_id} taking off",
                    involved_aircraft=[aircraft_id, other_id]
                )
                violations.append(violation)
        
        # Check with aircraft already landed/taken off (recent history)
        violation = self._check_time_separation(
            aircraft_id, requested_runway, operation, current_time
        )
        if violation:
            violations.append(violation)
        
        return len(violations) == 0, violations
    
    def _check_wake_separation_landing(
        self,
        aircraft_id: str,
        other_id: str,
        aircraft_state: Dict,
        other_state: Dict
    ) -> Optional[SafetyViolation]:
        """Check wake separation for landing aircraft."""
        my_alt = aircraft_state.get('altitude_ft', 0)
        other_alt = other_state.get('altitude_ft', 0)
        my_gs = aircraft_state.get('ground_speed_knots', 100)
        
        # If other aircraft is below us, no wake separation needed
        if other_alt < my_alt - 500:
            return None
        
        # Calculate time since other aircraft's landing
        # If recent enough, need wake separation
        other_est_time = other_state.get('estimated_landing_time', 0)
        if other_est_time == 0:
            # Assume recent
            my_cat = aircraft_state.get('aircraft_category', 'M')
            other_cat = other_state.get('aircraft_category', 'M')
            
            min_sep = self.WAKE_SEPARATION_MIN.get((other_cat, my_cat), 3.0)
            
            return SafetyViolation(
                violation_type='wake_separation',
                severity='warning',
                message=f"Insufficient wake separation: {other_id} ({other_cat}) -> {aircraft_id} ({my_cat}), need {min_sep}min",
                involved_aircraft=[aircraft_id, other_id]
            )
        
        return None
    
    def _check_wake_separation_takeoff(
        self,
        aircraft_id: str,
        other_id: str,
        aircraft_state: Dict,
        other_state: Dict
    ) -> Optional[SafetyViolation]:
        """Check wake separation for takeoff aircraft."""
        # Similar logic for takeoff
        my_cat = aircraft_state.get('aircraft_category', 'M')
        other_cat = other_state.get('aircraft_category', 'M')
        
        min_sep = self.WAKE_SEPARATION_MIN.get((other_cat, my_cat), 3.0)
        
        return SafetyViolation(
            violation_type='wake_separation',
            severity='warning',
            message=f"Insufficient wake separation: {other_id} ({other_cat}) -> {aircraft_id} ({my_cat}), need {min_sep}min",
            involved_aircraft=[aircraft_id, other_id]
        )
    
    def _check_time_separation(
        self,
        aircraft_id: str,
        runway_id: str,
        operation: str,
        current_time: float
    ) -> Optional[SafetyViolation]:

        if runway_id in self.last_operations:
            last_aircraft, last_time = self.last_operations[runway_id]

            # Ignore same aircraft
            if last_aircraft == aircraft_id:
                return None

            time_since = current_time - last_time

            if time_since < self.TIME_SEPARATION_SEC:
                return SafetyViolation(
                    violation_type='time_separation',
                    severity='warning',
                    message=f"Insufficient time separation on {runway_id}: {time_since:.0f}s < {self.TIME_SEPARATION_SEC}s",
                    involved_aircraft=[aircraft_id, last_aircraft]
                )

        return None

    
    def record_operation(
        self,
        runway_id: str,
        operation: str,
        current_time: float,
        aircraft_id: str
    ):
        """
        Record when an operation completed on a runway.

        Fixes applied:
        1. Validate inputs: runway_id must be str, operation in ('landing', 'takeoff'), aircraft_id not None
        2. Ignore None or invalid calls
        3. Prevent overwriting newer timestamps (ignore out-of-order calls)
        4. Optional: prevent duplicates in same tick
        """

        # Input validation
        if not runway_id or not isinstance(runway_id, str):
            return  # invalid runway
        if operation not in ('landing', 'takeoff'):
            return  # invalid operation
        if not aircraft_id:
            return  # invalid aircraft

        # Initialize last_operations dict if missing
        if not hasattr(self, 'last_operations') or self.last_operations is None:
            self.last_operations = {}

        # Prevent overwriting newer timestamps
        last_entry = self.last_operations.get(runway_id)
        if last_entry:
            _, last_time = last_entry
            if current_time <= last_time:
                # Out-of-order or duplicate call; ignore
                return

        # Record operation
        self.last_operations[runway_id] = (aircraft_id, current_time)
        if operation == 'landing':
            if not hasattr(self, 'last_landings') or self.last_landings is None:
                self.last_landings = {}
            self.last_landings[runway_id] = current_time
        else:
            if not hasattr(self, 'last_takeoffs') or self.last_takeoffs is None:
                self.last_takeoffs = {}
            self.last_takeoffs[runway_id] = current_time
    
    def check_collision_risk(
        self,
        aircraft_state: Dict,
        other_aircraft_list: List[Dict]
    ) -> Optional[SafetyViolation]:
        """Check for potential collision."""
        my_lat = aircraft_state.get('lat')
        my_lon = aircraft_state.get('lon')
        my_alt = aircraft_state.get('altitude_ft', 0)
        
        if not my_lat or not my_lon:
            return None
        
        for other in other_aircraft_list:
            other_lat = other.get('lat')
            other_lon = other.get('lon')
            other_alt = other.get('altitude_ft', 0)
            
            if not other_lat or not other_lon:
                continue
            
            # Check horizontal distance
            dist_nm = self._haversine_nm(my_lat, my_lon, other_lat, other_lon)
            
            # Check vertical distance
            alt_diff = abs(my_alt - other_alt)
            
            # Critical if less than 1 nm horizontal and 500 ft vertical
            if dist_nm < 1.0 and alt_diff < 500:
                return SafetyViolation(
                    violation_type='collision_risk',
                    severity='critical',
                    message=f"Collision risk with {other.get('id', 'unknown')}: {dist_nm:.2f}nm, {alt_diff:.0f}ft",
                    involved_aircraft=[aircraft_state.get('id', 'unknown'), other.get('id', 'unknown')]
                )
        
        return None
    
    def _haversine_nm(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance in nautical miles."""
        R = 3440.065  # Nautical miles
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
