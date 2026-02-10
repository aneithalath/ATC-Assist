"""
trace_processor.py
Async trace processor for PHX Local Controller AI (Step 3)
"""
import aiohttp
import asyncio
import logging
import math
from typing import List, Dict, Any, Optional

TOWER_LAT = 33.435298
TOWER_LON = -112.005895
MAX_CONCURRENT_REQUESTS = 10
REQUEST_TIMEOUT = 10
MAX_RETRIES = 3

# Haversine distance in nautical miles
def haversine_nm(lat1, lon1, lat2, lon2):
    R = 3440.065  # Nautical miles
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

async def fetch_trace(session, icao, date, elev, logger):
    url = f"https://samples.adsbexchange.com/traces/{date.year}/{date.month:02}/{date.day:02}/{icao[-2:]}/trace_full_{icao}.json"
    for attempt in range(1, MAX_RETRIES+1):
        try:
            async with session.get(url, timeout=REQUEST_TIMEOUT) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    logger.warning(f"{icao}: HTTP {resp.status} on attempt {attempt}")
        except Exception as e:
            logger.warning(f"{icao}: {e} on attempt {attempt}")
        await asyncio.sleep(2 ** (attempt-1))
    logger.error(f"{icao}: Failed to fetch trace after {MAX_RETRIES} attempts")
    return None

