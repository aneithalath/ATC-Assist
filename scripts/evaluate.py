"""
evaluate.py
Evaluation script - compare AI predictions against true labels
"""
import json
import argparse
import sys
from pathlib import Path
from typing import Dict, List
import numpy as np

from controller_engine import ControllerEngine
import pandas as pd
from sklearn.metrics import confusion_matrix, accuracy_score


class ATC_Evaluator:
    """Evaluate ATC engine performance."""
    
    def __init__(self, debug: bool = False):
        """Initialize evaluator."""
        self.debug = debug
        self.engine = ControllerEngine(
            models_dir="models",
            logs_dir="logs",
            debug=False,  # No debug spam during eval
            mode="simulation"  # Allow runway state mutation
        )
    
    def evaluate_file(self, csv_file: str) -> Dict:
        """
        Evaluate engine against labeled data in CSV.
        """
        print(f"\n{'='*70}")
        print(f"ATC Engine Evaluation")
        print(f"{'='*70}\n")

        predictions = []
        ground_truth = []
        confidences = []
        rejected_count = 0
        degraded_count = 0
        timestamps = []

        try:
            df = pd.read_csv(csv_file)
            print(f"✓ Loaded {len(df)} rows from {csv_file}")
        except Exception as e:
            print(f"✗ Error loading {csv_file}: {e}")
            return {}

        # Iterate over each row and run inference

        for idx, row in df.iterrows():
            # Extract timestamp
            timestamp = row.get('timestamp', None)
            timestamps.append(timestamp)

            # Build aircraft state dict
            ac_data = row.to_dict()

            # Inject default lat/lon (PHX tower) if missing
            if 'lat' not in ac_data or ac_data['lat'] is None:
                ac_data['lat'] = 33.435298
            if 'lon' not in ac_data or ac_data['lon'] is None:
                ac_data['lon'] = -112.005895

            # Map altitude_agl_ft to altitude_ft (MSL) for PHX
            if 'altitude_agl_ft' in ac_data:
                ac_data['altitude_ft'] = ac_data['altitude_agl_ft'] + 1083

            # True label
            true_runway = ac_data.get('runway')

            # Run inference
            result = self.engine.process_tick(
                timestamp=float(timestamp) if timestamp is not None else 0.0,
                aircraft_list=[ac_data],
                weather=None,
                runway_info=None
            )
            decisions = result.get('decisions', [])
            system_flags = result.get('system_flags', {})

            # Only one aircraft per tick
            if decisions:
                dec = decisions[0]
                # Debug print for each row
                print(f"Row {idx}: decision={dec['decision']}, runway={dec.get('assigned_runway')}, confidence={dec.get('confidence')}, reason={dec.get('reason')}")
                if dec['decision'] == 'HOLD':
                    rejected_count += 1
                else:
                    predictions.append(dec['assigned_runway'])
                    ground_truth.append(true_runway)
                    confidences.append(dec['confidence'])

                if system_flags.get('degraded_mode', False):
                    degraded_count += 1
            else:
                print(f"Row {idx}: No decision generated")
                rejected_count += 1

        # Calculate metrics
        if predictions:

            # Filter ground truth to only match cleared predictions
            cleared_ground_truth = [
                gt for gt, pred in zip(ground_truth, 
                [p if p is not None else None for p in predictions])
            ]

            accuracy = accuracy_score(cleared_ground_truth, predictions)

            runway_ids = sorted(df['runway'].dropna().unique())
            conf_matrix = confusion_matrix(
                cleared_ground_truth,
                predictions,
                labels=runway_ids
            )

            results = {
                'accuracy': float(accuracy),
                'total_evaluated': len(predictions),
                'rejected_decisions': rejected_count,
                'rejection_rate': rejected_count / (rejected_count + len(predictions)) if (rejected_count + len(predictions)) > 0 else 0,
                'degraded_ticks': degraded_count,
                'degradation_rate': degraded_count / len(timestamps) if len(timestamps) > 0 else 0,
                'mean_confidence': float(np.mean(confidences)) if confidences else 0.0,
                'min_confidence': float(np.min(confidences)) if confidences else 0.0,
                'max_confidence': float(np.max(confidences)) if confidences else 0.0,
                'confusion_matrix': conf_matrix.tolist(),
                'runway_ids': runway_ids
            }


            # Print results
            print(f"\n{'='*70}")
            print(f"Evaluation Results")
            print(f"{'='*70}\n")
            print(f"✓ Total Samples: {len(predictions)}")
            print(f"✓ Accuracy: {accuracy*100:.2f}%")
            print(f"✓ Rejected (HOLD): {rejected_count} ({results['rejection_rate']*100:.1f}%)")
            print(f"✓ Degraded Mode Ticks: {degraded_count} ({results['degradation_rate']*100:.1f}%)")
            print(f"✓ Mean Confidence: {results['mean_confidence']:.4f}")
            print(f"✓ Confidence Range: [{results['min_confidence']:.4f}, {results['max_confidence']:.4f}]\n")

            # Print confusion matrix
            print("Confusion Matrix:")
            print("           " + "  ".join(f"{r:>6}" for r in runway_ids))

            for i, runway in enumerate(runway_ids):
                row_label = f"{runway:>8} "
                row_vals = "  ".join(f"{conf_matrix[i, j]:>6}" for j in range(len(runway_ids)))
                print(f"{row_label} {row_vals}")

            print(f"\n{'='*70}\n")

            return results
        else:
            print("✗ No valid predictions generated")
            return {}
    
    def save_results(self, results: Dict, output_file: str = "logs/evaluation_results.json"):
        """Save evaluation results to JSON."""
        output_path = Path(output_file)
        with open(output_path, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        print(f"✓ Results saved to {output_file}\n")


def main():
    """Main evaluation entry point."""
    parser = argparse.ArgumentParser(
        description='Evaluate ATC Engine Performance'
    )
    parser.add_argument(
        '--input',
        type=str,
        default='logs/ml_sample.csv',
        help='Input CSV file with features and true labels'
    )
    parser.add_argument(
        '--output',
        type=str,
        default='logs/evaluation_results.json',
        help='Output file for results'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug output'
    )
    
    args = parser.parse_args()
    
    try:
        # Check if input file exists
        if not Path(args.input).exists():
            print(f"✗ Input file not found: {args.input}")
            print(f"  Available: logs/feature.csv or logs/ml_sample.csv")
            return 1
        
        evaluator = ATC_Evaluator(debug=args.debug)
        results = evaluator.evaluate_file(args.input)
        
        if results:
            evaluator.save_results(results, args.output)
            return 0
        else:
            return 1
    
    except Exception as e:
        print(f"✗ Error: {e}", file=sys.stderr)
        if args.debug:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
