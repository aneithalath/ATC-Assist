"""
runner.py
CLI entry point for running the ATC engine in simulation or assistant mode
"""
import json
import argparse
import sys
import time
import math
from pathlib import Path
from typing import Optional, List, Dict

from controller_engine import ControllerEngine


class SimulationRunner:
    """Runner for the ATC simulation."""
    
    def __init__(self, mode: str = "simulation", debug: bool = False):
        """Initialize runner."""
        self.mode = mode
        self.debug = debug
        
        # Initialize engine
        self.engine = ControllerEngine(
            models_dir="models",
            logs_dir="logs",
            debug=debug,
            mode=mode
        )
        
        self.tick_count = 0
        self.start_time = None
    
    def run_interactive(self, duration_sec: int = 60, tick_interval: float = 1.0):
        """Run interactive simulation."""
        print(f"\n{'='*70}")
        print(f"ATC Engine Runtime - {self.mode.upper()} Mode")
        print(f"{'='*70}\n")
        
        # Use real current time as simulation start
        self.start_time = time.time()
        sim_time = self.start_time
        end_time = self.start_time + duration_sec
        
        print(f"Running for {duration_sec} seconds (tick every {tick_interval}s, debug={self.debug})")
        print(f"Press Ctrl+C to stop\n")
        
        try:
            while sim_time <= end_time:
                # Simulate aircraft data
                aircraft = self._generate_test_aircraft(sim_time)
                weather = self._generate_test_weather()
                # Process tick
                result = self.engine.process_tick(
                    timestamp=sim_time,
                    aircraft_list=aircraft,
                    weather=weather
                )
                # Output result
                self._print_tick_result(result)
                self.tick_count += 1
                sim_time += tick_interval
                # Sleep to maintain real-time pace
                time.sleep(tick_interval)
        
        except KeyboardInterrupt:
            print("\n\nSimulation interrupted by user")
        
        # Save logs
        self.engine.save_logs()
        elapsed = time.time() - self.start_time
        
        print(f"\n{'='*70}")
        print(f"Simulation Complete")
        print(f"Ticks processed: {self.tick_count}")
        print(f"Elapsed: {elapsed:.2f}s")
        print(f"Logs saved to: logs/atc_runtime.json")
        print(f"{'='*70}\n")
    
    def run_batch(self, data_file: str, output_file: str = "decisions.json"):
        """Run batch processing from CSV file."""
        print(f"\n{'='*70}")
        print(f"ATC Engine - Batch Mode ({self.mode.upper()})")
        print(f"{'='*70}\n")
        
        import pandas as pd
        
        # Load data
        if not Path(data_file).exists():
            print(f"ERROR: Data file not found: {data_file}")
            return False
        
        try:
            df = pd.read_csv(data_file)
            print(f"Loaded {len(df)} rows from {data_file}")
        except Exception as e:
            print(f"ERROR loading data: {e}")
            return False
        
        # Group by timestamp
        if 'timestamp' not in df.columns:
            print("ERROR: 'timestamp' column required in data")
            return False
        
        all_decisions = []
        timestamps = sorted(df['timestamp'].unique())
        
        for ts in timestamps:
            # Get aircraft at this timestamp
            ts_data = df[df['timestamp'] == ts]
            aircraft = []
            
            for _, row in ts_data.iterrows():
                ac = {
                    'aircraft_id': row.get('aircraft_id', row.get('id', f'AC{_}')),
                    'lat': row.get('lat'),
                    'lon': row.get('lon'),
                    'altitude_ft': row.get('altitude_ft', row.get('altitude_agl_ft', 5000)),
                    'ground_speed_knots': row.get('ground_speed_knots', 200),
                    'heading_deg': row.get('heading_deg'),
                    'vertical_rate_fpm': row.get('vertical_rate_fpm'),
                    'aircraft_category': row.get('aircraft_category', 'M'),
                    'operation': row.get('operation', 'landing'),
                    'distance_to_tower_nm': row.get('distance_to_tower_nm'),
                    'runway_alignment_error': row.get('runway_alignment_error', 0),
                    'field_elevation_ft': 1083,
                    'timestamp': ts
                }
                aircraft.append(ac)
            
            # Process
            result = self.engine.process_tick(
                timestamp=ts,
                aircraft_list=aircraft,
                weather=None
            )
            
            all_decisions.append(result)
            
            if self.debug or (len(all_decisions) % 10 == 0):
                print(f"Processed {len(all_decisions)} ticks...")
        
        # Save results
        output_path = Path(output_file)
        with open(output_path, 'w') as f:
            json.dump(all_decisions, f, indent=2, default=str)
        
        self.engine.save_logs()
        
        print(f"\n{'='*70}")
        print(f"Batch processing complete")
        print(f"Ticks processed: {len(all_decisions)}")
        print(f"Decisions saved to: {output_file}")
        print(f"Logs saved to: logs/atc_runtime.json")
        print(f"{'='*70}\n")
        
        return True
    
    def _generate_test_aircraft(self, sim_time: float) -> List[Dict]:
        """Generate synthetic aircraft for demonstration."""
        import math
        
        import random
        aircraft = []
        # Aircraft 1: Descending approach (Heavy Jet)
        alt1 = max(0, 10000 - sim_time * 200)
        dist1 = max(1, 30 - sim_time * 0.5)
        lat1 = 33.435298 + (dist1 / 60)
        lon1 = -112.005895 + (dist1 / 80)
        aircraft.append({
            'aircraft_id': 'AAL123',
            'lat': lat1,
            'lon': lon1,
            'altitude_ft': alt1,
            'ground_speed_knots': 150 - (alt1 / 100),
            'heading_deg': 260.0,
            'vertical_rate_fpm': -300 if alt1 > 1000 else 0,
            'aircraft_category': 'heavy_jet',  # Correct for one-hot
            'operation': 'landing',
            'runway_alignment_error': 5.0,
            'field_elevation_ft': 1083,
            'timestamp': sim_time
        })
        # Aircraft 2: Climbing departure (Medium Jet)
        alt2 = min(35000, 1000 + sim_time * 300)
        aircraft.append({
            'aircraft_id': 'SWA456',
            'lat': 33.435298 - 0.1,
            'lon': -112.005895,
            'altitude_ft': alt2,
            'ground_speed_knots': 80 + (alt2 / 100),
            'heading_deg': 80.0,
            'vertical_rate_fpm': 1500 if alt2 < 10000 else 500,
            'aircraft_category': 'medium_jet',  # Correct for one-hot
            'operation': 'takeoff',
            'runway_alignment_error': 0.0,
            'field_elevation_ft': 1083,
            'timestamp': sim_time
        })
        # Occasional third aircraft (Light Prop)
        if int(sim_time) % 10 == 0 and sim_time > 5:
            alt3 = 5000
            aircraft.append({
                'aircraft_id': f'N{int(sim_time)}AB',
                'lat': 33.435298,
                'lon': -112.005895 - 0.05,
                'altitude_ft': alt3,
                'ground_speed_knots': 120,
                'heading_deg': 170.0,
                'vertical_rate_fpm': -200,
                'aircraft_category': 'light_prop',  # Correct for one-hot
                'operation': 'landing',
                'runway_alignment_error': 8.0,
                'field_elevation_ft': 1083,
                'timestamp': sim_time
            })
        return aircraft
    
    def _generate_test_weather(self) -> Dict:
        """Generate synthetic but realistic weather, including wind components."""
        import random
        # Random wind direction (0-359 deg) and speed (0-20 knots)
        wind_direction = random.uniform(0, 359)
        wind_speed = random.uniform(0, 20)
        # Assume runway heading 260 (PHX west flow) for wind component calculation
        runway_heading = 260.0
        # Use same logic as FeatureBuilder for wind components
        def wind_along(wind_speed, wind_dir, runway_heading):
            relative = (wind_dir - runway_heading) % 360
            return wind_speed * math.cos(math.radians(relative))
        def wind_cross(wind_speed, wind_dir, runway_heading):
            relative = (wind_dir - runway_heading) % 360
            return wind_speed * math.sin(math.radians(relative))
        return {
            'tmpf': random.uniform(80, 110),
            'relh': random.uniform(10, 60),
            'drct': wind_direction,
            'sknt': wind_speed,
            'wind_speed': wind_speed,
            'wind_direction': wind_direction,
            'wind_along_runway': wind_along(wind_speed, wind_direction, runway_heading),
            'wind_cross_runway': wind_cross(wind_speed, wind_direction, runway_heading)
        }
    
    def _print_tick_result(self, result: Dict):
        """Pretty-print tick result."""
        if not self.debug:
            return
        
        tick = result['timestamp']
        decisions = result['decisions']
        alerts = result['safety_alerts']
        
        print(f"\n[Tick {tick}] {result['datetime']}")
        print(f"  Decisions: {len(decisions)}")
        
        for dec in decisions[:5]:  # Show first 5
            ac = dec.get('aircraft_id', 'UNKNOWN')
            decision = dec.get('decision', 'UNKNOWN')
            runway = dec.get('assigned_runway', '-')
            conf = dec.get('confidence', 0)
            print(f"    {ac:15} → {str(decision):10} {str(runway):5} (conf={conf:.3f})")
        
        if alerts:
            print(f"  ⚠ Safety Alerts: {len(alerts)}")
            for alert in alerts[:3]:
                print(f"    {alert['aircraft_id']}: {alert['violation_type']}")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description='ATC Engine Runtime'
    )
    parser.add_argument(
        '--mode',
        choices=['simulation', 'assistant'],
        default='simulation',
        help='Operating mode'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug output'
    )
    parser.add_argument(
        '--duration',
        type=int,
        default=60,
        help='Simulation duration (seconds)'
    )
    parser.add_argument(
        '--batch',
        type=str,
        help='Run batch mode from CSV file'
    )
    parser.add_argument(
        '--output',
        type=str,
        default='decisions.json',
        help='Output file for batch results'
    )
    
    args = parser.parse_args()
    
    try:
        runner = SimulationRunner(mode=args.mode, debug=args.debug)
        
        if args.batch:
            # Batch mode
            runner.run_batch(args.batch, args.output)
        else:
            # Interactive mode
            runner.run_interactive(duration_sec=args.duration)
    
    except Exception as e:
        print(f"\nERROR: {e}", file=sys.stderr)
        if args.debug:
            import traceback
            traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
