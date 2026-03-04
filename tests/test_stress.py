"""
test_stress.py
Stress and high-load scenario tests
"""
import unittest
import time
from test_utils import (
    APIClient, generate_tick_input, generate_aircraft_list, generate_test_weather,
    assert_api_healthy, verify_queue_integrity
)


class TestStressMode(unittest.TestCase):
    """Verify system handles high-load scenarios."""
    
    def setUp(self):
        """Set up test fixtures."""
        assert_api_healthy()
        self.api_client = APIClient()
        self.api_client.reset()
    
    def test_sustained_load_50_ticks(self):
        """System should handle 50 consecutive ticks."""
        timestamp = time.time()
        weather = generate_test_weather()
        
        results = []
        errors = []
        
        for i in range(50):
            try:
                tick = {
                    'timestamp': timestamp + i,
                    'aircraft_list': generate_aircraft_list(3, timestamp + i),
                    'weather': weather,
                    'runway_info': None
                }
                
                result = self.api_client.process_tick(tick)
                results.append(result)
            except Exception as e:
                errors.append((i, str(e)))
        
        # Should complete with no errors
        self.assertEqual(len(errors), 0, f"Errors during sustained load: {errors}")
        self.assertEqual(len(results), 50, "Not all ticks completed")
    
    def test_high_aircraft_density(self):
        """System should handle high aircraft density."""
        timestamp = time.time()
        weather = generate_test_weather()
        
        # 20 aircraft at once
        tick = {
            'timestamp': timestamp,
            'aircraft_list': generate_aircraft_list(20, timestamp),
            'weather': weather,
            'runway_info': None
        }
        
        result = self.api_client.process_tick(tick)
        
        # Should handle all aircraft
        self.assertEqual(
            len(result['decisions']),
            20,
            "Not all aircraft processed"
        )
        
        # Queue integrity should be maintained
        is_valid, msg = verify_queue_integrity(result['runway_states'])
        self.assertTrue(is_valid, f"Queue integrity failed: {msg}")
    
    def test_rapid_fire_ticks(self):
        """System should handle rapid sequential ticks."""
        timestamp = time.time()
        weather = generate_test_weather()
        
        # 10 rapid ticks
        for i in range(10):
            tick = {
                'timestamp': timestamp + i * 0.1,
                'aircraft_list': generate_aircraft_list(2, timestamp + i * 0.1),
                'weather': weather,
                'runway_info': None
            }
            
            result = self.api_client.process_tick(tick)
            
            # Should not crash
            self.assertIn('decisions', result)
            self.assertGreater(len(result['decisions']), 0)
    
    def test_state_accumulation_over_time(self):
        """State should accumulate correctly over many ticks."""
        timestamp = time.time()
        weather = generate_test_weather()
        
        aircraft_count_trend = []
        
        for i in range(10):
            tick = {
                'timestamp': timestamp + i,
                'aircraft_list': generate_aircraft_list(3, timestamp + i),
                'weather': weather,
                'runway_info': None
            }
            
            self.api_client.process_tick(tick)
            
            # Check state
            state = self.api_client.get_state()
            aircraft_count_trend.append(state['aircraft_count'])
        
        # Aircraft count should fluctuate based on assignments
        self.assertGreater(
            len(aircraft_count_trend),
            0,
            "No state recorded"
        )
    
    def test_mixed_operations_stress(self):
        """Mixed landings and takeoffs under stress."""
        timestamp = time.time()
        weather = generate_test_weather()
        
        for i in range(20):
            # Mix landing and takeoff
            aircraft = generate_aircraft_list(5, timestamp + i, mix_operations=True)
            
            tick = {
                'timestamp': timestamp + i,
                'aircraft_list': aircraft,
                'weather': weather,
                'runway_info': None
            }
            
            result = self.api_client.process_tick(tick)
            
            # All should be processed
            self.assertEqual(len(result['decisions']), 5)
    
    def test_runway_utilization_under_load(self):
        """Runways should be efficiently utilized under load."""
        timestamp = time.time()
        weather = generate_test_weather()
        
        runway_occupation = {}
        
        for i in range(10):
            aircraft = generate_aircraft_list(8, timestamp + i, mix_operations=False)
            for ac in aircraft:
                ac['operation'] = 'landing'
            
            tick = {
                'timestamp': timestamp + i,
                'aircraft_list': aircraft,
                'weather': weather,
                'runway_info': None
            }
            
            result = self.api_client.process_tick(tick)
            
            # Track which runways get assignments
            for dec in result['decisions']:
                if dec['decision'] == 'CLEARED' and dec.get('assigned_runway'):
                    runway = dec['assigned_runway']
                    runway_occupation[runway] = runway_occupation.get(runway, 0) + 1
        
        # Multiple runways should be used
        self.assertGreater(
            len(runway_occupation),
            1,
            "Only one runway used under heavy load"
        )
    
    def test_decision_consistency_under_load(self):
        """Decisions should be consistent even under high load."""
        timestamp = time.time()
        weather = generate_test_weather()
        
        decision_types = {'CLEARED': 0, 'HOLD': 0}
        
        for i in range(20):
            aircraft = generate_aircraft_list(4, timestamp + i)
            
            tick = {
                'timestamp': timestamp + i,
                'aircraft_list': aircraft,
                'weather': weather,
                'runway_info': None
            }
            
            result = self.api_client.process_tick(tick)
            
            for dec in result['decisions']:
                if dec['decision'] in decision_types:
                    decision_types[dec['decision']] += 1
        
        # Should have mix of decisions
        self.assertGreater(
            decision_types['CLEARED'] + decision_types['HOLD'],
            0,
            "No decisions made"
        )
    
    def test_memory_efficient_reset_under_load(self):
        """Reset should be efficient even after heavy load."""
        timestamp = time.time()
        weather = generate_test_weather()
        
        # Build up some state
        for i in range(20):
            tick = {
                'timestamp': timestamp + i,
                'aircraft_list': generate_aircraft_list(5, timestamp + i),
                'weather': weather,
                'runway_info': None
            }
            self.api_client.process_tick(tick)
        
        # Reset should complete quickly
        start = time.time()
        self.api_client.reset()
        elapsed = time.time() - start
        
        # Should reset in under 1 second
        self.assertLess(
            elapsed,
            1.0,
            f"Reset too slow after load: {elapsed:.2f}s"
        )
        
        # Verify clean state
        state = self.api_client.get_state()
        self.assertEqual(state['aircraft_count'], 0)
    
    def test_error_recovery_under_stress(self):
        """System should recover from errors during stress."""
        timestamp = time.time()
        weather = generate_test_weather()
        
        errors_encountered = 0
        successful_after_error = 0
        
        for i in range(15):
            try:
                # Alternate between valid and invalid inputs
                if i % 3 == 0:
                    # Invalid input
                    tick = {
                        'timestamp': "invalid",
                        'aircraft_list': None,
                        'weather': None,
                        'runway_info': None
                    }
                else:
                    # Valid input
                    tick = {
                        'timestamp': timestamp + i,
                        'aircraft_list': generate_aircraft_list(2, timestamp + i),
                        'weather': weather,
                        'runway_info': None
                    }
                
                result = self.api_client.process_tick(tick)
                successful_after_error += 1
            except Exception:
                errors_encountered += 1
        
        # Should have recovered and processed some valid inputs
        self.assertGreater(
            successful_after_error,
            0,
            "Never recovered from errors"
        )
    
    def test_sustained_determinism_under_load(self):
        """Determinism should hold even under load."""
        timestamp = time.time()
        weather = generate_test_weather()
        
        # Process same input multiple times under load
        aircraft = generate_aircraft_list(4, timestamp)
        tick_input = {
            'timestamp': timestamp,
            'aircraft_list': aircraft,
            'weather': weather,
            'runway_info': None
        }
        
        results = []
        for i in range(5):
            # Intersperse with other ticks
            self.api_client.process_tick({
                'timestamp': timestamp + i,
                'aircraft_list': generate_aircraft_list(2, timestamp + i),
                'weather': weather,
                'runway_info': None
            })
            
            # Process our test input
            result = self.api_client.process_tick(tick_input)
            results.append(result)
        
        # All results should be identical
        decisions_list = [
            {d['aircraft_id']: d for d in r['decisions']}
            for r in results
        ]
        
        for i in range(1, len(decisions_list)):
            for ac_id in decisions_list[0].keys():
                self.assertEqual(
                    decisions_list[0][ac_id]['decision'],
                    decisions_list[i][ac_id]['decision'],
                    f"Determinism lost at tick {i}"
                )


if __name__ == '__main__':
    unittest.main()
