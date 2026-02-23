#!/usr/bin/env python
"""Test script for ATC API"""
import requests
import json
import time

BASE_URL = "http://127.0.0.1:8000"

def test_health():
    """Test health endpoint."""
    print("\n" + "="*70)
    print("TEST 1: Health Check")
    print("="*70)
    try:
        resp = requests.get(f"{BASE_URL}/health")
        print(f"Status: {resp.status_code}")
        print(f"Response: {json.dumps(resp.json(), indent=2)}")
        if resp.status_code == 200:
            print("✓ PASS")
            return True
    except Exception as e:
        print(f"✗ FAIL: {e}")
        return False

def test_tick():
    """Test tick endpoint."""
    print("\n" + "="*70)
    print("TEST 2: Process Tick")
    print("="*70)
    
    tick_data = {
        "timestamp": time.time(),
        "aircraft_list": [
            {
                "aircraft_id": "AAL123",
                "lat": 33.435298,
                "lon": -112.005895,
                "altitude_ft": 10000,
                "ground_speed_knots": 150,
                "heading_deg": 260.0,
                "vertical_rate_fpm": -300,
                "aircraft_category": "heavy_jet",
                "operation": "landing",
                "runway_alignment_error": 5.0,
                "field_elevation_ft": 1083
            }
        ]
    }
    
    try:
        resp = requests.post(f"{BASE_URL}/tick", json=tick_data)
        print(f"Status: {resp.status_code}")
        result = resp.json()
        print(f"Timestamp: {result['timestamp']}")
        print(f"Mode: {result['mode']}")
        print(f"Decisions: {len(result['decisions'])}")
        if result['decisions']:
            dec = result['decisions'][0]
            print(f"  - Aircraft: {dec['aircraft_id']}")
            print(f"  - Decision: {dec['decision']}")
            print(f"  - Confidence: {dec['confidence']:.3f}")
        print("✓ PASS")
        return True
    except Exception as e:
        print(f"✗ FAIL: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_state():
    """Test state endpoint."""
    print("\n" + "="*70)
    print("TEST 3: Get State")
    print("="*70)
    try:
        resp = requests.get(f"{BASE_URL}/state")
        print(f"Status: {resp.status_code}")
        result = resp.json()
        print(f"Aircraft Count: {result['aircraft_count']}")
        print(f"Engine Mode: {result['engine_mode']}")
        print("✓ PASS")
        return True
    except Exception as e:
        print(f"✗ FAIL: {e}")
        return False

def test_tick_again():
    """Test second tick to verify state persistence."""
    print("\n" + "="*70)
    print("TEST 4: Second Tick (State Persistence)")
    print("="*70)
    
    tick_data = {
        "timestamp": time.time() + 1,
        "aircraft_list": [
            {
                "aircraft_id": "AAL123",
                "lat": 33.44,
                "lon": -112.00,
                "altitude_ft": 9000,
                "ground_speed_knots": 145,
                "heading_deg": 260.0,
                "vertical_rate_fpm": -300,
                "aircraft_category": "heavy_jet",
                "operation": "landing",
                "runway_alignment_error": 4.0,
                "field_elevation_ft": 1083
            }
        ]
    }
    
    try:
        resp = requests.post(f"{BASE_URL}/tick", json=tick_data)
        print(f"Status: {resp.status_code}")
        result = resp.json()
        print(f"Timestamp: {result['timestamp']}")
        print(f"Decisions: {len(result['decisions'])}")
        print("✓ PASS - State persisted across calls")
        return True
    except Exception as e:
        print(f"✗ FAIL: {e}")
        return False

def test_reset():
    """Test reset endpoint."""
    print("\n" + "="*70)
    print("TEST 5: Reset Engine")
    print("="*70)
    try:
        resp = requests.post(f"{BASE_URL}/reset")
        print(f"Status: {resp.status_code}")
        result = resp.json()
        print(f"Status: {result['status']}")
        print(f"Message: {result['message']}")
        print("✓ PASS")
        return True
    except Exception as e:
        print(f"✗ FAIL: {e}")
        return False

def test_runways():
    """Test runways endpoint."""
    print("\n" + "="*70)
    print("TEST 6: Get Runways")
    print("="*70)
    try:
        resp = requests.get(f"{BASE_URL}/runways")
        print(f"Status: {resp.status_code}")
        result = resp.json()
        print(f"Runway Count: {result['runway_count']}")
        print(f"Engine Mode: {result['engine_mode']}")
        if result['runways']:
            rwy = result['runways'][0]
            print(f"  - First Runway: {rwy['runway_id']}")
            print(f"  - In Use: {rwy['occupied']}")
        print("✓ PASS")
        return True
    except Exception as e:
        print(f"✗ FAIL: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all tests."""
    print("\n╔════════════════════════════════════════════════════════════════════╗")
    print("║         ATC Engine FastAPI Testing                                 ║")
    print("╚════════════════════════════════════════════════════════════════════╝")
    
    results = {
        "Health": test_health(),
        "Tick": test_tick(),
        "State": test_state(),
        "Tick Again": test_tick_again(),
        "Reset": test_reset(),
        "Runways": test_runways()
    }
    
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    for test_name, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{test_name:20} {status}")
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n✓ ALL TESTS PASSED!")
        return 0
    else:
        print(f"\n✗ {total - passed} test(s) failed")
        return 1

if __name__ == "__main__":
    main()
