import json
import time
import math
import random
import os
from pathlib import Path

# Helper function for current timestamp
def current_ts():
    return time.time()

# Ensure logs directory exists
Path('logs').mkdir(exist_ok=True)
Path('logs/responses').mkdir(exist_ok=True)

# Aircraft generation helpers
PHX_LAT, PHX_LON = 33.4353, -112.0059
RUNWAY_HEADING = 260

CATEGORY_SPEEDS = {
    'light_prop': (80, 150),
    'medium_jet': (200, 250),
    'heavy_jet': (300, 450)
}

CATEGORY_ALTITUDE = {
    'landing': (500, 10000),
    'takeoff': (0, 35000)
}

CATEGORY_VERTICAL = {
    'landing': (-3000, -100),
    'takeoff': (1000, 3000)
}

AIRCRAFT_CATEGORIES = ['light_prop', 'medium_jet', 'heavy_jet']
OPERATIONS = ['landing', 'takeoff']

# Generate wind components
def wind_components(sknt, drct, runway_heading=RUNWAY_HEADING):
    rel_angle = math.radians(drct - runway_heading)
    along = sknt * math.cos(rel_angle)
    cross = sknt * math.sin(rel_angle)
    return along, cross

# Aircraft generator
def generate_aircraft(idx, operation, category, emergency=False, conflict=False, landing_queue=False, crosswind=False):
    lat = PHX_LAT + random.uniform(-0.1, 0.1)
    lon = PHX_LON + random.uniform(-0.1, 0.1)
    altitude = random.randint(*CATEGORY_ALTITUDE[operation])
    speed = random.uniform(*CATEGORY_SPEEDS[category])
    heading = random.uniform(0, 359)
    if operation == 'landing':
        vertical = random.randint(*CATEGORY_VERTICAL['landing'])
        if emergency:
            vertical = random.randint(-3000, -2000)
        alignment_error = random.uniform(0, 15)
    else:
        vertical = random.randint(*CATEGORY_VERTICAL['takeoff'])
        if emergency:
            vertical = random.randint(2000, 3000)
        alignment_error = 0.0
    if landing_queue:
        altitude = random.randint(500, 2000)
        speed = random.uniform(80, 120)
    aircraft_id = f"AC{idx:03d}"
    return {
        "aircraft_id": aircraft_id,
        "lat": lat,
        "lon": lon,
        "altitude_ft": altitude,
        "ground_speed_knots": speed,
        "heading_deg": heading,
        "vertical_rate_fpm": vertical,
        "aircraft_category": category,
        "operation": operation,
        "runway_alignment_error": alignment_error,
        "field_elevation_ft": 1083,
        "timestamp": current_ts()
    }

# Weather generator
def generate_weather(crosswind=False):
    tmpf = random.uniform(75, 110)
    relh = random.uniform(10, 60)
    drct = random.uniform(0, 359)
    sknt = random.uniform(0, 20)
    wind_speed = sknt
    wind_direction = drct
    along, cross = wind_components(sknt, drct)
    if crosswind:
        cross = random.uniform(15, 20)
        along = random.uniform(-5, 5)
    return {
        "tmpf": tmpf,
        "relh": relh,
        "drct": drct,
        "sknt": sknt,
        "wind_speed": wind_speed,
        "wind_direction": wind_direction,
        "wind_along_runway": along,
        "wind_cross_runway": cross
    }

# Scenario generators
def scenario_default():
    aircraft = [generate_aircraft(i+1, random.choice(OPERATIONS), random.choice(AIRCRAFT_CATEGORIES)) for i in range(random.randint(2,6))]
    weather = generate_weather()
    return {"timestamp": current_ts(), "aircraft_list": aircraft, "weather": weather, "runway_info": None}

def scenario_runway_conflict():
    # Two aircraft landing, same runway, close altitudes
    aircraft = [
        generate_aircraft(1, 'landing', 'medium_jet'),
        generate_aircraft(2, 'landing', 'heavy_jet', conflict=True)
    ]
    weather = generate_weather()
    return {"timestamp": current_ts(), "aircraft_list": aircraft, "weather": weather, "runway_info": None}

def scenario_landing_queue():
    aircraft = [generate_aircraft(i+1, 'landing', random.choice(AIRCRAFT_CATEGORIES), landing_queue=True) for i in range(4)]
    weather = generate_weather()
    return {"timestamp": current_ts(), "aircraft_list": aircraft, "weather": weather, "runway_info": None}

def scenario_emergency():
    aircraft = [
        generate_aircraft(1, 'landing', 'medium_jet', emergency=True),
        generate_aircraft(2, 'takeoff', 'heavy_jet')
    ]
    weather = generate_weather()
    return {"timestamp": current_ts(), "aircraft_list": aircraft, "weather": weather, "runway_info": None}

def scenario_high_crosswind():
    aircraft = [generate_aircraft(i+1, 'landing', random.choice(AIRCRAFT_CATEGORIES)) for i in range(3)]
    weather = generate_weather(crosswind=True)
    return {"timestamp": current_ts(), "aircraft_list": aircraft, "weather": weather, "runway_info": None}

def scenario_stress_test():
    aircraft = [generate_aircraft(i+1, random.choice(OPERATIONS), random.choice(AIRCRAFT_CATEGORIES)) for i in range(random.randint(15,20))]
    weather = generate_weather()
    return {"timestamp": current_ts(), "aircraft_list": aircraft, "weather": weather, "runway_info": None}

SCENARIOS = [
    scenario_default,
    scenario_runway_conflict,
    scenario_landing_queue,
    scenario_emergency,
    scenario_high_crosswind,
    scenario_stress_test
]

FILE_NAMES = [
    "tick_input_1.json",
    "tick_input_2.json",
    "tick_input_3.json",
    "tick_input_4.json",
    "tick_input_5.json"
]

# Generate and save test files
def generate_test_files():
    for i, scenario in enumerate(SCENARIOS[:5]):
        data = scenario()
        with open(f"logs/{FILE_NAMES[i]}", "w") as f:
            json.dump(data, f, indent=2)
    # Stress test
    data = scenario_stress_test()
    with open("logs/tick_input_5.json", "w") as f:
        json.dump(data, f, indent=2)

generate_test_files()

# Automated /tick tests
import requests

def run_tick_tests():
    responses_dir = Path('logs/responses')
    responses_dir.mkdir(exist_ok=True)
    summary = []
    for fname in FILE_NAMES:
        with open(f"logs/{fname}", "r") as f:
            payload = json.load(f)
        resp = requests.post(
            "http://localhost:8000/tick",
            headers={"Content-Type": "application/json"},
            json=payload
        )
        resp_json = resp.json()
        with open(responses_dir / fname.replace("tick_input", "response"), "w") as rf:
            json.dump(resp_json, rf, indent=2)
        aircraft_count = len(payload["aircraft_list"])
        decisions = resp_json.get("decisions", [])
        alerts = resp_json.get("alerts", [])
        print(f"Scenario {fname}: {aircraft_count} aircraft, {len(decisions)} decisions, {len(alerts)} safety alerts")
        summary.append({"file": fname, "aircraft": aircraft_count, "decisions": len(decisions), "alerts": len(alerts)})
    return summary

if __name__ == "__main__":
    run_tick_tests()
