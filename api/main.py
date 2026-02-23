"""
main.py
FastAPI wrapper for ATC Engine
"""
import sys
import time
import threading
import json
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# Add scripts and api directories to path
api_path = Path(__file__).parent
scripts_path = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(api_path))
sys.path.insert(0, str(scripts_path))

from scripts.controller_engine import ControllerEngine
from schemas import (
    TickRequest, TickResponse, ResetResponse, HealthResponse,
    Decision, RunwayState, SafetyAlert, SystemFlags
)

# ============================================================================
# Global Engine Instance
# ============================================================================

# Initialize engine once at startup
try:
    ENGINE = ControllerEngine(
        models_dir="models",
        logs_dir="logs",
        debug=False,
        mode="assistant"  # Use assistant mode to avoid mutating state
    )
    ENGINE_INITIALIZED = True
except Exception as e:
    ENGINE = None
    ENGINE_INITIALIZED = False
    print(f"ERROR: Failed to initialize ControllerEngine: {e}")

# Thread lock for state mutations
ENGINE_LOCK = threading.Lock()

# ============================================================================
# FastAPI App
# ============================================================================

app = FastAPI(
    title="ATC Engine API",
    description="FastAPI wrapper for Air Traffic Control decision engine",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Health Check
# ============================================================================

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Check API health status."""
    if not ENGINE_INITIALIZED or ENGINE is None:
        raise HTTPException(status_code=503, detail="Engine not initialized")
    
    return HealthResponse(
        status="healthy",
        engine_mode=ENGINE.mode,
        message="ATC Engine API is running",
        timestamp=time.time()
    )


# ============================================================================
# Tick Endpoint - Process one tick of simulation/assistance
# ============================================================================

@app.post("/tick", response_model=TickResponse)
async def process_tick(request: TickRequest):
    """Process one tick of the simulation.
    
    Thread-safe: Uses lock to protect engine state mutations.
    """
    if not ENGINE_INITIALIZED or ENGINE is None:
        raise HTTPException(status_code=503, detail="Engine not initialized")
    
    try:
        with ENGINE_LOCK:
            # Call engine with request data
            result = ENGINE.process_tick(
                timestamp=request.timestamp,
                aircraft_list=[ac.model_dump() for ac in request.aircraft_list],
                weather=request.weather.model_dump() if request.weather else None,
                runway_info=request.runway_info
            )
        
        # Parse runway states (dictionary -> list)
        runway_states = []
        for runway_id, state_dict in result.get('runway_states', {}).items():
            # Construct RunwayState with the runway_id
            rwy_state = {
                'runway_id': runway_id,
                'currently_in_use': state_dict.get('occupied', False),
                'recent_operations': [],  # Not populated by engine currently
                'landing_queue': [f'AC{i}' for i in range(state_dict.get('landing_queue_count', 0))],
                'takeoff_queue': [f'AC{i}' for i in range(state_dict.get('takeoff_queue_count', 0))]
            }
            runway_states.append(RunwayState(**rwy_state))
        
        # Parse decisions
        decisions = []
        for dec in result.get('decisions', []):
            decisions.append(Decision(**dec))
        
        # Parse safety alerts
        safety_alerts = []
        for sa in result.get('safety_alerts', []):
            alert_dict = {
                'aircraft_id': sa.get('aircraft_id'),
                'violation_type': sa.get('violation_type'),
                'severity': sa.get('severity', 'unknown'),
                'message': sa.get('message', '')
            }
            safety_alerts.append(SafetyAlert(**alert_dict))
        
        # Parse system flags
        system_flags = SystemFlags(**result.get('system_flags', {'degraded_mode': False}))
        
        response = TickResponse(
            timestamp=result['timestamp'],
            datetime=result['datetime'],
            mode=result['mode'],
            decisions=decisions,
            runway_states=runway_states,
            safety_alerts=safety_alerts,
            system_flags=system_flags
        )
        
        return response
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Error processing tick: {str(e)}"
        )


# ============================================================================
# Reset Endpoint - Reset engine state
# ============================================================================

@app.post("/reset", response_model=ResetResponse)
async def reset_engine():
    """Reset engine state while preserving model and configuration.
    
    Thread-safe: Uses lock to protect engine state mutations.
    """
    if not ENGINE_INITIALIZED or ENGINE is None:
        raise HTTPException(status_code=503, detail="Engine not initialized")
    
    try:
        with ENGINE_LOCK:
            before = len(ENGINE.state_tracker.get_all_aircraft())
            print(f"Aircraft before reset: {before}")

            ENGINE.reset()

            after = len(ENGINE.state_tracker.get_all_aircraft())
            print(f"Aircraft after reset: {after}")
        
        return ResetResponse(
            status="success",
            message="Engine state reset successfully",
            timestamp=time.time()
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error resetting engine: {str(e)}"
        )


# ============================================================================
# State Endpoint - Get current engine state
# ============================================================================

@app.get("/state")
async def get_state():
    """Get current engine state.
    
    Returns aircraft tracking state without mutations.
    """
    if not ENGINE_INITIALIZED or ENGINE is None:
        raise HTTPException(status_code=503, detail="Engine not initialized")
    
    try:
        with ENGINE_LOCK:
            # Get all tracked aircraft
            all_aircraft = ENGINE.state_tracker.get_all_aircraft()
            aircraft_states = []
            
            for ac in all_aircraft:
                aircraft_states.append({
                    'id': ac.aircraft_id,
                    'current_state': ac.current_state,
                    'assigned_runway': ac.assigned_runway,
                    'operation': ac.operation,
                    'confidence': ac.confidence,
                    'cleared': ac.clearance_issued,
                    'safety_flags': ac.safety_flags,
                    'last_updated': ac.last_update
                })
        
        return {
            'timestamp': time.time(),
            'aircraft_count': len(aircraft_states),
            'aircraft': aircraft_states,
            'engine_mode': ENGINE.mode
        }
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving state: {str(e)}"
        )


# ============================================================================
# Runways Endpoint - Get current runway states
# ============================================================================

@app.get("/runways")
async def get_runways():
    """Get current state of all runways."""
    if not ENGINE_INITIALIZED or ENGINE is None:
        raise HTTPException(status_code=503, detail="Engine not initialized")
    
    try:
        with ENGINE_LOCK:
            runway_states = ENGINE.runway_manager.get_all_runway_states(time.time())
        
        # Convert dict to list for API response
        runways_list = []
        for runway_id, state_dict in runway_states.items():
            runways_list.append({
                'runway_id': runway_id,
                'occupied': state_dict.get('occupied', False),
                'occupancy_remaining_sec': state_dict.get('occupancy_remaining_sec', 0),
                'current_operation': state_dict.get('current_operation'),
                'landing_queue_count': state_dict.get('landing_queue_count', 0),
                'takeoff_queue_count': state_dict.get('takeoff_queue_count', 0),
                'locked': state_dict.get('locked', False),
                'emergency_override': state_dict.get('emergency_override', False)
            })
        
        return {
            'timestamp': time.time(),
            'runway_count': len(runways_list),
            'runways': runways_list,
            'engine_mode': ENGINE.mode
        }
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving runway states: {str(e)}"
        )


# ============================================================================
# Error Handlers
# ============================================================================

@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Handle unexpected exceptions."""
    import traceback
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {str(exc)}"}
    )