async def process_traces(ops: List[Dict[str,Any]], logger) -> Dict[str,Any]:
    sem = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
    results = {}
    async with aiohttp.ClientSession() as session:
        async def process_op(op):
            async with sem:
                icao = op['icao']
                date = op['time']
                elev = float(op['elev']) if 'elev' in op and op['elev'] else 0
                operation = op.get('operation', '').lower()
                runway = op.get('runway', '')
                trace = await fetch_trace(session, icao, date, elev, logger)
                if trace is None:
                    logger.info(f"Skipped {icao}: missing trace")
                    return (icao, None)
                # Filtering: 5NM, <4000ft AGL, direction, stop at leg break
                base_ts = trace.get('timestamp', None)
                points = trace.get('trace', [])
                if not base_ts or not points:
                    logger.info(f"Skipped {icao}: empty trace")
                    return (icao, None)
                # Determine direction
                if operation == 'landing':
                    indices = range(len(points)-1, -1, -1)  # backward
                else:
                    indices = range(len(points))  # forward
                filtered = []
                last_valid = None
                for idx in indices:
                    p = points[idx]
                    # Unpack fields
                    t_rel, lat, lon, alt, gs, hdg, flags = p[:7]
                    # Leg break
                    if flags is not None and int(flags) & 2:
                        break
                    # Altitude handling
                    if alt == "ground":
                        agl = 0
                    elif alt is not None:
                        try:
                            agl = float(alt) - elev
                        except Exception:
                            agl = None
                    else:
                        agl = None
                    # Distance to tower
                    if lat is not None and lon is not None:
                        dist = haversine_nm(lat, lon, TOWER_LAT, TOWER_LON)
                    else:
                        dist = None
                    # Filter
                    if dist is not None and agl is not None:
                        if dist > 5 or agl > 4000:
                            continue
                    else:
                        continue
                    # Compute vertical rate
                    if last_valid is not None and agl is not None:
                        prev_t, prev_lat, prev_lon, prev_agl = last_valid
                        time_diff = t_rel - prev_t
                        if time_diff > 0 and agl is not None and prev_agl is not None:
                            vr = (agl - prev_agl) * 60 / time_diff
                        else:
                            vr = None
                    else:
                        vr = None
                    # Interpolation for large gaps
                    if last_valid is not None:
                        prev_t, prev_lat, prev_lon, prev_agl = last_valid
                        gap = abs(t_rel - prev_t)
                        if gap > 20:
                            logger.info(f"{icao}: Interpolating {gap}s gap at {t_rel}")
                            # Linear interpolate in time steps of 8s
                            steps = int(gap // 8)
                            for s in range(1, steps):
                                frac = s * 8 / gap
                                interp_lat = prev_lat + frac * (lat - prev_lat)
                                interp_lon = prev_lon + frac * (lon - prev_lon)
                                interp_agl = prev_agl + frac * (agl - prev_agl)
                                interp_vert_rate = (interp_agl - prev_agl) / (s*8) * 60 if interp_agl is not None and prev_agl is not None else None
                                filtered.append({
                                    'icao': icao,
                                    'runway': runway,
                                    'timestamp': base_ts + prev_t + s*8,
                                    'ac_type': op.get('ac_type', ''),
                                    'lat': interp_lat,
                                    'lon': interp_lon,
                                    'agl': interp_agl,
                                    'gs': gs,
                                    'hdg': hdg,
                                    'operation': operation,
                                    'vertical_rate_fpm': interp_vert_rate
                                })
                    filtered.append({
                        'icao': icao,
                        'runway': runway,
                        'operation': operation,
                        'ac_type': op.get('ac_type', ''),
                        'timestamp': base_ts + t_rel,
                        'lat': lat,
                        'lon': lon,
                        'agl': agl,
                        'gs': gs,
                        'hdg': hdg,
                        'vertical_rate_fpm': vr
                    })
                    last_valid = (t_rel, lat, lon, agl)
                if not filtered:
                    logger.info(f"Skipped {icao}: no valid points after filtering")
                    return (icao, None)
                return (icao, filtered)
        tasks = [process_op(op) for op in ops]
        for fut in asyncio.as_completed(tasks):
            icao, trace = await fut
            if trace:
                results[icao] = trace
    return results


# Step 4: Feature Construction
import pandas as pd
import datetime

def load_weather(weather_csv):
    df = pd.read_csv(weather_csv)
    df['valid'] = pd.to_datetime(df['valid'], errors='coerce')
    df = df[df['valid'].notna()]
    df = df.sort_values('valid')
    return df

def get_prior_weather(weather_df, ts):
    # Find most recent prior weather row
    if not isinstance(ts, pd.Timestamp):
        ts = pd.to_datetime(ts, errors='coerce')
    prior = weather_df[weather_df['valid'] <= ts]
    if prior.empty:
        return None
    return prior.iloc[-1].to_dict()

def extract_features(states, runway_dict, weather_df):
    features = []
    last_vr = None  # Track last known vertical rate
    next_known_idx = 0  # For lookahead interpolation

    # Precompute indices of known vertical rates
    known_vr_indices = [i for i, s in enumerate(states) if s.get('vertical_rate_fpm') is not None]

    for i, s in enumerate(states):
        # Vertical rate handling
        vr = s.get('vertical_rate_fpm')
        if vr is None:
            # Find next known vertical rate for interpolation
            next_known_idx = next((idx for idx in known_vr_indices if idx > i), None)
            if last_vr is not None and next_known_idx is not None:
                # Linear interpolate
                next_vr = states[next_known_idx]['vertical_rate_fpm']
                steps = next_known_idx - i + 1
                frac = 1 / steps
                vr = last_vr + frac * (next_vr - last_vr)
            elif last_vr is not None:
                vr = last_vr  # forward fill
            elif next_known_idx is not None:
                vr = states[next_known_idx]['vertical_rate_fpm']  # backfill
            else:
                vr = None  # preserve value as unknown
        else:
            last_vr = vr

        # Find runway info
        rw = next((r for r in runway_dict if r['id'] == str(s['runway'])), None)
        # Find weather
        w = get_prior_weather(weather_df, datetime.datetime.utcfromtimestamp(s['timestamp']))
        # Compute wind components
        wind_dir = float(w['drct']) if w and w.get('drct') not in [None, 'M'] else None
        wind_speed = float(w['sknt']) if w and w.get('sknt') not in [None, 'M'] else None
        rw_heading = float(rw['heading']) if rw else None
        if wind_dir is not None and rw_heading is not None:
            rel_wind = wind_dir - rw_heading
            wind_along = wind_speed * math.cos(math.radians(rel_wind)) if wind_speed is not None else None
            wind_cross = wind_speed * math.sin(math.radians(rel_wind)) if wind_speed is not None else None
        else:
            wind_along = wind_cross = None
        # Time-of-day encoding
        dt = datetime.datetime.utcfromtimestamp(s['timestamp'])
        tod = dt.hour + dt.minute/60 + dt.second/3600
        # Runway alignment error
        if rw_heading is not None and s.get('hdg') is not None:
            align_err = abs(float(s['hdg']) - rw_heading)
        else:
            align_err = None

        # Aircraft category (simple mapping)
        def classify_aircraft(icao_type: str) -> str:
            if not isinstance(icao_type, str):
                return "unknown"

            t = icao_type.upper().strip()

            # Heavies (widebody, long-haul)
            if t.startswith(("B74", "B77", "B78", "A33", "A34", "A35", "A38")):
                return "heavy_jet"

            # Large narrowbody jets
            if t.startswith(("B73", "A32", "A20", "A21")):
                return "medium_jet"

            # Regional jets
            if t.startswith(("CRJ", "E17", "E19", "E70", "E75")):
                return "regional_jet"

            # Turboprops
            if t.startswith(("DH", "AT", "Q4", "SF3", "PC")):
                return "turboprop"

            # Light GA props
            if t.startswith(("C1", "C2", "C3", "PA", "BE")):
                return "light_prop"

            return "unknown"


        ac_type = s.get('ac_type')

        if isinstance(ac_type, str):
            ac_cat = classify_aircraft(ac_type)
        else:
            ac_cat = "unknown"
        
        features.append({
            'icao': s['icao'],
            'runway': s['runway'],
            'operation': s.get('operation'),
            'timestamp': s['timestamp'],
            'distance_to_tower_nm': haversine_nm(s['lat'], s['lon'], TOWER_LAT, TOWER_LON),
            'altitude_agl_ft': s['agl'],
            'ground_speed_knots': s['gs'],
            'vertical_rate_fpm': vr, 
            'heading_deg': s['hdg'],
            'wind_along_runway': wind_along,
            'wind_cross_runway': wind_cross,
            'time_of_day': tod,
            'runway_alignment_error': align_err,
            'aircraft_category': ac_cat,
            'weather_tmpf': w['tmpf'] if w else None,
            'weather_relh': w['relh'] if w else None,
            'weather_drct': w['drct'] if w else None,
            'weather_sknt': w['sknt'] if w else None,
        })
    return features

def run_trace_processing(ops: List[Dict[str,Any]], logger, runway_dict=None, weather_csv=None) -> Dict[str,Any]:
    """Synchronous entry point for trace processing and feature construction."""
    traces = asyncio.run(process_traces(ops, logger))
    if runway_dict and weather_csv:
        weather_df = load_weather(weather_csv)
        for icao, states in traces.items():
            if states:
                traces[icao] = extract_features(states, runway_dict, weather_df)
    return traces
