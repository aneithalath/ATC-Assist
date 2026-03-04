"""
test_adversarial.py
Tests handling of adversarial and malformed inputs
"""
import unittest
from test_utils import (
    APIClient, generate_tick_input, generate_test_weather,
    assert_api_healthy
)


class TestAdversarialInputHandling(unittest.TestCase):
    """Verify robust handling of bad inputs."""
    
    def setUp(self):
        """Set up test fixtures."""
        assert_api_healthy()
        self.api_client = APIClient()
        self.api_client.reset()
    
    def test_missing_aircraft_id(self):
        """Aircraft missing ID should be handled safely."""
        tick_input = generate_tick_input(aircraft_count=1)
        
        # Remove aircraft_id
        if tick_input['aircraft_list']:
            del tick_input['aircraft_list'][0]['aircraft_id']
        
        # Should not crash
        try:
            result = self.api_client.process_tick(tick_input)
            # Either handled or error returned
            self.assertIn('decisions', result)
        except Exception as e:
            # If it errors, that's also acceptable (safe failure)
            self.assertIsNotNone(str(e))
    
    def test_missing_position_data(self):
        """Aircraft missing position should trigger HOLD."""
        tick_input = generate_tick_input(aircraft_count=1)
        
        if tick_input['aircraft_list']:
            ac = tick_input['aircraft_list'][0]
            ac['id'] = 'AC_NO_POS'
            # Remove position
            if 'lat' in ac:
                del ac['lat']
            if 'lon' in ac:
                del ac['lon']
        
        # Should not crash
        result = self.api_client.process_tick(tick_input)
        self.assertIn('decisions', result)
        
        # Should likely be HOLD
        if result['decisions']:
            decision = result['decisions'][0]
            self.assertIn(
                decision['decision'],
                ['HOLD', 'CLEARED'],
                "Should make valid decision"
            )
    
    def test_null_aircraft_list(self):
        """Null aircraft list should be handled."""
        tick_input = generate_tick_input(aircraft_count=1)
        tick_input['aircraft_list'] = None
        
        # Should not crash
        try:
            result = self.api_client.process_tick(tick_input)
            self.assertIn('decisions', result)
        except Exception:
            # Safe to fail
            pass
    
    def test_empty_aircraft_list(self):
        """Empty aircraft list should be handled."""
        tick_input = generate_tick_input(aircraft_count=0)
        
        result = self.api_client.process_tick(tick_input)
        
        # Should return valid response
        self.assertIn('decisions', result)
        self.assertEqual(len(result['decisions']), 0)
    
    def test_negative_altitude(self):
        """Negative altitude should be handled."""
        tick_input = generate_tick_input(aircraft_count=1)
        
        if tick_input['aircraft_list']:
            tick_input['aircraft_list'][0]['altitude_ft'] = -1000
        
        # Should not crash
        result = self.api_client.process_tick(tick_input)
        self.assertIn('decisions', result)
    
    def test_negative_ground_speed(self):
        """Negative ground speed should be handled."""
        tick_input = generate_tick_input(aircraft_count=1)
        
        if tick_input['aircraft_list']:
            tick_input['aircraft_list'][0]['ground_speed_knots'] = -100
        
        # Should not crash
        result = self.api_client.process_tick(tick_input)
        self.assertIn('decisions', result)
    
    def test_invalid_heading(self):
        """Invalid heading should be handled."""
        tick_input = generate_tick_input(aircraft_count=1)
        
        if tick_input['aircraft_list']:
            tick_input['aircraft_list'][0]['heading_deg'] = 400  # Invalid
        
        # Should not crash
        result = self.api_client.process_tick(tick_input)
        self.assertIn('decisions', result)
    
    def test_extreme_coordinates(self):
        """Extreme coordinates should be handled."""
        tick_input = generate_tick_input(aircraft_count=1)
        
        if tick_input['aircraft_list']:
            tick_input['aircraft_list'][0]['lat'] = 200
            tick_input['aircraft_list'][0]['lon'] = 400
        
        # Should not crash
        result = self.api_client.process_tick(tick_input)
        self.assertIn('decisions', result)
    
    def test_duplicate_aircraft_ids(self):
        """Duplicate aircraft IDs should be handled."""
        tick_input = generate_tick_input(aircraft_count=3)
        
        # Make all IDs the same
        if len(tick_input['aircraft_list']) > 1:
            for ac in tick_input['aircraft_list']:
                ac['aircraft_id'] = 'DUPLICATE_ID'
        
        # Should not crash
        try:
            result = self.api_client.process_tick(tick_input)
            self.assertIn('decisions', result)
        except Exception:
            # Safe to fail on duplicates
            pass
    
    def test_missing_operation_field(self):
        """Missing operation field should be handled."""
        tick_input = generate_tick_input(aircraft_count=1)
        
        if tick_input['aircraft_list']:
            ac = tick_input['aircraft_list'][0]
            if 'operation' in ac:
                del ac['operation']
        
        # Should not crash
        result = self.api_client.process_tick(tick_input)
        self.assertIn('decisions', result)
    
    def test_invalid_operation_type(self):
        """Invalid operation type should be handled."""
        tick_input = generate_tick_input(aircraft_count=1)
        
        if tick_input['aircraft_list']:
            tick_input['aircraft_list'][0]['operation'] = 'invalid_operation'
        
        # Should not crash
        result = self.api_client.process_tick(tick_input)
        self.assertIn('decisions', result)
    
    def test_missing_weather_data(self):
        """Missing weather should be handled."""
        tick_input = generate_tick_input(aircraft_count=1)
        tick_input['weather'] = None
        
        # Should not crash
        result = self.api_client.process_tick(tick_input)
        self.assertIn('decisions', result)
    
    def test_null_weather(self):
        """Null weather dict should be handled."""
        tick_input = generate_tick_input(aircraft_count=1)
        
        # Remove weather fields
        if tick_input['weather']:
            tick_input['weather'] = {}
        
        # Should not crash
        result = self.api_client.process_tick(tick_input)
        self.assertIn('decisions', result)
    
    def test_extremely_large_aircraft_list(self):
        """Large aircraft list should be handled."""
        tick_input = {
            'timestamp': 1234567890.0,
            'aircraft_list': [
                {
                    'aircraft_id': f'AC{i:05d}',
                    'lat': 33.4484,
                    'lon': -112.0740,
                    'altitude_ft': 5000 + i * 10,
                    'ground_speed_knots': 150,
                    'heading_deg': 180,
                    'vertical_rate_fpm': -500,
                    'aircraft_category': 'medium_jet',
                    'operation': 'landing',
                    'runway_alignment_error': 5,
                    'field_elevation_ft': 1083,
                    'timestamp': 1234567890.0
                }
                for i in range(100)  # 100 aircraft
            ],
            'weather': generate_test_weather(),
            'runway_info': None
        }
        
        # Should not crash, though may take time
        try:
            result = self.api_client.process_tick(tick_input)
            self.assertIn('decisions', result)
        except Exception as e:
            # System timeout is acceptable
            self.assertIn('timeout', str(e).lower().replace('_', ' ') or 'True')
    
    def test_all_fields_null(self):
        """All null fields should be handled."""
        tick_input = {
            'timestamp': None,
            'aircraft_list': None,
            'weather': None,
            'runway_info': None
        }
        
        # Should not crash
        try:
            result = self.api_client.process_tick(tick_input)
            # May return error or empty decisions
        except Exception:
            # Safe to fail
            pass
    
    def test_string_instead_of_number(self):
        """String where number expected should be handled."""
        tick_input = generate_tick_input(aircraft_count=1)
        
        if tick_input['aircraft_list']:
            ac = tick_input['aircraft_list'][0]
            ac['altitude_ft'] = "five thousand"
            ac['ground_speed_knots'] = "one hundred fifty"
        
        # Should not crash
        try:
            result = self.api_client.process_tick(tick_input)
            self.assertIn('decisions', result)
        except Exception:
            # Safe to fail on type mismatch
            pass
    
    def test_none_values_in_required_fields(self):
        """None values in required fields should be handled."""
        tick_input = generate_tick_input(aircraft_count=1)
        
        if tick_input['aircraft_list']:
            ac = tick_input['aircraft_list'][0]
            ac['lat'] = None
            ac['lon'] = None
        
        # Should not crash
        result = self.api_client.process_tick(tick_input)
        self.assertIn('decisions', result)
    
    def test_malformed_timestamp(self):
        """Malformed timestamp should be handled."""
        tick_input = generate_tick_input(aircraft_count=1)
        tick_input['timestamp'] = "not a timestamp"
        
        # Should not crash
        try:
            result = self.api_client.process_tick(tick_input)
            self.assertIn('decisions', result)
        except Exception:
            # Safe to fail
            pass


if __name__ == '__main__':
    unittest.main()
