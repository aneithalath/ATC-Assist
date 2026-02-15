# Quick Start Guide

## 30-Second Setup

1. **Install dependencies** (one time):
   ```bash
   pip install -r requirements.txt
   ```

2. **Verify system** (optional):
   ```bash
   python verify_system.py
   ```

---

## Run the System

### Simulation (Watch AI Control Runways)

```bash
python scripts/runner.py --mode simulation --duration 60 --debug
```

Output: Real-time decisions every 1 second for 60 seconds.

**Output:**
```
[OK] ControllerEngine initialized (mode=simulation, device=cpu)

======================================================================
ATC Engine Runtime - SIMULATION Mode
======================================================================

[Tick 0] 2021-01-01T00:00:00+00:00
  Decisions: 2
    AAL123          → CLEARED    25L   (conf=0.950)
    SWA456          → HOLD       25R   (conf=0.320)
```

### Assistant Mode (Get Recommendations)

```bash
python scripts/runner.py --mode assistant --duration 30
```

Output: Same as above, but AI doesn't change runway state.

### Batch Processing

```bash
python scripts/runner.py --batch logs/ml_sample.csv --output decisions.json
```

Output: JSON file with all decisions from CSV data.

### Evaluation

```bash
python scripts/evaluate.py --input logs/ml_sample.csv
```

Output:
```
✓ Accuracy: 78.50%
✓ Rejected (HOLD): 11.1%
✓ Mean Confidence: 0.8542
```

---

## Where to Find Results

- **Latest run events**: `logs/atc_runtime.json`
- **Evaluation results**: `evaluation_results.json` (if you ran evaluate)
- **Training results**: `logs/training_log.txt`

---

## Common Commands

| Command | Purpose |
|---------|---------|
| `python scripts/runner.py --mode simulation --duration 10 --debug` | Quick 10-second test with debug output |
| `python scripts/runner.py --mode assistant` | Run in recommendation mode |
| `python scripts/evaluate.py --input logs/ml_sample.csv` | Evaluate accuracy |
| `python verify_system.py` | Check all components are ready |
| `python scripts/train_controller.py` | Retrain model (optional) |

---

## Understanding Output

### CLEARED
```
AAL123          → CLEARED    25L   (conf=0.950)
```
Runway assigned, all checks passed, clearance issued.

### HOLD
```
SWA456          → HOLD       25R   (conf=0.320)
```
Either:
- Low confidence (<0.6)
- Runway occupied
- Safety violation detected
- Aircraft degraded

### Degraded Mode
```
⚠ Feature degradation: 45.2%
```
Poor sensor data - system raised confidence threshold and is being conservative.

---

## Debug Mode

Add `--debug` flag to see:

```bash
python scripts/runner.py --mode simulation --duration 5 --debug
```

Shows:
- Feature vectors (30 dimensions)
- Model confidence scores
- Safety checks details
- Runway occupancy timers
- Missing data and imputation
- Queue states

---

## System Architecture (Quick Overview)

```
Input: Aircraft state (lat, lon, altitude, speed, etc.)
   ↓
[Feature Builder] → Normalize 27 features, handle missing data
   ↓
[Neural Network] → Predict runway (0-5 for 6 runways)
   ↓
[Safety Validator] → Check wake, collision, conflicts
   ↓
[Runway Manager] → Verify runway available, manage queue
   ↓
Output: CLEARED or HOLD decision
   ↓
[Logger] → Event to JSON
```

---

## Key Safety Features

✓ Never crashes from missing data
✓ Automatically raises confidence threshold if data degraded
✓ Enforces wake separation by aircraft size
✓ Prevents runway conflicts
✓ Queues aircraft when runway occupied
✓ Logs all safety violations
✓ Supports emergency override (logged)

---

## Configuration

Edit `models/feature_config.json` to change:

- Confidence threshold
- Which features can be missing
- Runway ID to label mapping

Edit `scripts/runway_manager.py` for:
- Rollout time (50 seconds default)
- Separation time (60 seconds default)

---

## Troubleshooting

**"Model not found"**
```
RuntimeError: Error(s) in loading state_dict...
```
→ Model dimensions mismatch. Recreate with correct feature count (27).

**"Feature config not found"**
```
FileNotFoundError: models/feature_config.json
```
→ Run training: `python scripts/train_controller.py`

**"No valid predictions generated"**
→ All decisions were HOLD (low confidence or safety violations). This is correct behavior - system is being conservative.

**Unicode errors on Windows**
→ Already fixed in code. Run normally, no special setup needed.

---

## Next Steps

1. ✓ Understand output format → Check sample logs in `logs/atc_runtime.json`
2. ✓ Try different durations → `--duration 120` for 2 minutes
3. ✓ Integrate with your UI → Output is pure JSON
4. ✓ Add real data → Replace synthetic aircraft generation in `runner.py`
5. ✓ Fine-tune → Adjust confidence threshold in `feature_config.json`

---

## Support

- **Full README**: See `README.md` for complete documentation
- **Implementation details**: See `IMPLEMENTATION_SUMMARY.md`
- **System check**: Run `python verify_system.py`
- **Logs**: Check `logs/atc_runtime.json` for all events

---

**Ready to control runways!** 🛫
