"""
test_api_parity.py
Tests parity between CLI engine and API endpoints
"""
import unittest
import time
from test_utils import (
    CLIEngine, APIClient, generate_tick_input,
    assert_api_healthy, assert_response_valid,
    compare_responses
)


class TestAPIClIParity(unittest.TestCase):
    """Verify API and CLI produce compatible results."""
    
    def setUp(self):
        """Set up test fixtures."""
        assert_api_healthy()
        self.api_client = APIClient()
        self.cli_engine = CLIEngine(debug=False)
        
        # Reset both
        self.api_client.reset()
        self.cli_engine.reset()
    
    def test_tick_endpoint_parity_single_aircraft(self):
        """Single aircraft should produce parity between API and CLI."""
        tick_input = generate_tick_input(aircraft_count=1)
        
        # Process via CLI
        cli_result = self.cli_engine.process_tick(
            timestamp=tick_input['timestamp'],
            aircraft_list=tick_input['aircraft_list'],
            weather=tick_input['weather']
        )
        
        # Process via API
        api_result = self.api_client.process_tick(tick_input)
        
        # Validate responses
        assert_response_valid(api_result)
        
        # Compare
        matches, diffs = compare_responses(api_result, cli_result)
        self.assertTrue(matches, f"Parity lost: {diffs}")
    
    def test_tick_endpoint_parity_multiple_aircraft(self):
        """Multiple aircraft should produce parity."""
        tick_input = generate_tick_input(aircraft_count=5)
        
        cli_result = self.cli_engine.process_tick(
            timestamp=tick_input['timestamp'],
            aircraft_list=tick_input['aircraft_list'],
            weather=tick_input['weather']
        )
        
        api_result = self.api_client.process_tick(tick_input)
        assert_response_valid(api_result)
        
        # Both should have same aircraft
        cli_decs = {d['aircraft_id']: d for d in cli_result.get('decisions', [])}
        api_decs = {d['aircraft_id']: d for d in api_result.get('decisions', [])}
        
        self.assertEqual(
            set(cli_decs.keys()),
            set(api_decs.keys()),
            "Aircraft set differs between CLI and API"
        )
        
        # Each aircraft should have compatible decisions
        for ac_id in cli_decs.keys():
            cli_dec = cli_decs[ac_id]
            api_dec = api_decs[ac_id]
            
            self.assertEqual(
                cli_dec['decision'],
                api_dec['decision'],
                f"AC {ac_id}: decision mismatch between CLI and API"
            )
    
    def test_reset_endpoint_parity(self):
        """Reset should work identically in API and CLI."""
        # Warm up with a tick
        tick_input = generate_tick_input(aircraft_count=2)
        
        self.api_client.process_tick(tick_input)
        self.cli_engine.process_tick(
            timestamp=tick_input['timestamp'],
            aircraft_list=tick_input['aircraft_list'],
            weather=tick_input['weather']
        )
        
        # Reset via API
        api_reset = self.api_client.reset()
        self.assertEqual(api_reset['status'], 'success')
        
        # Reset via CLI
        self.cli_engine.reset()
        
        # Both should produce identical results on next tick
        tick_input2 = generate_tick_input(aircraft_count=2)
        
        api_result2 = self.api_client.process_tick(tick_input2)
        cli_result2 = self.cli_engine.process_tick(
            timestamp=tick_input2['timestamp'],
            aircraft_list=tick_input2['aircraft_list'],
            weather=tick_input2['weather']
        )
        
        # Compare
        matches, diffs = compare_responses(api_result2, cli_result2)
        self.assertTrue(matches, f"Parity after reset lost: {diffs}")
    
    def test_state_endpoint_consistency(self):
        """State endpoint should return currently tracked aircraft."""
        # Process some ticks
        for i in range(3):
            tick_input = generate_tick_input(aircraft_count=2)
            self.api_client.process_tick(tick_input)
        
        # Get state
        state = self.api_client.get_state()
        
        # Verify structure
        self.assertIn('aircraft', state)
        self.assertIn('aircraft_count', state)
        self.assertEqual(
            state['aircraft_count'],
            len(state['aircraft']),
            "Aircraft count mismatch"
        )
        
        # Each aircraft should have required fields
        for ac in state['aircraft']:
            self.assertIn('id', ac)
            self.assertIn('current_state', ac)
    
    def test_runways_endpoint_consistency(self):
        """Runways endpoint should return valid runway states."""
        # Process a tick
        tick_input = generate_tick_input(aircraft_count=2)
        self.api_client.process_tick(tick_input)
        
        # Get runways
        runways = self.api_client.get_runways()
        
        # Verify structure
        self.assertIn('runways', runways)
        self.assertIn('runway_count', runways)
        self.assertEqual(
            runways['runway_count'],
            len(runways['runways']),
            "Runway count mismatch"
        )
        
        # Expected runways
        expected_runways = {'07L', '07R', '25L', '25R', '26', '8'}
        found_runways = {r['runway_id'] for r in runways['runways']}
        
        self.assertEqual(
            found_runways,
            expected_runways,
            "Runway set mismatch"
        )
        
        # Each runway should have required fields
        for rwy in runways['runways']:
            self.assertIn('runway_id', rwy)
            self.assertIn('occupied', rwy)
    
    def test_sequential_ticks_parity(self):
        """Sequential ticks should maintain parity across CLI and API."""
        cli_engine_seq = CLIEngine(debug=False)
        api_client_seq = APIClient()
        
        # Reset
        api_client_seq.reset()
        cli_engine_seq.reset()
        
        # Run 3 sequential ticks with both engines
        timestamp = time.time()
        
        for i in range(3):
            tick_input = generate_tick_input(
                aircraft_count=2,
                timestamp=timestamp + i
            )
            
            cli_result = cli_engine_seq.process_tick(
                timestamp=tick_input['timestamp'],
                aircraft_list=tick_input['aircraft_list'],
                weather=tick_input['weather']
            )
            
            api_result = api_client_seq.process_tick(tick_input)
            
            # Compare
            matches, diffs = compare_responses(api_result, cli_result)
            
            self.assertTrue(
                matches or len(diffs) <= 1,
                f"Tick {i}: Parity lost: {diffs}"
            )
    
    def test_health_check_parity(self):
        """Health check should reflect actual status."""
        health = self.api_client.health_check()
        
        self.assertEqual(health['status'], 'healthy')
        self.assertIn('engine_mode', health)
        self.assertIn('message', health)
        self.assertIn('timestamp', health)
    
    def test_error_handling_consistency(self):
        """Error conditions should be handled consistently."""
        # Test with empty aircraft list
        tick_input = generate_tick_input(aircraft_count=0)
        
        try:
            api_result = self.api_client.process_tick(tick_input)
            # Should still return valid structure
            self.assertIn('decisions', api_result)
            self.assertEqual(len(api_result['decisions']), 0)
        except Exception as e:
            self.fail(f"API should handle empty aircraft list: {e}")
        
        # CLI should also handle it
        try:
            cli_result = self.cli_engine.process_tick(
                timestamp=tick_input['timestamp'],
                aircraft_list=tick_input['aircraft_list'],
                weather=tick_input['weather']
            )
            self.assertIn('decisions', cli_result)
        except Exception as e:
            self.fail(f"CLI should handle empty aircraft list: {e}")


if __name__ == '__main__':
    unittest.main()
