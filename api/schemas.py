"""
schemas.py
Pydantic models for FastAPI request/response schema
"""
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field


class AircraftData(BaseModel):
    """Aircraft state data for tick request."""
    aircraft_id: str = Field(..., description="Aircraft identifier")
    lat: float = Field(..., description="Latitude")
    lon: float = Field(..., description="Longitude")
    altitude_ft: float = Field(..., description="Altitude in feet")
    ground_speed_knots: float = Field(..., description="Ground speed in knots")
    heading_deg: float = Field(..., description="Heading in degrees")
    vertical_rate_fpm: Optional[float] = Field(None, description="Vertical rate in feet per minute")
    aircraft_category: str = Field(..., description="Aircraft category (e.g., 'heavy_jet', 'medium_jet', 'light_prop')")
    operation: str = Field(default="landing", description="Operation type: 'landing' or 'takeoff'")
    runway_alignment_error: Optional[float] = Field(default=0.0, description="Runway alignment error in degrees")
    field_elevation_ft: Optional[float] = Field(default=1083, description="Field elevation in feet")
    distance_to_tower_nm: Optional[float] = Field(None, description="Distance to tower in nautical miles")
    timestamp: Optional[float] = Field(None, description="Timestamp (Unix seconds)")


class WeatherData(BaseModel):
    """Weather state data for tick request."""
    tmpf: Optional[float] = Field(None, description="Temperature in Fahrenheit")
    relh: Optional[float] = Field(None, description="Relative humidity percentage")
    drct: Optional[float] = Field(None, description="Wind direction in degrees")
    sknt: Optional[float] = Field(None, description="Wind speed in knots")
    wind_speed: Optional[float] = Field(None, description="Wind speed (knots)")
    wind_direction: Optional[float] = Field(None, description="Wind direction (degrees)")
    wind_along_runway: Optional[float] = Field(None, description="Wind component along runway")
    wind_cross_runway: Optional[float] = Field(None, description="Wind component cross runway")


class TickRequest(BaseModel):
    """Request for /tick endpoint."""
    timestamp: float = Field(..., description="Current simulation time (Unix seconds)")
    aircraft_list: List[AircraftData] = Field(..., description="List of aircraft states")
    weather: Optional[WeatherData] = Field(None, description="Current weather conditions")
    runway_info: Optional[Dict[str, Any]] = Field(None, description="Optional runway metadata")


class RunwayState(BaseModel):
    """State of a runway."""
    runway_id: str
    currently_in_use: bool
    recent_operations: List[Dict[str, Any]]
    landing_queue: List[str]
    takeoff_queue: List[str]


class Decision(BaseModel):
    """Decision for an aircraft."""
    aircraft_id: str
    decision: str
    operation: Optional[str] = None
    assigned_runway: Optional[str] = None
    confidence: float
    reason: str
    queued: Optional[bool] = None


class SafetyAlert(BaseModel):
    """Safety alert."""
    aircraft_id: str
    violation_type: str
    severity: str
    message: str


class SystemFlags(BaseModel):
    """System operational flags."""
    degraded_mode: bool


class TickResponse(BaseModel):
    """Response from /tick endpoint."""
    timestamp: int
    datetime: str
    mode: str
    decisions: List[Decision]
    runway_states: List[RunwayState]
    safety_alerts: List[SafetyAlert]
    system_flags: SystemFlags


class ResetResponse(BaseModel):
    """Response from /reset endpoint."""
    status: str = Field(..., description="Status message")
    message: str = Field(..., description="Detailed message")
    timestamp: float = Field(..., description="Reset timestamp")


class HealthResponse(BaseModel):
    """Health/status response."""
    status: str
    engine_mode: str
    message: str
    timestamp: float
