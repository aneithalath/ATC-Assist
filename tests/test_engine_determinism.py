"""
test_engine_determinism.py
Tests engine determinism: identical inputs produce identical outputs
"""
import unittest
import json
from test_utils import (
    CLIEngine, APIClient, generate_tick_input, assert_api_healthy,
    assert_response_valid, compare_responses
)


class TestEngineDeterminism(unittest.TestCase):
    """Verify engine produces deterministic outputs."""
    
    def setUp(self):
        """Set up test fixtures."""
        assert_api_healthy()
        self.api_client = APIClient()
        self.cli_engine = CLIEngine(debug=False)
        
        # Reset via API
        self.api_client.reset()
    
    def test_cli_determinism_identical_inputs(self):
        """Same CLI input should produce identical output."""
        tick_input = generate_tick_input(aircraft_count=3)
        
        # Run twice
        result1 = self.cli_engine.process_tick(
            timestamp=tick_input['timestamp'],
            aircraft_list=tick_input['aircraft_list'],
            weather=tick_input['weather']
        )
        
        result2 = self.cli_engine.process_tick(
            timestamp=tick_input['timestamp'],
            aircraft_list=tick_input['aircraft_list'],
            weather=tick_input['weather']
        )
        
        # Verify results are identical
        self.assertEqual(
            len(result1['decisions']),
            len(result2['decisions']),
            "Decision count mismatch"
        )
        
        for i, (dec1, dec2) in enumerate(zip(result1['decisions'], result2['decisions'])):
            self.assertEqual(
                dec1['aircraft_id'],
                dec2['aircraft_id'],
                f"Decision {i}: aircraft_id mismatch"
            )
            self.assertEqual(
                dec1['decision'],
                dec2['decision'],
                f"Decision {i}: decision mismatch"
            )
            self.assertEqual(
                dec1.get('assigned_runway'),
                dec2.get('assigned_runway'),
                f"Decision {i}: runway assignment mismatch"
            )
            self.assertAlmostEqual(
                dec1.get('confidence', 0.0),
                dec2.get('confidence', 0.0),
                places=5,
                msg=f"Decision {i}: confidence mismatch"
            )
    
    def test_api_determinism_identical_inputs(self):
        """Same API input should produce identical output (within tolerance)."""
        tick_input = generate_tick_input(aircraft_count=3)
        
        # Run twice via API
        result1 = self.api_client.process_tick(tick_input)
        result2 = self.api_client.process_tick(tick_input)
        
        assert_response_valid(result1)
        assert_response_valid(result2)
        
        # Compare decisions
        api_decs1 = {d['aircraft_id']: d for d in result1['decisions']}
        api_decs2 = {d['aircraft_id']: d for d in result2['decisions']}
        
        self.assertEqual(
            set(api_decs1.keys()),
            set(api_decs2.keys()),
            "Aircraft set changed between runs"
        )
        
        for ac_id in api_decs1.keys():
            dec1 = api_decs1[ac_id]
            dec2 = api_decs2[ac_id]
            
            self.assertEqual(
                dec1['decision'],
                dec2['decision'],
                f"AC {ac_id}: decision changed"
            )
            self.assertEqual(
                dec1.get('assigned_runway'),
                dec2.get('assigned_runway'),
                f"AC {ac_id}: runway changed"
            )
            self.assertAlmostEqual(
                dec1.get('confidence', 0.0),
                dec2.get('confidence', 0.0),
                places=3,
                msg=f"AC {ac_id}: confidence diverged"
            )
    
    def test_cli_vs_api_determinism(self):
        """CLI and API should produce compatible results for same input."""
        tick_input = generate_tick_input(aircraft_count=3)
        
        # Process via CLI
        cli_result = self.cli_engine.process_tick(
            timestamp=tick_input['timestamp'],
            aircraft_list=tick_input['aircraft_list'],
            weather=tick_input['weather']
        )
        
        # Process via API
        api_result = self.api_client.process_tick(tick_input)
        
        # Compare
        matches, diffs = compare_responses(api_result, cli_result)
        
        # Log differences for debugging
        if diffs:
            print(f"\nDifferences found (may be expected):")
            for diff in diffs:
                print(f"  - {diff}")
        
        # We expect them to be very similar
        self.assertTrue(
            matches or len(diffs) <= 2,  # Allow for minor differences
            f"CLI vs API: Too many differences: {diffs}"
        )
    
    def test_determinism_across_multiple_resets(self):
        """Same input produces same output after engine reset."""
        tick_input = generate_tick_input(aircraft_count=2)
        
        # Run 1: Process tick
        result1 = self.api_client.process_tick(tick_input)
        
        # Reset
        self.api_client.reset()
        
        # Run 2: Same input again
        result2 = self.api_client.process_tick(tick_input)
        
        # Results should be identical
        dec1 = {d['aircraft_id']: d for d in result1['decisions']}
        dec2 = {d['aircraft_id']: d for d in result2['decisions']}
        
        self.assertEqual(
            set(dec1.keys()),
            set(dec2.keys()),
            "Aircraft set differs after reset"
        )
        
        for ac_id in dec1.keys():
            self.assertEqual(
                dec1[ac_id]['decision'],
                dec2[ac_id]['decision'],
                f"AC {ac_id}: decision not deterministic after reset"
            )


if __name__ == '__main__':
    unittest.main()
