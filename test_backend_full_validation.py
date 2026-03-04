"""
test_backend_full_validation.py
Master validation script that runs all test suites and reports results
"""
import sys
import os
import unittest
from pathlib import Path
from datetime import datetime
import json

# Add paths
TEST_DIR = Path(__file__).parent / "tests"
ROOT_DIR = Path(__file__).parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "tests"))
sys.path.insert(0, str(ROOT_DIR / "scripts"))
sys.path.insert(0, str(ROOT_DIR / "api"))

# Import all test modules
from tests.test_engine_determinism import TestEngineDeterminism
from tests.test_state_persistence import TestStatePersistence
from tests.test_api_parity import TestAPIClIParity
from tests.test_concurrency import TestConcurrency
from tests.test_reset_behavior import TestResetBehavior
from tests.test_logging import TestLoggingIntegrity
from tests.test_model_stability import TestModelStability
from tests.test_adversarial import TestAdversarialInputHandling
from tests.test_stress import TestStressMode
from tests.test_metrics import TestMetricsLogging


class TestSuiteRunner:
    """Run all test suites and collect results."""
    
    def __init__(self):
        self.results = {}
        self.start_time = None
        self.end_time = None
    
    def run_test_suite(self, test_class, suite_name):
        """Run a single test suite and return results."""
        print(f"\n{'='*70}")
        print(f"Running: {suite_name}")
        print(f"{'='*70}")
        
        # Create test suite
        loader = unittest.TestLoader()
        suite = loader.loadTestsFromTestCase(test_class)
        
        # Run tests
        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(suite)
        
        # Store results
        passed = result.testsRun - len(result.failures) - len(result.errors)
        self.results[suite_name] = {
            'status': 'PASS' if result.wasSuccessful() else 'FAIL',
            'tests_run': result.testsRun,
            'passed': passed,
            'failed': len(result.failures),
            'errors': len(result.errors),
            'success': result.wasSuccessful()
        }
        
        return result.wasSuccessful()
    
    def run_all_tests(self):
        """Run all test suites."""
        print("\n")
        print("╔" + "="*68 + "╗")
        print("║" + " "*15 + "ATC-ASSIST BACKEND VALIDATION SUITE" + " "*19 + "║")
        print("╚" + "="*68 + "╝")
        print(f"\nStarted: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        self.start_time = datetime.now()
        
        test_suites = [
            (TestEngineDeterminism, "Engine Determinism"),
            (TestStatePersistence, "State Persistence"),
            (TestAPIClIParity, "API/CLI Parity"),
            (TestConcurrency, "Concurrency Integrity"),
            (TestResetBehavior, "Reset Behavior"),
            (TestLoggingIntegrity, "Logging Integrity"),
            (TestModelStability, "Model Load Stability"),
            (TestAdversarialInputHandling, "Adversarial Input Handling"),
            (TestStressMode, "Stress Mode"),
            (TestMetricsLogging, "Metrics Logging"),
        ]
        
        all_passed = True
        for test_class, suite_name in test_suites:
            try:
                passed = self.run_test_suite(test_class, suite_name)
                if not passed:
                    all_passed = False
            except Exception as e:
                print(f"\n❌ EXCEPTION in {suite_name}: {e}")
                self.results[suite_name] = {
                    'status': 'ERROR',
                    'error': str(e)
                }
                all_passed = False
        
        self.end_time = datetime.now()
        return all_passed
    
    def print_summary(self):
        """Print test summary."""
        print("\n")
        print("╔" + "="*68 + "╗")
        print("║" + " "*20 + "VALIDATION SUMMARY" + " "*30 + "║")
        print("╚" + "="*68 + "╝\n")
        
        test_order = [
            "Engine Determinism",
            "State Persistence",
            "API/CLI Parity",
            "Concurrency Integrity",
            "Reset Behavior",
            "Logging Integrity",
            "Model Load Stability",
            "Adversarial Input Handling",
            "Stress Mode",
            "Metrics Logging",
        ]
        
        passed_count = 0
        total_count = 0
        
        for suite_name in test_order:
            if suite_name in self.results:
                result = self.results[suite_name]
                status = result['status']
                
                total_count += 1
                
                if status == 'PASS':
                    passed_count += 1
                    symbol = "✓"
                    status_str = "PASS"
                else:
                    symbol = "✗"
                    status_str = "FAIL"
                
                if 'tests_run' in result:
                    details = f" ({result['passed']}/{result['tests_run']} tests)"
                else:
                    details = " (error during execution)"
                
                print(f"  [{symbol}] {suite_name:<50}{status_str}{details}")
        
        print("\n" + "="*70)
        
        if passed_count == total_count:
            print(f"\n✓ All {total_count} test suites PASSED!")
            print(f"\n  Backend Validation: {passed_count}/{total_count} PASSED")
        else:
            print(f"\n✗ {total_count - passed_count} test suite(s) FAILED")
            print(f"\n  Backend Validation: {passed_count}/{total_count} PASSED")
        
        print("\n" + "="*70)
        
        # Timing
        if self.start_time and self.end_time:
            elapsed = (self.end_time - self.start_time).total_seconds()
            print(f"\nCompleted: {self.end_time.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"Duration:  {elapsed:.2f} seconds")
        
        print("\n")
        
        return passed_count == total_count
    
    def save_results_json(self, output_file="validation_results.json"):
        """Save results to JSON file."""
        output_path = ROOT_DIR / output_file
        
        data = {
            'timestamp': self.start_time.isoformat() if self.start_time else None,
            'duration_seconds': (self.end_time - self.start_time).total_seconds() if self.start_time and self.end_time else None,
            'results': self.results,
            'summary': {
                'total_suites': len(self.results),
                'passed_suites': sum(1 for r in self.results.values() if r.get('status') == 'PASS'),
                'failed_suites': sum(1 for r in self.results.values() if r.get('status') == 'FAIL'),
            }
        }
        
        with open(output_path, 'w') as f:
            json.dump(data, f, indent=2)
        
        print(f"Results saved to: {output_path}")


def main():
    """Main entry point."""
    runner = TestSuiteRunner()
    
    # Run all tests
    all_passed = runner.run_all_tests()
    
    # Print summary
    summary_passed = runner.print_summary()
    
    # Save results
    try:
        runner.save_results_json()
    except Exception as e:
        print(f"Warning: Could not save results JSON: {e}")
    
    # Exit with appropriate code
    if all_passed and summary_passed:
        print("\n✓ VALIDATION COMPLETE: Backend is production-safe for frontend integration\n")
        sys.exit(0)
    else:
        print("\n✗ VALIDATION FAILED: Fix issues before proceeding\n")
        sys.exit(1)


if __name__ == '__main__':
    main()
