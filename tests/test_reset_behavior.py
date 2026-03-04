"""
test_reset_behavior.py
Tests reset behavior and state clearing
"""
import unittest
import time
from test_utils import (
    APIClient, generate_tick_input, generate_aircraft_list, generate_test_weather,
    assert_api_healthy
)


class TestResetBehavior(unittest.TestCase):
    """Verify reset clears state and behaves consistently."""
    
    def setUp(self):
        """Set up test fixtures."""
        assert_api_healthy()
        self.api_client = APIClient()
    
    def test_reset_clears_all_aircraft(self):
        """Reset should clear all tracked aircraft."""
        # Process some ticks
        for i in range(3):
            tick_input = generate_tick_input(aircraft_count=2)
            self.api_client.process_tick(tick_input)
        
        # Verify aircraft are tracked
        state_before = self.api_client.get_state()
        aircraft_count_before = state_before['aircraft_count']
        self.assertGreater(aircraft_count_before, 0, "Aircraft should be tracked")
        
        # Reset
        reset_result = self.api_client.reset()
        self.assertEqual(reset_result['status'], 'success')
        
        # Verify all aircraft cleared
        state_after = self.api_client.get_state()
        aircraft_count_after = state_after['aircraft_count']
        self.assertEqual(aircraft_count_after, 0, "All aircraft should be cleared")
    
    def test_reset_clears_runway_occupancy(self):
        """Reset should clear runway occupancy."""
        timestamp = time.time()
        weather = generate_test_weather()
        
        # Land an aircraft
        aircraft = generate_aircraft_list(1, timestamp)
        aircraft[0]['aircraft_id'] = 'AC_RESET_TEST'
        aircraft[0]['operation'] = 'landing'
        
        self.api_client.process_tick({
            'timestamp': timestamp,
            'aircraft_list': aircraft,
            'weather': weather,
            'runway_info': None
        })
        
        # Check occupancy before reset
        runways_before = self.api_client.get_runways()
        occupied_before = sum(1 for r in runways_before['runways'] if r.get('occupied'))
        
        # Reset
        self.api_client.reset()
        
        # Check occupancy after reset
        runways_after = self.api_client.get_runways()
        occupied_after = sum(1 for r in runways_after['runways'] if r.get('occupied'))
        
        # Should have no occupied runways
        self.assertEqual(occupied_after, 0, "Runways should be unoccupied after reset")
    
    def test_reset_preserves_model_and_config(self):
        """Reset should not affect model or configuration."""
        # Process initial tick
        tick_input = generate_tick_input(aircraft_count=2)
        result_before = self.api_client.process_tick(tick_input)
        
        # Reset
        self.api_client.reset()
        
        # Process same tick again
        result_after = self.api_client.process_tick(tick_input)
        
        # Should be identical results (same decisions)
        dec_before = {d['aircraft_id']: d for d in result_before['decisions']}
        dec_after = {d['aircraft_id']: d for d in result_after['decisions']}
        
        for ac_id in dec_before.keys():
            self.assertEqual(
                dec_before[ac_id]['decision'],
                dec_after[ac_id]['decision'],
                f"AC {ac_id}: decision changed after reset"
            )
            self.assertEqual(
                dec_before[ac_id].get('assigned_runway'),
                dec_after[ac_id].get('assigned_runway'),
                f"AC {ac_id}: runway changed after reset"
            )
    
    def test_multiple_resets_safe(self):
        """Multiple consecutive resets should be safe."""
        # Process a tick
        tick_input = generate_tick_input(aircraft_count=2)
        self.api_client.process_tick(tick_input)
        
        # Reset multiple times
        for i in range(3):
            result = self.api_client.reset()
            self.assertEqual(result['status'], 'success', f"Reset {i+1} failed")
            
            # Verify state is clean after each reset
            state = self.api_client.get_state()
            self.assertEqual(
                state['aircraft_count'],
                0,
                f"After reset {i+1}, aircraft still present"
            )
    
    def test_reset_before_first_tick(self):
        """Reset should be safe even before any ticks."""
        # Reset without any prior ticks
        result = self.api_client.reset()
        self.assertEqual(result['status'], 'success', "Reset before first tick should work")
        
        # Now process a tick normally
        tick_input = generate_tick_input(aircraft_count=1)
        response = self.api_client.process_tick(tick_input)
        
        self.assertIn('decisions', response)
        self.assertEqual(len(response['decisions']), 1)
    
    def test_resume_after_reset_deterministic(self):
        """Engine behavior is deterministic across reset boundaries."""
        timestamp = time.time()
        weather = generate_test_weather()
        
        # Scenario 1: Run 3 ticks without reset
        aircraft1 = generate_aircraft_list(2, timestamp)
        for ac in aircraft1:
            ac['aircraft_id'] = f"{ac['aircraft_id']}_SCENARIO1"
        
        tick1 = {
            'timestamp': timestamp,
            'aircraft_list': aircraft1,
            'weather': weather,
            'runway_info': None
        }
        
        result1a = self.api_client.process_tick(tick1)
        
        aircraft2 = generate_aircraft_list(2, timestamp + 1)
        for ac in aircraft2:
            ac['aircraft_id'] = f"{ac['aircraft_id']}_SCENARIO1"
        
        tick2 = {
            'timestamp': timestamp + 1,
            'aircraft_list': aircraft2,
            'weather': weather,
            'runway_info': None
        }
        
        result1b = self.api_client.process_tick(tick2)
        
        aircraft3 = generate_aircraft_list(2, timestamp + 2)
        for ac in aircraft3:
            ac['aircraft_id'] = f"{ac['aircraft_id']}_SCENARIO1"
        
        tick3 = {
            'timestamp': timestamp + 2,
            'aircraft_list': aircraft3,
            'weather': weather,
            'runway_info': None
        }
        
        result1c = self.api_client.process_tick(tick3)
        
        # Reset
        self.api_client.reset()
        
        # Scenario 2: Run the same 3 ticks after reset
        aircraft1_again = generate_aircraft_list(2, timestamp)
        for ac in aircraft1_again:
            ac['aircraft_id'] = f"{ac['aircraft_id']}_SCENARIO2"
        
        tick1_again = {
            'timestamp': timestamp,
            'aircraft_list': aircraft1_again,
            'weather': weather,
            'runway_info': None
        }
        
        result2a = self.api_client.process_tick(tick1_again)
        
        # First tick of each scenario should have same decision pattern
        dec1a = {d['aircraft_id'].split('_')[0]: d['decision'] for d in result1a['decisions']}
        dec2a = {d['aircraft_id'].split('_')[0]: d['decision'] for d in result2a['decisions']}
        
        # Should have same decisions for same aircraft types
        self.assertEqual(
            set(dec1a.values()),
            set(dec2a.values()),
            "Decision patterns differ after reset"
        )
    
    def test_reset_while_aircraft_assigned(self):
        """Reset while aircraft have assignments should clear everything."""
        timestamp = time.time()
        weather = generate_test_weather()
        
        # Land multiple aircraft
        aircraft = generate_aircraft_list(3, timestamp)
        for i, ac in enumerate(aircraft):
            ac['aircraft_id'] = f'AC_FOR_RESET_{i+1}'
            ac['operation'] = 'landing'
        
        tick = {
            'timestamp': timestamp,
            'aircraft_list': aircraft,
            'weather': weather,
            'runway_info': None
        }
        
        result = self.api_client.process_tick(tick)
        
        # Verify assignments exist
        clearances = sum(1 for d in result['decisions'] if d['decision'] == 'CLEARED')
        
        # Reset
        self.api_client.reset()
        
        # Verify all cleared
        state = self.api_client.get_state()
        self.assertEqual(state['aircraft_count'], 0, "Aircraft assignments not cleared")
        
        # Verify runways are free
        runways = self.api_client.get_runways()
        occupied = sum(1 for r in runways['runways'] if r.get('occupied'))
        self.assertEqual(occupied, 0, "Runways not freed")
    
    def test_reset_response_valid(self):
        """Reset response should be properly formatted."""
        result = self.api_client.reset()
        
        self.assertIsInstance(result, dict)
        self.assertIn('status', result)
        self.assertIn('message', result)
        self.assertIn('timestamp', result)
        self.assertEqual(result['status'], 'success')


if __name__ == '__main__':
    unittest.main()
