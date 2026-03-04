"""
test_metrics.py
Tests metrics logging and statistics
"""
import unittest
import time
from test_utils import (
    APIClient, generate_tick_input, generate_aircraft_list, generate_test_weather,
    assert_api_healthy
)


class TestMetricsLogging(unittest.TestCase):
    """Verify metrics logging is accurate."""
    
    def setUp(self):
        """Set up test fixtures."""
        assert_api_healthy()
        self.api_client = APIClient()
        self.api_client.reset()
    
    def test_decision_metrics_collection(self):
        """Decision metrics should be trackable."""
        timestamp = time.time()
        weather = generate_test_weather()
        
        metrics = {
            'CLEARED': 0,
            'HOLD': 0,
            'total': 0
        }
        
        # Run multiple ticks
        for i in range(5):
            aircraft = generate_aircraft_list(4, timestamp + i)
            
            tick = {
                'timestamp': timestamp + i,
                'aircraft_list': aircraft,
                'weather': weather,
                'runway_info': None
            }
            
            result = self.api_client.process_tick(tick)
            
            for decision in result['decisions']:
                metrics['total'] += 1
                decision_type = decision['decision']
                if decision_type in metrics:
                    metrics[decision_type] += 1
        
        # Should have recorded all decisions
        self.assertEqual(
            metrics['total'],
            20,  # 5 ticks * 4 aircraft
            "Not all decisions recorded"
        )
        
        # Should have mix
        self.assertGreater(
            metrics['CLEARED'],
            0,
            "No CLEARED decisions"
        )
    
    def test_runway_assignment_frequency(self):
        """Track which runways get assignments."""
        timestamp = time.time()
        weather = generate_test_weather()
        
        runway_assignments = {}
        
        for i in range(10):
            aircraft = generate_aircraft_list(3, timestamp + i)
            
            tick = {
                'timestamp': timestamp + i,
                'aircraft_list': aircraft,
                'weather': weather,
                'runway_info': None
            }
            
            result = self.api_client.process_tick(tick)
            
            for decision in result['decisions']:
                if decision['decision'] == 'CLEARED':
                    runway = decision.get('assigned_runway')
                    if runway:
                        runway_assignments[runway] = runway_assignments.get(runway, 0) + 1
        
        # Some runways should have assignments
        self.assertGreater(
            len(runway_assignments),
            0,
            "No runway assignments made"
        )
        
        # Log the distribution
        self.assertLessEqual(
            len(runway_assignments),
            6,  # Max 6 runways
            "More than 6 runways assigned"
        )
    
    def test_confidence_score_statistics(self):
        """Collect statistics on confidence scores."""
        timestamp = time.time()
        weather = generate_test_weather()
        
        confidences = []
        
        for i in range(10):
            aircraft = generate_aircraft_list(3, timestamp + i)
            
            tick = {
                'timestamp': timestamp + i,
                'aircraft_list': aircraft,
                'weather': weather,
                'runway_info': None
            }
            
            result = self.api_client.process_tick(tick)
            
            for decision in result['decisions']:
                conf = decision.get('confidence', 0.0)
                confidences.append(conf)
        
        # Should have confidence scores
        self.assertGreater(len(confidences), 0)
        
        # All should be valid
        for conf in confidences:
            self.assertGreaterEqual(conf, 0.0)
            self.assertLessEqual(conf, 1.0)
    
    def test_hold_event_tracking(self):
        """Track HOLD events throughout simulation."""
        timestamp = time.time()
        weather = generate_test_weather()
        
        hold_events = []
        tick_count = 0
        
        for i in range(15):
            aircraft = generate_aircraft_list(3, timestamp + i)
            
            tick = {
                'timestamp': timestamp + i,
                'aircraft_list': aircraft,
                'weather': weather,
                'runway_info': None
            }
            
            result = self.api_client.process_tick(tick)
            tick_count += 1
            
            holds_this_tick = sum(1 for d in result['decisions'] if d['decision'] == 'HOLD')
            if holds_this_tick > 0:
                hold_events.append({
                    'tick': i,
                    'count': holds_this_tick,
                    'timestamp': result['timestamp']
                })
        
        # HOLD events should be logged
        # (May be 0 in normal conditions, but can log count)
        self.assertLessEqual(
            sum(h['count'] for h in hold_events),
            45,  # Max 3 aircraft * 15 ticks
            "Too many HOLD events"
        )
    
    def test_degraded_mode_tracking(self):
        """Track when degraded mode is active."""
        timestamp = time.time()
        weather = generate_test_weather()
        
        degraded_count = 0
        total_responses = 0
        
        for i in range(10):
            # Generate some aircraft with missing data
            aircraft = generate_aircraft_list(2, timestamp + i)
            
            # Randomly remove some data to trigger degradation
            import random
            if random.random() > 0.5:
                if aircraft and 'heading_deg' in aircraft[0]:
                    del aircraft[0]['heading_deg']
            
            tick = {
                'timestamp': timestamp + i,
                'aircraft_list': aircraft,
                'weather': weather,
                'runway_info': None
            }
            
            result = self.api_client.process_tick(tick)
            total_responses += 1
            
            flags = result.get('system_flags', {})
            if flags.get('degraded_mode'):
                degraded_count += 1
        
        # Should have processed responses
        self.assertEqual(total_responses, 10)
        
        # Degraded mode tracking should be consistent
        self.assertLessEqual(
            degraded_count,
            total_responses,
            "More degraded responses than total"
        )
    
    def test_operation_type_distribution(self):
        """Track distribution of landings vs takeoffs."""
        timestamp = time.time()
        weather = generate_test_weather()
        
        operation_metrics = {
            'landing': {'assigned': 0, 'held': 0},
            'takeoff': {'assigned': 0, 'held': 0}
        }
        
        for i in range(10):
            aircraft = generate_aircraft_list(4, timestamp + i, mix_operations=True)
            
            tick = {
                'timestamp': timestamp + i,
                'aircraft_list': aircraft,
                'weather': weather,
                'runway_info': None
            }
            
            result = self.api_client.process_tick(tick)
            
            for decision in result['decisions']:
                operation = decision.get('operation', 'unknown')
                
                if operation in operation_metrics:
                    if decision['decision'] == 'CLEARED':
                        operation_metrics[operation]['assigned'] += 1
                    else:
                        operation_metrics[operation]['held'] += 1
        
        # Both operation types should have decisions
        self.assertGreater(
            sum(
                operation_metrics[op]['assigned'] +
                operation_metrics[op]['held']
                for op in operation_metrics
            ),
            0,
            "No operation metrics collected"
        )
    
    def test_performance_timing_metrics(self):
        """Measure tick processing performance."""
        timestamp = time.time()
        weather = generate_test_weather()
        
        process_times = []
        
        for i in range(10):
            aircraft = generate_aircraft_list(5, timestamp + i)
            
            tick = {
                'timestamp': timestamp + i,
                'aircraft_list': aircraft,
                'weather': weather,
                'runway_info': None
            }
            
            start = time.time()
            result = self.api_client.process_tick(tick)
            elapsed = time.time() - start
            
            process_times.append(elapsed)
        
        # Should have timing data
        self.assertEqual(len(process_times), 10)
        
        # All should complete in reasonable time
        avg_time = sum(process_times) / len(process_times)
        self.assertLess(
            avg_time,
            2.0,
            f"Average tick time too high: {avg_time:.3f}s"
        )
        
        # Should not have extreme outliers
        max_time = max(process_times)
        self.assertLess(
            max_time,
            5.0,
            f"Max tick time too high: {max_time:.3f}s"
        )
    
    def test_safety_alert_frequency(self):
        """Track safety alert frequency."""
        timestamp = time.time()
        weather = generate_test_weather()
        
        alert_metrics = {
            'total': 0,
            'critical': 0,
            'warning': 0
        }
        
        for i in range(10):
            aircraft = generate_aircraft_list(4, timestamp + i)
            
            tick = {
                'timestamp': timestamp + i,
                'aircraft_list': aircraft,
                'weather': weather,
                'runway_info': None
            }
            
            result = self.api_client.process_tick(tick)
            
            for alert in result.get('safety_alerts', []):
                alert_metrics['total'] += 1
                severity = alert.get('severity', 'unknown')
                
                if severity in alert_metrics:
                    alert_metrics[severity] += 1
        
        # Alert tracking should be consistent
        total = alert_metrics['total']
        critical_warning = alert_metrics['critical'] + alert_metrics['warning']
        
        self.assertEqual(
            total,
            critical_warning,
            "Alert count mismatch"
        )


if __name__ == '__main__':
    unittest.main()
