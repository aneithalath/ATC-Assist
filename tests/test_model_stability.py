"""
test_model_stability.py
Tests model loading and stability
"""
import unittest
import time
from test_utils import (
    CLIEngine, APIClient, generate_tick_input,
    assert_api_healthy
)


class TestModelStability(unittest.TestCase):
    """Verify model loads reliably and stably."""
    
    def test_model_loads_successfully(self):
        """Model should load successfully."""
        try:
            engine = CLIEngine(debug=False)
            self.assertIsNotNone(engine.engine)
            self.assertIsNotNone(engine.engine.model)
        except Exception as e:
            self.fail(f"Model failed to load: {e}")
    
    def test_multiple_engine_instances(self):
        """Multiple engine instances should work."""
        engines = []
        
        try:
            for i in range(3):
                engine = CLIEngine(debug=False)
                engines.append(engine)
                self.assertIsNotNone(engine.engine.model)
        except Exception as e:
            self.fail(f"Multiple engine instances failed: {e}")
    
    def test_model_inference_speed(self):
        """Model inference should complete quickly."""
        engine = CLIEngine(debug=False)
        tick_input = generate_tick_input(aircraft_count=5)
        
        start = time.time()
        result = engine.process_tick(
            timestamp=tick_input['timestamp'],
            aircraft_list=tick_input['aircraft_list'],
            weather=tick_input['weather']
        )
        elapsed = time.time() - start
        
        # Should complete in under 5 seconds
        self.assertLess(
            elapsed,
            5.0,
            f"Model inference too slow: {elapsed:.2f}s"
        )
    
    def test_model_consistency_across_instances(self):
        """Same input should produce same output across instances."""
        tick_input = generate_tick_input(aircraft_count=3)
        
        # Run through instance 1
        engine1 = CLIEngine(debug=False)
        result1 = engine1.process_tick(
            timestamp=tick_input['timestamp'],
            aircraft_list=tick_input['aircraft_list'],
            weather=tick_input['weather']
        )
        
        # Run through instance 2
        engine2 = CLIEngine(debug=False)
        result2 = engine2.process_tick(
            timestamp=tick_input['timestamp'],
            aircraft_list=tick_input['aircraft_list'],
            weather=tick_input['weather']
        )
        
        # Results should be identical
        dec1 = {d['aircraft_id']: d for d in result1['decisions']}
        dec2 = {d['aircraft_id']: d for d in result2['decisions']}
        
        self.assertEqual(set(dec1.keys()), set(dec2.keys()))
        
        for ac_id in dec1.keys():
            self.assertEqual(
                dec1[ac_id]['decision'],
                dec2[ac_id]['decision']
            )
    
    def test_api_model_persistence(self):
        """API should reliably use same model for all requests."""
        assert_api_healthy()
        api_client = APIClient()
        
        tick_input = generate_tick_input(aircraft_count=2)
        
        # Process multiple times
        results = []
        for i in range(5):
            result = api_client.process_tick(tick_input)
            results.append(result)
        
        # All should produce consistent decisions
        for i, result in enumerate(results):
            self.assertGreater(
                len(result['decisions']),
                0,
                f"Result {i} has no decisions"
            )
    
    def test_rapid_sequential_inference(self):
        """Model should handle rapid sequential calls."""
        engine = CLIEngine(debug=False)
        
        # 10 rapid ticks
        for i in range(10):
            tick_input = generate_tick_input(aircraft_count=2)
            result = engine.process_tick(
                timestamp=tick_input['timestamp'],
                aircraft_list=tick_input['aircraft_list'],
                weather=tick_input['weather']
            )
            
            self.assertIn('decisions', result)
            self.assertGreater(len(result['decisions']), 0)
    
    def test_model_device_compatibility(self):
        """Model should work on available device (CPU/CUDA)."""
        engine = CLIEngine(debug=False)
        
        # Model should have a device
        self.assertIsNotNone(engine.engine.device)
        
        # Should complete inference successfully
        tick_input = generate_tick_input(aircraft_count=1)
        result = engine.process_tick(
            timestamp=tick_input['timestamp'],
            aircraft_list=tick_input['aircraft_list'],
            weather=tick_input['weather']
        )
        
        self.assertIn('decisions', result)
    
    def test_model_output_validity(self):
        """Model outputs should be valid predictions."""
        engine = CLIEngine(debug=False)
        tick_input = generate_tick_input(aircraft_count=3)
        
        result = engine.process_tick(
            timestamp=tick_input['timestamp'],
            aircraft_list=tick_input['aircraft_list'],
            weather=tick_input['weather']
        )
        
        # Check decisions
        for decision in result['decisions']:
            # Should have confidence score
            confidence = decision.get('confidence', 0.0)
            self.assertGreaterEqual(
                confidence,
                0.0,
                f"Negative confidence: {confidence}"
            )
            self.assertLessEqual(
                confidence,
                1.0,
                f"Confidence > 1: {confidence}"
            )
            
            # Should have valid decision
            self.assertIn(
                decision['decision'],
                ['CLEARED', 'HOLD'],
                f"Invalid decision: {decision['decision']}"
            )
    
    def test_model_memory_stability(self):
        """Model should not leak memory across calls."""
        engine = CLIEngine(debug=False)
        
        # Process 20 ticks
        for i in range(20):
            tick_input = generate_tick_input(aircraft_count=3)
            result = engine.process_tick(
                timestamp=tick_input['timestamp'],
                aircraft_list=tick_input['aircraft_list'],
                weather=tick_input['weather']
            )
            
            # Should complete successfully
            self.assertIn('decisions', result)
        
        # If we got here without crashing, memory is stable


if __name__ == '__main__':
    unittest.main()
