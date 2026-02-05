"""
Fetch and process ADS-B Exchange traces for PHX operations in filtered CSVs.

Usage:
    venv\Scripts\activate
    pip install pandas requests geopy
    python scripts/fetch_trace_window.py
"""

import os
import pandas as pd
import aiohttp
import asyncio
import time as time_mod
from datetime import datetime, timezone
import numpy as np
from math import radians, sin, cos, sqrt, atan2

from requests import session

# Constants
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'operations_data')
TOWER_COORDS = (33.434167, -112.011667)
TRACE_URL_TEMPLATE = "https://samples.adsbexchange.com/traces/{yyyy}/{mm}/{dd}/{xx}/trace_full_{icao}.json"
MAX_RETRIES = 3
RADIUS_NM = 5
MAX_AGL_FT = 4000

REQUIRED_OPS_COLS = ['icao', 'flight', 'operation', 'time', 'elev']


# In-memory cache for ICAO+date traces
trace_cache = {}

async def fetch_trace_json_async(session, icao, dt, sem):
    icao_hex = icao.lower()
    xx = icao_hex[-2:]
    url = TRACE_URL_TEMPLATE.format(
        yyyy=dt.strftime('%Y'),
        mm=dt.strftime('%m'),
        dd=dt.strftime('%d'),
        xx=xx,
        icao=icao_hex
    )
    cache_key = (icao_hex, dt.strftime('%Y-%m-%d'))
    if cache_key in trace_cache:
        return trace_cache[cache_key]
    for attempt in range(1, MAX_RETRIES+1):
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with sem:
                async with session.get(url, timeout=timeout) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        trace_cache[cache_key] = data
                        return data
                    else:
                        print(f"Warning: HTTP {resp.status} for {url}")
        except Exception as e:
            print(f"Error fetching {url} (attempt {attempt}): {e}")
        await asyncio.sleep(2)
    print(f"Failed to fetch trace for {icao} on {dt.date()} after {MAX_RETRIES} attempts.")
    trace_cache[cache_key] = None
    return None


# Vectorized haversine for arrays
def haversine_np(lat1, lon1, lat2, lon2):
    # All args in degrees, returns distance in nautical miles
    R = 3440.065  # Earth radius in NM
    lat1 = np.radians(lat1)
    lon1 = np.radians(lon1)
    lat2 = np.radians(lat2)
    lon2 = np.radians(lon2)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat/2)**2 + np.cos(lat1)*np.cos(lat2)*np.sin(dlon/2)**2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1-a))
    return R * c


async def process_operation_row_async(row, session, sem):
    icao = row['icao']
    flight = row['flight']
    operation = row['operation'].lower()
    elev = float(row['elev']) if pd.notnull(row['elev']) else 0.0
    try:
        dt = pd.to_datetime(row['time'], utc=True)
        ops_ts = int(dt.timestamp())
    except Exception:
        return []
    trace = await fetch_trace_json_async(session, icao, dt, sem)
    if not trace or 'timestamp' not in trace or 'trace' not in trace:
        return []
    base_ts = int(trace['timestamp'])
    trace_rows = trace['trace']
    # Find index in trace closest to ops_ts
    t_abs_arr = np.array([base_ts + int(t[0]) for t in trace_rows])
    idx = np.argmin(np.abs(t_abs_arr - ops_ts)) if len(t_abs_arr) > 0 else None
    if idx is None:
        return []
    # Windowing
    if operation == 'arrival':
        indices = range(idx, -1, -1)  # backward
    else:
        indices = range(idx, len(trace_rows))  # forward
    # Pre-extract arrays for vectorized distance
    lats, lons, alts, gss, headings, legbreaks = [], [], [], [], [], []
    t_abs_list = []
    for i in indices:
        trow = trace_rows[i]
        try:
            t_abs = base_ts + int(trow[0])
            lat, lon = float(trow[1]), float(trow[2])
            alt = trow[3]
            if alt == "ground":
                alt_ft = 0.0
            else:
                alt_ft = float(alt)
            alt_agl = alt_ft - elev
            gs = float(trow[4]) if trow[4] is not None else None
            heading = float(trow[5]) if trow[5] is not None else None
            legbreak = (len(trow) > 6 and trow[6] == 1)
            t_abs_list.append(t_abs)
            lats.append(lat)
            lons.append(lon)
            alts.append(alt_agl)
            gss.append(gs)
            headings.append(heading)
            legbreaks.append(legbreak)
        except Exception:
            continue
    if not lats:
        return []
    lats = np.array(lats)
    lons = np.array(lons)
    alts = np.array(alts)
    gss = np.array(gss)
    headings = np.array(headings)
    t_abs_list = np.array(t_abs_list)
    dist_nm = haversine_np(lats, lons, TOWER_COORDS[0], TOWER_COORDS[1])
    # Filtering
    mask = (alts <= MAX_AGL_FT) & (dist_nm <= RADIUS_NM)
    # Stop at first out-of-window or legbreak
    filtered = []
    for i in range(len(mask)):
        if not mask[i] or legbreaks[i]:
            break
        filtered.append({
            "icao": icao,
            "flight": flight,
            "timestamp": int(t_abs_list[i]),
            "lat": float(lats[i]),
            "lon": float(lons[i]),
            "alt_agl": float(alts[i]),
            "gs": float(gss[i]) if gss[i] is not None else None,
            "heading": float(headings[i]) if headings[i] is not None else None,
            "distance_to_tower_nm": float(dist_nm[i])
        })
    return filtered


async def process_file_async(filepath, sem):
    df = pd.read_csv(filepath, dtype=str)
    df = df.dropna(subset=['icao', 'flight', 'operation', 'time', 'elev'])
    total_ops = len(df)
    total_states = 0
    async with aiohttp.ClientSession() as session:
        tasks = [process_operation_row_async(row, session, sem) for _, row in df.iterrows()]
        all_states = await asyncio.gather(*tasks)
        for states in all_states:
            total_states += len(states)
            # Here you could yield or process states as needed
            # For demonstration, we do nothing with them
    print(f"{os.path.basename(filepath)}: {total_ops} ops, {total_states} states included after filtering")


def main():
    loop = asyncio.get_event_loop()
    sem = asyncio.Semaphore(20)
    tasks = []
    for fname in os.listdir(DATA_DIR):
        if fname.endswith('.csv'):
            fpath = os.path.join(DATA_DIR, fname)
            tasks.append(process_file_async(fpath, sem))
    if tasks:
        loop.run_until_complete(asyncio.gather(*tasks))

if __name__ == "__main__":
    main()
