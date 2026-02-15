"""
feature_builder.py
Constructs feature vectors for inference at runtime
"""
import json
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone
import math


class FeatureBuilder:
    """Loads feature configuration from training and builds runtime features."""
    
    def __init__(self, config_path: str):
        """Initialize with feature config from training."""
        with open(config_path, 'r') as f:
            self.config = json.load(f)
        
        self.feature_cols = self.config['feature_cols']
        self.medians = self.config['medians']
        self.allow_missing = set(self.config['allow_missing'])
        self.critical_columns = set(self.config['critical_columns'])
        self.label_map = self.config['label_map']
        self.confidence_threshold = self.config['confidence_threshold']
        self.runway_ids = self.config['runway_ids']
        
        # Track first occurrence of missing data per aircraft
        self.missing_alerts = {}
    
    def encode_aircraft_category(self, category: str) -> Dict[str, int]:
        """One-hot encode aircraft category for all supported types."""
        # Map input string to config field
        mapping = {
            'heavy_jet': 'ac_cat_heavy_jet',
            'medium_jet': 'ac_cat_medium_jet',
            'regional_jet': 'ac_cat_regional_jet',
            'turboprop': 'ac_cat_turboprop',
            'light_prop': 'ac_cat_light_prop',
            'unknown': 'ac_cat_unknown',
            # legacy codes for compatibility
            'H': 'ac_cat_heavy_jet',
            'M': 'ac_cat_medium_jet',
            'L': 'ac_cat_light_prop',
        }
        encoded = {col: 0 for col in self.feature_cols if col.startswith('ac_cat_')}
        col = mapping.get(category, 'ac_cat_unknown')
        if col in encoded:
            encoded[col] = 1
        return encoded
    
    def encode_operation(self, operation: str) -> Dict[str, int]:
        """One-hot encode operation type."""
        operations = ['landing', 'takeoff']
        encoded = {}
        for op in operations:
            col_name = f'op_{op}'
            if col_name in self.feature_cols:
                encoded[col_name] = 1 if operation == op else 0
        return encoded
    
    def build_feature_vector(
        self,
        aircraft_id: str,
        state: Dict,
        weather: Optional[Dict] = None,
        runway_info: Optional[Dict] = None
    ) -> Tuple[np.ndarray, Dict]:
        """
        Build normalized feature vector from aircraft state.
        
        Args:
            aircraft_id: Unique aircraft identifier
            state: Aircraft state dict with position, speed, etc.
            weather: Optional current weather dict
            runway_info: Optional runway metadata for alignment calculation
        
        Returns:
            (feature_vector, metadata_dict) where metadata tracks missing/degraded info
        """
        features = {}
        degradation_flags = {
            'missing_features': [],
            'imputed_features': [],
            'degraded': False,
            'degradation_percent': 0.0
        }
        
        # Basic required fields
        timestamp = state.get('timestamp')
        lat = state.get('lat')
        lon = state.get('lon')
        
        # Drop tick if missing critical position data
        if not all([timestamp, lat is not None, lon is not None]):
            degradation_flags['degraded'] = True
            missing_critical = []
            if not timestamp:
                missing_critical.append('timestamp')
            if lat is None:
                missing_critical.append('lat')
            if lon is None:
                missing_critical.append('lon')
            degradation_flags['missing_features'] = missing_critical
            return None, degradation_flags
        
        # Distance to tower
        if 'distance_to_tower_nm' in self.feature_cols:
            tower_lat, tower_lon = 33.435298, -112.005895
            dist = self._haversine_nm(lat, lon, tower_lat, tower_lon)
            features['distance_to_tower_nm'] = dist
        
        # Altitude AGL
        if 'altitude_agl_ft' in self.feature_cols:
            alt_msl = state.get('altitude_ft', 0)
            field_elev = state.get('field_elevation_ft', 1083)  # PHX elevation
            alt_agl = max(0, alt_msl - field_elev)
            features['altitude_agl_ft'] = alt_agl
        
        # Ground speed
        if 'ground_speed_knots' in self.feature_cols:
            gs = state.get('ground_speed_knots', 0)
            features['ground_speed_knots'] = max(0, gs)
        
        # Heading
        if 'heading_deg' in self.feature_cols:
            heading = state.get('heading_deg')
            if heading is not None:
                features['heading_deg'] = heading
            else:
                # Try to infer from position delta
                inferred = self._infer_heading_from_position(aircraft_id, lat, lon)
                if inferred is not None:
                    features['heading_deg'] = inferred
                    degradation_flags['imputed_features'].append('heading_deg')
                else:
                    features['heading_deg'] = 0.0
                    degradation_flags['missing_features'].append('heading_deg')
        
        # Wind components (requires runway info)
        wind_along = state.get('wind_along_runway', None)
        wind_cross = state.get('wind_cross_runway', None)
        
        if 'wind_along_runway' in self.feature_cols:
            if wind_along is not None:
                features['wind_along_runway'] = wind_along
            elif weather and 'wind_speed' in weather:
                # Compute from wind direction + runway heading
                runway_heading = runway_info.get('heading', 0) if runway_info else 0
                wind_dir = weather.get('wind_direction', 0)
                wind_speed = weather.get('wind_speed', 0)
                features['wind_along_runway'] = self._wind_component(wind_speed, wind_dir, runway_heading)
                degradation_flags['imputed_features'].append('wind_along_runway')
            else:
                features['wind_along_runway'] = 0.0
                degradation_flags['missing_features'].append('wind_along_runway')
        
        if 'wind_cross_runway' in self.feature_cols:
            if wind_cross is not None:
                features['wind_cross_runway'] = wind_cross
            elif weather and 'wind_speed' in weather:
                runway_heading = runway_info.get('heading', 0) if runway_info else 0
                wind_dir = weather.get('wind_direction', 0)
                wind_speed = weather.get('wind_speed', 0)
                features['wind_cross_runway'] = self._wind_component_cross(wind_speed, wind_dir, runway_heading)
                degradation_flags['imputed_features'].append('wind_cross_runway')
            else:
                features['wind_cross_runway'] = 0.0
                degradation_flags['missing_features'].append('wind_cross_runway')
        
        # Time of day (0-24)
        if 'time_of_day' in self.feature_cols:
            if isinstance(timestamp, (int, float)):
                dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            else:
                dt = timestamp if isinstance(timestamp, datetime) else datetime.now(timezone.utc)
            features['time_of_day'] = dt.hour + dt.minute / 60.0
        
        # Runway alignment error
        if 'runway_alignment_error' in self.feature_cols:
            rae = state.get('runway_alignment_error', 0)
            features['runway_alignment_error'] = rae if rae is not None else 0.0
        
        # Vertical rate
        if 'vertical_rate_fpm' in self.feature_cols:
            vr = state.get('vertical_rate_fpm')
            if vr is not None:
                features['vertical_rate_fpm'] = vr
            else:
                # Check for glitch: altitude increasing but vr=0
                prev_alt = getattr(self, f'_prev_alt_{aircraft_id}', None)
                if prev_alt and prev_alt > 1000:
                    vr = getattr(self, f'_prev_vr_{aircraft_id}', 0)
                    if vr is not None and vr != 0:
                        features['vertical_rate_fpm'] = vr
                        degradation_flags['imputed_features'].append('vertical_rate_fpm')
                    else:
                        features['vertical_rate_fpm'] = 0.0
                        degradation_flags['missing_features'].append('vertical_rate_fpm')
                else:
                    features['vertical_rate_fpm'] = 0.0
                    degradation_flags['missing_features'].append('vertical_rate_fpm')
        
        # Store for next tick
        setattr(self, f'_prev_alt_{aircraft_id}', state.get('altitude_ft', 0))
        setattr(self, f'_prev_vr_{aircraft_id}', state.get('vertical_rate_fpm'))
        
        # Weather features
        if weather:
            if 'weather_tmpf' in self.feature_cols:
                features['weather_tmpf'] = weather.get('tmpf', 70.0)
            if 'weather_relh' in self.feature_cols:
                features['weather_relh'] = weather.get('relh', 50.0)
            if 'weather_drct' in self.feature_cols:
                features['weather_drct'] = weather.get('drct', 0.0)
            if 'weather_sknt' in self.feature_cols:
                features['weather_sknt'] = weather.get('sknt', 0.0)
        else:
            # Weather missing - use calm defaults
            for col in ['weather_tmpf', 'weather_relh', 'weather_drct', 'weather_sknt']:
                if col in self.feature_cols:
                    features[col] = 70.0 if 'tmp' in col else (50.0 if 'relh' in col else 0.0)
        
        # One-hot encode aircraft category & operation
        ac_category = state.get('aircraft_category', 'M')
        features.update(self.encode_aircraft_category(ac_category))
        
        operation = state.get('operation', 'landing')
        features.update(self.encode_operation(operation))
        
        # Add missing indicators for allowed-missing columns
        for col in self.allow_missing:
            if col in self.feature_cols:
                miss_col = f"{col}_missing"
                if miss_col in self.feature_cols:
                    features[miss_col] = 1 if col in degradation_flags['missing_features'] else 0
        
        # Impute missing values
        for col in self.feature_cols:
            if col not in features or pd.isna(features[col]):
                if col in self.allow_missing:
                    features[col] = self.medians.get(col, 0.0)
                    if col not in degradation_flags['missing_features']:
                        degradation_flags['imputed_features'].append(col)
                else:
                    # Critical: should not be missing but fallback
                    features[col] = 0.0
                    degradation_flags['missing_features'].append(col)
        
        # Build ordered vector
        vector = np.array([features.get(col, 0.0) for col in self.feature_cols], dtype=np.float32)
        
        # Check for NaN
        if np.any(np.isnan(vector)):
            vector = np.nan_to_num(vector, nan=0.0, posinf=0.0, neginf=0.0)
            degradation_flags['degraded'] = True
        
        # Track degradation
        total_missing = len(degradation_flags['missing_features'])
        degradation_flags['degradation_percent'] = (total_missing / len(self.feature_cols)) * 100
        if degradation_flags['degradation_percent'] > 30:
            degradation_flags['degraded'] = True
        
        return vector, degradation_flags
    
    def _haversine_nm(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance in nautical miles."""
        R = 3440.065  # Nautical miles
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    def _infer_heading_from_position(self, aircraft_id: str, lat: float, lon: float) -> Optional[float]:
        """Infer heading from position change."""
        prev_key = f'_prev_pos_{aircraft_id}'
        if hasattr(self, prev_key):
            prev_lat, prev_lon = getattr(self, prev_key)
            if abs(lat - prev_lat) > 0.0001 or abs(lon - prev_lon) > 0.0001:
                dlat = lat - prev_lat
                dlon = lon - prev_lon
                heading = math.degrees(math.atan2(dlon, dlat)) % 360
                setattr(self, prev_key, (lat, lon))
                return heading
        setattr(self, prev_key, (lat, lon))
        return None
    
    def _wind_component(self, wind_speed: float, wind_dir: float, runway_heading: float) -> float:
        """Headwind component (positive = headwind)."""
        relative = (wind_dir - runway_heading) % 360
        return wind_speed * math.cos(math.radians(relative))
    
    def _wind_component_cross(self, wind_speed: float, wind_dir: float, runway_heading: float) -> float:
        """Crosswind component."""
        relative = (wind_dir - runway_heading) % 360
        return wind_speed * math.sin(math.radians(relative))
