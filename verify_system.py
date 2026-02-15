#!/usr/bin/env python
"""
System verification script - checks all components are ready
"""
import json
from pathlib import Path
import sys

def verify_system():
    """Verify all system components are in place."""
    print("=== ATC Engine System Verification ===\n")
    
    # File checks
    files_to_check = {
        'Model': 'models/phx_local_controller.pt',
        'Config': 'models/feature_config.json',
        'Runways': 'models/runway_label_map.json',
        'Runner': 'scripts/runner.py',
        'Engine': 'scripts/controller_engine.py',
        'Feature Builder': 'scripts/feature_builder.py',
        'Runway Manager': 'scripts/runway_manager.py',
        'Safety Validator': 'scripts/safety_validator.py',
        'State Tracker': 'scripts/state_tracker.py',
        'Logger': 'scripts/runtime_logger.py',
        'Evaluate': 'scripts/evaluate.py',
    }
    
    print("Files:\n")
    all_present = True
    for name, path in files_to_check.items():
        exists = Path(path).exists()
        status = "[OK]" if exists else "[MISSING]"
        print(f"  {status} {name:20} {path}")
        all_present = all_present and exists
    
    # Config checks
    print("\nConfiguration:\n")
    try:
        with open('models/feature_config.json') as f:
            config = json.load(f)
        
        features = len(config.get('feature_cols', []))
        runways = config.get('runway_ids', [])
        threshold = config.get('confidence_threshold', 0)
        medians_count = len(config.get('medians', {}))
        
        print(f"  [OK] Features configured: {features}")
        print(f"  [OK] Runways: {len(runways)} - {', '.join(runways[:3])}...")
        print(f"  [OK] Confidence threshold: {threshold}")
        print(f"  [OK] Missing value medians: {medians_count} features")
        
    except Exception as e:
        print(f"  [ERROR] Config error: {e}")
        all_present = False
    
    # Data checks
    print("\nData Files:\n")
    if Path('logs/ml_sample.csv').exists():
        print("  [OK] ML sample available for evaluation")
    if Path('logs/feature.csv').exists():
        print("  [OK] Feature dump available for training")
    
    # Summary
    print("\n" + "="*50)
    if all_present:
        print("✓ SYSTEM READY - All components present!\n")
        print("Quick start commands:")
        print("  python scripts/runner.py --mode simulation --duration 10 --debug")
        print("  python scripts/runner.py --mode assistant")
        print("  python scripts/evaluate.py --input logs/ml_sample.csv")
        return 0
    else:
        print("✗ SYSTEM INCOMPLETE - Missing components\n")
        return 1

if __name__ == "__main__":
    sys.exit(verify_system())
