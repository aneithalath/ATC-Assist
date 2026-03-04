"""
test_utils.py
Common utilities and fixtures for all test suites
"""
import json
import time
import sys
import os
import requests
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import random
import numpy as np

# Add parent directories to path
TEST_DIR = Path(__file__).parent
ROOT_DIR = TEST_DIR.parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "scripts"))
sys.path.insert(0, str(ROOT_DIR / "api"))

from scripts.controller_engine import ControllerEngine


# ============================================================================
# Constants
# ============================================================================

API_BASE_URL = "http://localhost:8000"
TEST_TIMEOUT = 30  # seconds for API requests
RUNWAY_IDS = ["07L", "07R", "25L", "25R", "26", "8"]

# Test data directory
TEST_DATA_DIR = ROOT_DIR / "logs"


# ============================================================================
# API Helpers
# ============================================================================

class APIClient:
    """Wrapper for API calls."""
    
    def __init__(self, base_url: str = API_BASE_URL, timeout: float = TEST_TIMEOUT):
        self.base_url = base_url
        self.timeout = timeout
    
    def health_check(self) -> Dict:
        """Check API health."""
        resp = requests.get(f"{self.base_url}/health", timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()
    
    def process_tick(self, tick_data: Dict) -> Dict:
        """Process a tick via API."""
        resp = requests.post(
            f"{self.base_url}/tick",
            json=tick_data,
            timeout=self.timeout
        )
        resp.raise_for_status()
        return resp.json()
    
    def reset(self) -> Dict:
        """Reset engine via API."""
        resp = requests.post(f"{self.base_url}/reset", timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()
    
    def get_state(self) -> Dict:
        """Get current engine state."""
        resp = requests.get(f"{self.base_url}/state", timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()
    
    def get_runways(self) -> Dict:
        """Get runway states."""
        resp = requests.get(f"{self.base_url}/runways", timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()


# ============================================================================
# Engine Helpers
# ============================================================================

class CLIEngine:
    """Wrapper for direct CLI engine access."""
    
    def __init__(self, debug: bool = False):
        self.engine = ControllerEngine(
            models_dir=str(ROOT_DIR / "models"),
            logs_dir=str(ROOT_DIR / "logs"),
            debug=debug,
            mode="assistant"  # Use assistant mode to avoid state mutations
        )
    
    def process_tick(
        self,
        timestamp: float,
        aircraft_list: List[Dict],
        weather: Optional[Dict] = None,
        runway_info: Optional[Dict] = None
    ) -> Dict:
        """Process a tick via CLI engine."""
        return self.engine.process_tick(
            timestamp=timestamp,
            aircraft_list=aircraft_list,
            weather=weather,
            runway_info=runway_info
        )
    
    def reset(self):
        """Reset CLI engine."""
        self.engine.reset()


# ============================================================================
# Test Data Generators
# ============================================================================

def generate_test_weather(
    tmpf: float = 81.0,
    relh: float = 18.0,
    drct: float = 248.0,
    sknt: float = 0.5
) -> Dict:
    """Generate test weather data."""
    return {
        "tmpf": tmpf,
        "relh": relh,
        "drct": drct,
        "sknt": sknt,
        "wind_speed": sknt,
        "wind_direction": drct,
        "wind_along_runway": 0.35,
        "wind_cross_runway": -0.08
    }


def generate_simple_aircraft(
    aircraft_id: str,
    operation: str = "landing",
    timestamp: float = None,
    altitude_ft: int = 3000,
    ground_speed_knots: float = 150.0,
    heading_deg: float = 180.0,
    vertical_rate_fpm: int = -500
) -> Dict:
    """Generate a simple aircraft state dict."""
    if timestamp is None:
        timestamp = time.time()
    
    # Default Phoenix area coordinates
    lat = 33.4484 + random.uniform(-0.1, 0.1)
    lon = -112.0740 + random.uniform(-0.1, 0.1)
    
    return {
        "aircraft_id": aircraft_id,
        "lat": lat,
        "lon": lon,
        "altitude_ft": altitude_ft,
        "ground_speed_knots": ground_speed_knots,
        "heading_deg": heading_deg,
        "vertical_rate_fpm": vertical_rate_fpm,
        "aircraft_category": random.choice(["light_prop", "medium_jet", "heavy_jet"]),
        "operation": operation,
        "runway_alignment_error": random.uniform(0, 10) if operation == "landing" else 0.0,
        "field_elevation_ft": 1083,
        "timestamp": timestamp
    }


def generate_aircraft_list(
    count: int,
    timestamp: float = None,
    mix_operations: bool = True
) -> List[Dict]:
    """Generate multiple test aircraft."""
    if timestamp is None:
        timestamp = time.time()
    
    aircraft = []
    for i in range(count):
        op = random.choice(["landing", "takeoff"]) if mix_operations else "landing"
        aircraft.append(generate_simple_aircraft(
            aircraft_id=f"AC{i+1:04d}",
            operation=op,
            timestamp=timestamp
        ))
    return aircraft


def generate_tick_input(
    timestamp: float = None,
    aircraft_count: int = 3,
    weather: Dict = None,
    runway_info: Dict = None
) -> Dict:
    """Generate a complete tick input payload."""
    if timestamp is None:
        timestamp = time.time()
    
    if weather is None:
        weather = generate_test_weather()
    
    return {
        "timestamp": timestamp,
        "aircraft_list": generate_aircraft_list(aircraft_count, timestamp),
        "weather": weather,
        "runway_info": runway_info
    }


# ============================================================================
# Response Comparison
# ============================================================================

def normalize_response(response: Dict) -> Dict:
    """Normalize response for comparison (remove timestamps that vary)."""
    norm = response.copy()
    
    # These fields vary naturally and shouldn't be compared
    fields_to_remove = ["timestamp"]
    
    for field in fields_to_remove:
        norm.pop(field, None)
    
    return norm


def compare_responses(api_response: Dict, cli_response: Dict, tolerance: float = 0.01) -> Tuple[bool, List[str]]:
    """
    Compare API response with CLI response.
    
    Returns:
        (matches, differences) where differences is a list of differences found
    """
    differences = []
    
    # Compare decisions
    api_decisions = {d['aircraft_id']: d for d in api_response.get('decisions', [])}
    cli_decisions = {d['aircraft_id']: d for d in cli_response.get('decisions', [])}
    
    if set(api_decisions.keys()) != set(cli_decisions.keys()):
        differences.append(f"Decision count mismatch: API={len(api_decisions)}, CLI={len(cli_decisions)}")
    
    for ac_id in api_decisions.keys():
        if ac_id not in cli_decisions:
            differences.append(f"Aircraft {ac_id} missing in CLI decisions")
            continue
        
        api_dec = api_decisions[ac_id]
        cli_dec = cli_decisions[ac_id]
        
        # Compare decision fields
        if api_dec.get('decision') != cli_dec.get('decision'):
            differences.append(f"AC {ac_id}: decision mismatch: API={api_dec.get('decision')}, CLI={cli_dec.get('decision')}")
        
        if api_dec.get('assigned_runway') != cli_dec.get('assigned_runway'):
            differences.append(f"AC {ac_id}: runway mismatch: API={api_dec.get('assigned_runway')}, CLI={cli_dec.get('assigned_runway')}")
        
        api_conf = api_dec.get('confidence', 0.0)
        cli_conf = cli_dec.get('confidence', 0.0)
        if abs(api_conf - cli_conf) > tolerance:
            differences.append(f"AC {ac_id}: confidence mismatch: API={api_conf}, CLI={cli_conf}")
    
    # Compare system flags
    api_flags = api_response.get('system_flags', {})
    cli_flags = cli_response.get('system_flags', {})
    if api_flags.get('degraded_mode') != cli_flags.get('degraded_mode'):
        differences.append(f"degraded_mode mismatch: API={api_flags.get('degraded_mode')}, CLI={cli_flags.get('degraded_mode')}")
    
    matches = len(differences) == 0
    return matches, differences


# ============================================================================
# State Verification
# ============================================================================

def verify_runway_occupancy(
    runways: List[Dict],
    expected_occupied: int = None
) -> Tuple[bool, str]:
    """Verify runway occupancy invariants."""
    occupied = sum(1 for r in runways if r.get('occupied'))
    
    if expected_occupied is not None and occupied != expected_occupied:
        return False, f"Expected {expected_occupied} occupied runways, got {occupied}"
    
    # Check for valid states
    for r in runways:
        if r.get('occupied') and r.get('occupancy_remaining_sec', 0) < 0:
            return False, f"Runway {r['runway_id']} occupied with negative remaining time"
    
    return True, f"OK ({occupied} occupied)"


def verify_queue_integrity(
    runway_states: List[Dict]
) -> Tuple[bool, str]:
    """Verify queue integrity."""
    all_aircraft_in_queues = set()
    
    for runway in runway_states:
        landing_queue = runway.get('landing_queue', [])
        takeoff_queue = runway.get('takeoff_queue', [])
        
        # Check for duplicates within runway
        if len(landing_queue) != len(set(landing_queue)):
            return False, f"Runway {runway['runway_id']}: duplicate aircraft in landing queue"
        
        if len(takeoff_queue) != len(set(takeoff_queue)):
            return False, f"Runway {runway['runway_id']}: duplicate aircraft in takeoff queue"
        
        # Track all aircraft
        all_aircraft_in_queues.update(landing_queue)
        all_aircraft_in_queues.update(takeoff_queue)
    
    # Check for cross-runway duplicates (aircraft should not be in multiple queues)
    aircraft_seen = {}
    for runway in runway_states:
        for ac in runway.get('landing_queue', []):
            if ac in aircraft_seen:
                return False, f"Aircraft {ac} appears in multiple runway queues"
            aircraft_seen[ac] = runway['runway_id']
        for ac in runway.get('takeoff_queue', []):
            if ac in aircraft_seen:
                return False, f"Aircraft {ac} appears in multiple runway queues"
            aircraft_seen[ac] = runway['runway_id']
    
    return True, f"OK (queues valid)"


# ============================================================================
# Assertion Helpers
# ============================================================================

def assert_api_healthy():
    """Assert API is healthy and accessible."""
    client = APIClient()
    try:
        health = client.health_check()
        assert health.get('status') == 'healthy', "API not healthy"
        return True
    except Exception as e:
        raise AssertionError(f"API health check failed: {e}")


def assert_decision_valid(decision: Dict, valid_runways: List[str] = RUNWAY_IDS):
    """Assert a decision is structurally valid."""
    assert 'aircraft_id' in decision, "Missing aircraft_id"
    assert 'decision' in decision, "Missing decision"
    assert decision['decision'] in ['CLEARED', 'HOLD'], f"Invalid decision: {decision['decision']}"
    
    if decision['decision'] == 'CLEARED':
        assert 'assigned_runway' in decision, "CLEARED missing assigned_runway"
        assert decision['assigned_runway'] in valid_runways, f"Invalid runway: {decision['assigned_runway']}"
        assert 'operation' in decision, "CLEARED missing operation"


def assert_response_valid(response: Dict):
    """Assert API response is structurally valid."""
    assert 'timestamp' in response, "Missing timestamp"
    assert 'decisions' in response, "Missing decisions"
    assert isinstance(response['decisions'], list), "Decisions not a list"
    assert 'runway_states' in response, "Missing runway_states"
    assert isinstance(response['runway_states'], list), "runway_states not a list"
    
    for decision in response['decisions']:
        assert_decision_valid(decision)
