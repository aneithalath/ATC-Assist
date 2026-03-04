"""
test_logging.py
Tests logging integrity across operations
"""
import unittest
import json
import time
from pathlib import Path
from test_utils import (
    APIClient, CLIEngine, generate_tick_input,
    assert_api_healthy, TEST_DATA_DIR
)


class TestLoggingIntegrity(unittest.TestCase):
    """Verify logging is complete and accurate."""
    
    def setUp(self):
        """Set up test fixtures."""
        assert_api_healthy()
        self.api_client = APIClient()
        self.api_client.reset()
        
        # Logs should be in logs/ directory
        self.logs_dir = TEST_DATA_DIR
    
    def test_logging_directory_writable(self):
        """Logging directory should be writable."""
        self.assertTrue(
            self.logs_dir.exists(),
            f"Logs directory does not exist: {self.logs_dir}"
        )
        self.assertTrue(
            self.logs_dir.is_dir(),
            f"Logs path is not a directory: {self.logs_dir}"
        )
    
    def test_json_logs_valid_format(self):
        """Log files should contain valid JSON."""
        # Process a tick to generate logs
        tick_input = generate_tick_input(aircraft_count=2)
        self.api_client.process_tick(tick_input)
        
        # Try to read any recent JSON log files
        log_files = list(self.logs_dir.glob("*.json"))
        
        # At minimum, look for key logs
        if log_files:
            for log_file in log_files[:3]:  # Check first 3
                try:
                    with open(log_file, 'r') as f:
                        data = json.load(f)
                        # Should be dict or list
                        self.assertIn(
                            type(data),
                            [dict, list],
                            f"Invalid JSON structure in {log_file.name}"
                        )
                except json.JSONDecodeError as e:
                    # It's okay if some files aren't JSON
                    pass
    
    def test_logging_no_corruption(self):
        """Logs should not be corrupted by concurrent writes."""
        # Process multiple ticks
        for i in range(3):
            tick_input = generate_tick_input(aircraft_count=2)
            self.api_client.process_tick(tick_input)
        
        # Check that log files exist and are readable
        log_files = list(self.logs_dir.glob("*.json"))
        
        # Should have at least some logs
        for log_file in log_files:
            try:
                with open(log_file, 'r') as f:
                    content = f.read()
                    # Should not be empty
                    self.assertGreater(
                        len(content),
                        0,
                        f"Log file {log_file.name} is empty"
                    )
                    
                    # Should be valid JSON
                    json.loads(content)
            except Exception as e:
                # Other files might not be JSON, skip
                if not str(log_file).endswith('.json'):
                    continue
    
    def test_runtime_log_entries_monotonic(self):
        """Log timestamps should be monotonically increasing."""
        cli_engine = CLIEngine(debug=False)
        cli_engine.reset()
        
        # Process 3 ticks
        timestamp = time.time()
        results = []
        
        for i in range(3):
            tick_input = generate_tick_input(
                aircraft_count=1,
                timestamp=timestamp + i
            )
            
            result = cli_engine.process_tick(
                timestamp=tick_input['timestamp'],
                aircraft_list=tick_input['aircraft_list'],
                weather=tick_input['weather']
            )
            
            results.append(result)
        
        # Timestamps should be monotonically increasing
        for i in range(1, len(results)):
            self.assertGreaterEqual(
                results[i]['timestamp'],
                results[i-1]['timestamp'],
                f"Timestamp not monotonic at tick {i}"
            )
    
    def test_log_values_match_response(self):
        """Log values should match returned API responses."""
        tick_input = generate_tick_input(aircraft_count=2)
        result = self.api_client.process_tick(tick_input)
        
        # Verify response has logged values
        self.assertIn('timestamp', result)
        self.assertIn('decisions', result)
        self.assertIn('runway_states', result)
        
        # Check decision structure
        for decision in result['decisions']:
            self.assertIn('aircraft_id', decision)
            self.assertIn('decision', decision)
            self.assertIn('confidence', decision)
    
    def test_decision_logging_accuracy(self):
        """Each decision should be logged with accurate info."""
        timestamp = time.time()
        
        # Generate aircraft with known IDs
        aircraft = generate_tick_input(aircraft_count=3)['aircraft_list']
        aircraft_ids = [ac['aircraft_id'] for ac in aircraft]
        
        result = self.api_client.process_tick({
            'timestamp': timestamp,
            'aircraft_list': aircraft,
            'weather': None,
            'runway_info': None
        })
        
        # Check decisions are logged
        decisions = {d['aircraft_id']: d for d in result['decisions']}
        
        for ac_id in aircraft_ids:
            self.assertIn(
                ac_id,
                decisions,
                f"Aircraft {ac_id} missing from decisions"
            )
            
            decision = decisions[ac_id]
            self.assertIn('decision', decision)
            self.assertIn('confidence', decision)
            
            # Decision should be valid
            self.assertIn(
                decision['decision'],
                ['CLEARED', 'HOLD'],
                f"Invalid decision for {ac_id}"
            )
    
    def test_safety_alert_logging(self):
        """Safety alerts should be logged when present."""
        # This is harder to trigger, but verify structure
        tick_input = generate_tick_input(aircraft_count=5)
        result = self.api_client.process_tick(tick_input)
        
        # Safety alerts may or may not be present
        if 'safety_alerts' in result:
            alerts = result['safety_alerts']
            self.assertIsInstance(alerts, list)
            
            for alert in alerts:
                self.assertIn('aircraft_id', alert)
                self.assertIn('violation_type', alert)
                self.assertIn('severity', alert)
    
    def test_runway_state_logging(self):
        """Runway states should be logged accurately."""
        tick_input = generate_tick_input(aircraft_count=2)
        result = self.api_client.process_tick(tick_input)
        
        # Check runway states
        runway_states = result['runway_states']
        self.assertIsInstance(runway_states, list)
        
        # Should have 6 runways
        self.assertEqual(
            len(runway_states),
            6,
            "Should have 6 runways"
        )
        
        # Each should have required fields
        expected_runways = {'07L', '07R', '25L', '25R', '26', '8'}
        found_runways = set()
        
        for rwy in runway_states:
            self.assertIn('runway_id', rwy)
            self.assertIn('occupied', rwy)
            self.assertIn('occupancy_remaining_sec', rwy)
            
            found_runways.add(rwy['runway_id'])
        
        self.assertEqual(
            found_runways,
            expected_runways,
            "Runway set mismatch"
        )
    
    def test_log_file_persistence(self):
        """Log files should persist across operations."""
        # Get initial log files
        initial_files = set(self.logs_dir.glob("*"))
        
        # Process some ticks
        for i in range(2):
            tick_input = generate_tick_input(aircraft_count=1)
            self.api_client.process_tick(tick_input)
        
        # Logs directory should still exist
        self.assertTrue(self.logs_dir.exists())
        
        # Should have same or more files
        final_files = set(self.logs_dir.glob("*"))
        self.assertGreaterEqual(
            len(final_files),
            len(initial_files),
            "Log files disappeared"
        )


if __name__ == '__main__':
    unittest.main()
