
import os
import sys
import subprocess
import time
import logging
import traceback
from datetime import datetime

# Ensure scripts directory is in sys.path for imports
scripts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scripts')
if scripts_dir not in sys.path:
    sys.path.insert(0, scripts_dir)

# Setup logging
LOG_PATH = os.path.join('logs', 'final_test.log')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s',
    handlers=[
        logging.FileHandler(LOG_PATH, mode='w'),
        logging.StreamHandler(sys.stdout)
    ]
)


def log(msg):
    # Remove Unicode emoji for Windows console compatibility
    msg = msg.replace('✅', '[PASS]').replace('❌', '[FAIL]')
    logging.info(msg)

# Activate virtual environment (Windows CMD-compatible)
def activate_venv():
    venv_activate = os.path.join('venv', 'Scripts', 'activate.bat')
    if os.path.exists(venv_activate):
        try:
            subprocess.call([venv_activate], shell=True)
            log('Virtual environment activated.')
        except Exception as e:
            log(f'Failed to activate venv: {e}')
    else:
        log('venv activation script not found. Skipping activation.')

activate_venv()

# SIMULATION TEST
def simulation_test():
    try:
        from scripts.runner import SimulationRunner
        log('Starting simulation mode (debug=True)...')
        sim_duration = 35  # seconds
        runner = SimulationRunner(mode="simulation", debug=True)
        # run_interactive prints to console, so capture tick count from runner
        runner.run_interactive(duration_sec=sim_duration, tick_interval=1.0)
        log(f'SIMULATION PASS [PASS] | Total ticks: {runner.tick_count}')
        return True
    except Exception as e:
        log(f'SIMULATION FAIL [FAIL]: {e}\n{traceback.format_exc()}')
        return False

# ASSISTANT TEST
def assistant_test():
    try:
        from scripts.runner import SimulationRunner
        log('Starting assistant mode (debug=False)...')
        assist_duration = 10  # seconds
        runner = SimulationRunner(mode="assistant", debug=False)
        # There is no explicit runway state check, so just run and log
        runner.run_interactive(duration_sec=assist_duration, tick_interval=1.0)
        log('ASSISTANT PASS [PASS] | Assistant mode ran without error.')
        return True
    except Exception as e:
        log(f'ASSISTANT FAIL [FAIL]: {e}\n{traceback.format_exc()}')
        return False

# EVALUATION TEST
def evaluation_test():
    try:
        from scripts.evaluate import ATC_Evaluator
        log('Running evaluation on logs/ml_sample.csv...')
        evaluator = ATC_Evaluator(debug=False)
        eval_result = evaluator.evaluate_file('logs/ml_sample.csv')
        accuracy = eval_result.get('accuracy', 0)
        rejected_holds = eval_result.get('rejected_decisions', 0)
        mean_conf = eval_result.get('mean_confidence', 0)
        summary = (f'EVAL SUMMARY: Accuracy={accuracy:.2%}, Rejected HOLDs={rejected_holds}, ' 
                   f'Mean Confidence={mean_conf:.3f}')
        log(summary)
        if accuracy > 0.8:
            log('EVALUATION PASS [PASS]')
            return True
        else:
            log('EVALUATION FAIL [FAIL] | Accuracy below threshold.')
            return False
    except Exception as e:
        log(f'EVALUATION FAIL [FAIL]: {e}\n{traceback.format_exc()}')
        return False

if __name__ == '__main__':
    log(f'--- FINAL TEST STARTED ({datetime.now().strftime("%Y-%m-%d %H:%M:%S")}) ---')
    sim_ok = simulation_test()
    assist_ok = assistant_test()
    eval_ok = evaluation_test()
    log(f'--- FINAL TEST COMPLETE ---')
    log(f'Logs saved to {LOG_PATH}')
    print(f'Logs saved to {LOG_PATH}')
    if all([sim_ok, assist_ok, eval_ok]):
        print('ALL TESTS PASSED ✅')
    else:
        print('Some tests failed ❌. See log for details.')
