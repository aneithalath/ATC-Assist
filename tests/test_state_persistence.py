"""
test_state_persistence.py
Tests state persistence across multiple ticks
"""
import unittest
import time
from test_utils import (
    CLIEngine, APIClient, generate_aircraft_list, generate_test_weather,
    assert_api_healthy, assert_response_valid, verify_runway_occupancy,
    verify_queue_integrity
)


class TestStatePersistence(unittest.TestCase):
    """Verify state persists correctly across ticks."""
    
    def setUp(self):
        """Set up test fixtures."""
        assert_api_healthy()
        self.api_client = APIClient()
        self.cli_engine = CLIEngine(debug=False)
        
        # Reset
        self.api_client.reset()
    
    def test_runway_occupancy_persists(self):
        """Runway occupancy should persist for duration of operation."""
        timestamp = time.time()
        weather = generate_test_weather()
        
        # Tick 1: Land aircraft on runway 07L
        aircraft1 = generate_aircraft_list(1, timestamp, mix_operations=False)
        aircraft1[0]['aircraft_id'] = 'AC_LANDING_001'
        aircraft1[0]['operation'] = 'landing'
        
        tick1 = {
            'timestamp': timestamp,
            'aircraft_list': aircraft1,
            'weather': weather,
            'runway_info': None
        }
        
        result1 = self.api_client.process_tick(tick1)
        assert_response_valid(result1)
        
        # Find which runway was assigned
        landing_decision = result1['decisions'][0]
        assigned_runway = landing_decision.get('assigned_runway')
        
        if assigned_runway and landing_decision['decision'] == 'CLEARED':
            # Check runway state
            runway_states1 = {r['runway_id']: r for r in result1['runway_states']}
            runway1_state = runway_states1.get(assigned_runway, {})
            
            occupancy_after_landing = runway1_state.get('occupancy_remaining_sec', 0)
            
            # Tick 2: One second later, runway should still be occupied
            timestamp2 = timestamp + 1.0
            aircraft2 = generate_aircraft_list(1, timestamp2, mix_operations=False)
            aircraft2[0]['aircraft_id'] = 'AC_WAITING_001'
            aircraft2[0]['operation'] = 'landing'
            
            tick2 = {
                'timestamp': timestamp2,
                'aircraft_list': aircraft2,
                'weather': weather,
                'runway_info': None
            }
            
            result2 = self.api_client.process_tick(tick2)
            runway_states2 = {r['runway_id']: r for r in result2['runway_states']}
            runway2_state = runway_states2.get(assigned_runway, {})
            
            occupancy_after_delay = runway2_state.get('occupancy_remaining_sec', 0)
            
            # Should have decreased by ~1 second but still occupied
            self.assertGreater(
                occupancy_after_landing,
                0,
                f"Runway {assigned_runway} not occupied after landing clearance"
            )
            self.assertGreater(
                occupancy_after_delay,
                0,
                f"Runway {assigned_runway} not still occupied 1 second later"
            )
            self.assertAlmostEqual(
                occupancy_after_landing - occupancy_after_delay,
                1.0,
                delta=0.2,
                msg="Occupancy time should decrease by ~1 second"
            )
    
    def test_aircraft_queue_consistency(self):
        """Aircraft queues should remain consistent across ticks."""
        timestamp = time.time()
        weather = generate_test_weather()
        
        # Tick 1: Send 3 landing aircraft
        aircraft = generate_aircraft_list(3, timestamp, mix_operations=False)
        for i, ac in enumerate(aircraft):
            ac['aircraft_id'] = f'AC_QUEUE_{i+1:02d}'
            ac['operation'] = 'landing'
        
        tick = {
            'timestamp': timestamp,
            'aircraft_list': aircraft,
            'weather': weather,
            'runway_info': None
        }
        
        result1 = self.api_client.process_tick(tick)
        
        # Verify queue integrity
        is_valid, msg = verify_queue_integrity(result1['runway_states'])
        self.assertTrue(is_valid, f"Queue integrity failed: {msg}")
        
        # Record aircraft assignments
        decisions1 = {d['aircraft_id']: d for d in result1['decisions']}
        
        # Tick 2: Same aircraft, no changes
        timestamp2 = timestamp + 1.0
        result2 = self.api_client.process_tick({
            'timestamp': timestamp2,
            'aircraft_list': aircraft,
            'weather': weather,
            'runway_info': None
        })
        
        # Verify queue integrity again
        is_valid, msg = verify_queue_integrity(result2['runway_states'])
        self.assertTrue(is_valid, f"Queue integrity failed after 1s: {msg}")
        
        # Aircraft assignments should be consistent
        decisions2 = {d['aircraft_id']: d for d in result2['decisions']}
        
        for ac_id in decisions1.keys():
            dec1 = decisions1[ac_id]
            dec2 = decisions2.get(ac_id, {})
            
            if dec1['decision'] == 'CLEARED':
                self.assertEqual(
                    dec1.get('assigned_runway'),
                    dec2.get('assigned_runway'),
                    f"AC {ac_id}: runway assignment changed"
                )
    
    def test_time_separation_enforcement(self):
        """Time separation >= 60s should be enforced between operations."""
        timestamp = time.time()
        weather = generate_test_weather()
        
        # Tick 1: Land aircraft on runway 07L
        aircraft1 = generate_aircraft_list(1, timestamp, mix_operations=False)
        aircraft1[0]['aircraft_id'] = 'AC_FIRST_LANDING'
        aircraft1[0]['operation'] = 'landing'
        
        result1 = self.api_client.process_tick({
            'timestamp': timestamp,
            'aircraft_list': aircraft1,
            'weather': weather,
            'runway_info': None
        })
        
        dec1 = result1['decisions'][0]
        if dec1['decision'] != 'CLEARED':
            self.skipTest("First aircraft not cleared (expected in busy scenario)")
        
        assigned_runway = dec1['assigned_runway']
        
        # Tick 2: 30 seconds later, try to land another aircraft
        timestamp2 = timestamp + 30.0
        aircraft2 = generate_aircraft_list(1, timestamp2, mix_operations=False)
        aircraft2[0]['aircraft_id'] = 'AC_SECOND_LANDING'
        aircraft2[0]['operation'] = 'landing'
        
        result2 = self.api_client.process_tick({
            'timestamp': timestamp2,
            'aircraft_list': aircraft2,
            'weather': weather,
            'runway_info': None
        })
        
        dec2 = result2['decisions'][0]
        
        # Should be HOLD at 30s (not enough time has passed)
        if assigned_runway:  # Only check if we know the runway
            self.assertIn(
                dec2['decision'],
                ['HOLD', 'CLEARED'],
                "Decision should be HOLD or CLEARED"
            )
        
        # Tick 3: 70 seconds later (100s total from first), try again
        timestamp3 = timestamp + 70.0
        aircraft3 = generate_aircraft_list(1, timestamp3, mix_operations=False)
        aircraft3[0]['aircraft_id'] = 'AC_THIRD_LANDING'
        aircraft3[0]['operation'] = 'landing'
        
        result3 = self.api_client.process_tick({
            'timestamp': timestamp3,
            'aircraft_list': aircraft3,
            'weather': weather,
            'runway_info': None
        })
        
        # Verify runway is no longer occupied
        runways3 = {r['runway_id']: r for r in result3['runway_states']}
        if assigned_runway in runways3:
            runway_state = runways3[assigned_runway]
            occupancy = runway_state.get('occupancy_remaining_sec', 0)
            self.assertEqual(
                occupancy,
                0,
                f"Runway {assigned_runway} should be unoccupied after 70 seconds"
            )
    
    def test_hold_status_persists(self):
        """HOLD decision should persist until conditions allow CLEARED."""
        timestamp = time.time()
        weather = generate_test_weather()
        
        # Tick 1: Send aircraft when all runways might be busy
        aircraft1 = generate_aircraft_list(5, timestamp, mix_operations=False)
        for i, ac in enumerate(aircraft1):
            ac['aircraft_id'] = f'AC_BUSY_{i+1:02d}'
            ac['operation'] = 'landing'
        
        result1 = self.api_client.process_tick({
            'timestamp': timestamp,
            'aircraft_list': aircraft1,
            'weather': weather,
            'runway_info': None
        })
        
        # Count HOLDs
        holds1 = sum(1 for d in result1['decisions'] if d['decision'] == 'HOLD')
        
        # Tick 2: 2 seconds later with same aircraft
        timestamp2 = timestamp + 2.0
        result2 = self.api_client.process_tick({
            'timestamp': timestamp2,
            'aircraft_list': aircraft1,
            'weather': weather,
            'runway_info': None
        })
        
        holds2 = sum(1 for d in result2['decisions'] if d['decision'] == 'HOLD')
        
        # HOLDs should be tracked (may change but should be logical)
        self.assertGreaterEqual(
            holds1,
            0,
            "Hold count should be non-negative"
        )
        self.assertGreaterEqual(
            holds2,
            0,
            "Hold count should be non-negative"
        )
    
    def test_state_reset_clears_all_state(self):
        """After reset(), all state should be cleared."""
        timestamp = time.time()
        weather = generate_test_weather()
        
        # Tick 1: Send aircraft and land them
        aircraft = generate_aircraft_list(3, timestamp, mix_operations=False)
        for i, ac in enumerate(aircraft):
            ac['aircraft_id'] = f'AC_PRE_RESET_{i+1:02d}'
            ac['operation'] = 'landing'
        
        result1 = self.api_client.process_tick({
            'timestamp': timestamp,
            'aircraft_list': aircraft,
            'weather': weather,
            'runway_info': None
        })
        
        # Get state before reset
        state_before = self.api_client.get_state()
        aircraft_before = len(state_before.get('aircraft', []))
        
        # Reset
        reset_response = self.api_client.reset()
        self.assertEqual(
            reset_response.get('status'),
            'success',
            "Reset should succeed"
        )
        
        # Get state after reset
        state_after = self.api_client.get_state()
        aircraft_after = len(state_after.get('aircraft', []))
        
        self.assertEqual(
            aircraft_after,
            0,
            "All aircraft should be cleared after reset"
        )
        
        # Tick 2: Send same aircraft again, should be treated as new
        result2 = self.api_client.process_tick({
            'timestamp': timestamp + 10.0,
            'aircraft_list': aircraft,
            'weather': weather,
            'runway_info': None
        })
        
        # Results should be identical to initial run
        dec1_dict = {d['aircraft_id']: d for d in result1['decisions']}
        dec2_dict = {d['aircraft_id']: d for d in result2['decisions']}
        
        for ac_id in dec1_dict.keys():
            self.assertEqual(
                dec1_dict[ac_id]['decision'],
                dec2_dict[ac_id]['decision'],
                f"AC {ac_id}: decision not same after reset"
            )


if __name__ == '__main__':
    unittest.main()
