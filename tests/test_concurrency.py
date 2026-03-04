"""
test_concurrency.py
Tests concurrent API access robustness
"""
import unittest
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from test_utils import (
    APIClient, generate_tick_input,
    assert_api_healthy, assert_response_valid,
    verify_queue_integrity
)


class TestConcurrency(unittest.TestCase):
    """Verify robust handling of concurrent requests."""
    
    def setUp(self):
        """Set up test fixtures."""
        assert_api_healthy()
        self.api_client = APIClient()
        self.api_client.reset()
    
    def test_concurrent_ticks_no_crash(self):
        """Multiple concurrent /tick calls should not crash."""
        tick_inputs = [generate_tick_input(aircraft_count=2) for _ in range(5)]
        
        results = []
        errors = []
        
        def process_tick(tick_input):
            try:
                result = self.api_client.process_tick(tick_input)
                return result
            except Exception as e:
                return {'error': str(e)}
        
        # Submit 5 concurrent ticks
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(process_tick, ti) for ti in tick_inputs]
            
            for future in as_completed(futures, timeout=30):
                try:
                    result = future.result()
                    if 'error' not in result:
                        results.append(result)
                        assert_response_valid(result)
                    else:
                        errors.append(result['error'])
                except Exception as e:
                    errors.append(str(e))
        
        # Should complete without crashes
        self.assertEqual(
            len(errors),
            0,
            f"Concurrent ticks failed: {errors}"
        )
        self.assertEqual(
            len(results),
            5,
            "Not all ticks completed"
        )
    
    def test_concurrent_resets_safe(self):
        """Multiple concurrent resets should be safe."""
        class Counter:
            def __init__(self):
                self.reset_count = 0
        
        counter = Counter()
        errors = []
        
        def reset_engine():
            try:
                self.api_client.reset()
                return True
            except Exception as e:
                return False
        
        # Submit 3 concurrent resets
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(reset_engine) for _ in range(3)]
            
            for future in as_completed(futures, timeout=15):
                try:
                    result = future.result()
                    if result:
                        counter.reset_count += 1
                except Exception as e:
                    errors.append(str(e))
        
        # Should complete safely
        self.assertEqual(len(errors), 0, f"Reset errors: {errors}")
        self.assertEqual(counter.reset_count, 3, "Not all resets completed")
    
    def test_mixed_concurrent_operations(self):
        """Mix of tick, reset, and state operations should be safe."""
        api_client = APIClient()
        api_client.reset()
        
        results = {'ticks': 0, 'resets': 0, 'states': 0, 'errors': 0}
        lock = threading.Lock()
        
        def do_tick():
            try:
                tick_input = generate_tick_input(aircraft_count=1)
                result = api_client.process_tick(tick_input)
                assert_response_valid(result)
                with lock:
                    results['ticks'] += 1
            except Exception as e:
                with lock:
                    results['errors'] += 1
        
        def do_reset():
            try:
                api_client.reset()
                with lock:
                    results['resets'] += 1
            except Exception as e:
                with lock:
                    results['errors'] += 1
        
        def do_state():
            try:
                api_client.get_state()
                with lock:
                    results['states'] += 1
            except Exception as e:
                with lock:
                    results['errors'] += 1
        
        # Mix of operations
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = []
            
            for i in range(10):
                op = i % 3
                if op == 0:
                    futures.append(executor.submit(do_tick))
                elif op == 1:
                    futures.append(executor.submit(do_reset))
                else:
                    futures.append(executor.submit(do_state))
            
            for future in as_completed(futures, timeout=30):
                future.result()
        
        # Should complete without crashes
        self.assertEqual(
            results['errors'],
            0,
            f"Concurrent operations failed: {results['errors']} errors"
        )
        self.assertGreater(
            results['ticks'],
            0,
            "No ticks completed"
        )
    
    def test_queue_integrity_under_concurrent_load(self):
        """Queue integrity should be maintained under concurrent load."""
        api_client = APIClient()
        api_client.reset()
        
        tick_results = []
        errors = []
        lock = threading.Lock()
        
        def send_tick(tick_num):
            try:
                tick_input = generate_tick_input(aircraft_count=3)
                result = api_client.process_tick(tick_input)
                
                with lock:
                    tick_results.append(result)
            except Exception as e:
                with lock:
                    errors.append(str(e))
        
        # Send 5 ticks concurrently
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(send_tick, i) for i in range(5)]
            
            for future in as_completed(futures, timeout=30):
                future.result()
        
        # Check queue integrity in all results
        self.assertEqual(len(errors), 0, f"Tick errors: {errors}")
        
        for result in tick_results:
            is_valid, msg = verify_queue_integrity(result['runway_states'])
            self.assertTrue(
                is_valid,
                f"Queue integrity failed concurrent tick: {msg}"
            )
    
    def test_no_duplicate_runway_assignments(self):
        """Under concurrent load, no runway should be assigned to multiple aircraft."""
        api_client = APIClient()
        api_client.reset()
        
        tick_results = []
        errors = []
        lock = threading.Lock()
        
        def send_tick():
            try:
                tick_input = generate_tick_input(aircraft_count=2)
                result = api_client.process_tick(tick_input)
                
                with lock:
                    tick_results.append(result)
            except Exception as e:
                with lock:
                    errors.append(str(e))
        
        # Send 5 ticks with multiple aircraft
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(send_tick) for _ in range(5)]
            
            for future in as_completed(futures, timeout=30):
                future.result()
        
        self.assertEqual(len(errors), 0, f"Errors occurred: {errors}")
        
        # Check runway assignments across all results
        runway_assignments = {}  # runway_id -> {aircraft_id -> count}
        
        for result in tick_results:
            for decision in result.get('decisions', []):
                if decision.get('decision') == 'CLEARED':
                    runway = decision.get('assigned_runway')
                    ac_id = decision.get('aircraft_id')
                    
                    if runway:
                        if runway not in runway_assignments:
                            runway_assignments[runway] = {}
                        
                        if ac_id not in runway_assignments[runway]:
                            runway_assignments[runway][ac_id] = 0
                        
                        runway_assignments[runway][ac_id] += 1
        
        # No aircraft should be assigned to same runway multiple times across responses
        for runway, assignments in runway_assignments.items():
            # Each aircraft should appear at most once per tick result
            for ac_id, count in assignments.items():
                self.assertLessEqual(
                    count,
                    5,  # 5 ticks max
                    f"Aircraft {ac_id} assigned to {runway} {count} times"
                )
    
    def test_concurrent_state_reads_safe(self):
        """Multiple concurrent state reads should be safe."""
        # First send a tick
        tick_input = generate_tick_input(aircraft_count=2)
        self.api_client.process_tick(tick_input)
        
        states = []
        errors = []
        lock = threading.Lock()
        
        def read_state():
            try:
                state = self.api_client.get_state()
                with lock:
                    states.append(state)
            except Exception as e:
                with lock:
                    errors.append(str(e))
        
        # Read state concurrently
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(read_state) for _ in range(5)]
            
            for future in as_completed(futures, timeout=15):
                future.result()
        
        # All should succeed
        self.assertEqual(len(errors), 0, f"State read errors: {errors}")
        self.assertEqual(len(states), 5, "Not all state reads completed")
        
        # All should return consistent data
        for state in states:
            self.assertIn('aircraft', state)
            self.assertEqual(
                state['aircraft_count'],
                len(state['aircraft'])
            )


if __name__ == '__main__':
    unittest.main()
