# 🧪 Complete End-to-End Testing Guide

This is exactly what you do. **Nothing more, nothing less.**

---

## ⏱️ Total Time: ~10 minutes (1 min + 30 sec + 3 min + 2 min + 5 min + 1 min review)

---

## **STEP 1: Basic System Verification** (1 minute)

### Exact Command:
```bash
python verify_system.py
```

### What You Should See:
```
Files:
  [OK] Model               models/phx_local_controller.pt
  [OK] Config              models/feature_config.json
  [OK] Runways             models/runway_label_map.json
  [OK] Runner              scripts/runner.py
  ... (8 more files all [OK]) ...

Configuration:
  [OK] Features configured: 30
  [OK] Runways: 6 - 07L, 07R, 25L, 25R...
  [OK] Confidence threshold: 0.6
  [OK] Missing value medians: 30 features

✓ SYSTEM READY - All components present!
```

### What to verify:
- ✅ All files show `[OK]` (no `[MISSING]`)
- ✅ Features: `30` (not 27 or 31)
- ✅ Runways: `6`
- ✅ Confidence threshold: `0.6`

**If PASS → Go to STEP 2**  
**If FAIL → Stop. Check that retraining completed successfully.**

---

## **STEP 2: Check Configuration Matches Model** (30 seconds)

### Exact Command:
```bash
python -c "import json; c=json.load(open('models/feature_config.json')); r=json.load(open('models/runway_label_map.json')); o=json.load(open('models/feature_order.json')); print(f'Features: {len(c[\"feature_cols\"])}'); print(f'Runways: {len(r)}'); print(f'Feature order matches: {c[\"feature_cols\"] == o[\"feature_cols\"]}'); print(f'Aircraft cats: {len([x for x in c[\"feature_cols\"] if x.startswith(\"ac_cat_\")])}'); print(f'Missing flags: {len([x for x in c[\"feature_cols\"] if x.endswith(\"_missing\")])}'); print('✓ All configs aligned')"
```

### What You Should See:
```
Features: 30
Runways: 6
Feature order matches: True
Aircraft cats: 6
Missing flags: 9
✓ All configs aligned
```

### What to verify:
- ✅ Features: `30`
- ✅ Runways: `6`
- ✅ Feature order matches: `True`
- ✅ Aircraft categories: `6` (heavy_jet, light_prop, medium_jet, regional_jet, turboprop, unknown)
- ✅ Missing flags: `9`

**If PASS → Go to STEP 3**  
**If FAIL → Retraining didn't complete properly. Run `python scripts/train_controller.py` again.**

---

## **STEP 3: Test Simulation** (3 minutes)

**What it does:** Runs AI controller for 10 seconds, shows real-time decisions.

### Exact Command:
```bash
python scripts/runner.py --mode simulation --duration 10 --debug
```

### What You Should See:
```
======================================================================
ATC Engine Runtime - SIMULATION Mode
======================================================================

[OK] ControllerEngine initialized (mode=simulation, device=cpu)
[OK] Model loaded with 6 runways

====== Tick 0 ======
Decisions: 2
    AC023          → CLEARED    07L   (conf=0.894)
    AC045          → HOLD       25R   (conf=0.412)

[DEBUG] inference: runway_id=07L, confidence=0.894

====== Tick 1 ======
Decisions: 1
    AC089          → CLEARED    26    (conf=0.756)

... [repeated for 10 ticks] ...

======================================================================
Simulation Complete
Ticks processed: 11
Elapsed: 11.23s
Logs saved to: logs/atc_runtime.json
```

### What to verify for EACH tick:
- ✅ Timestamp printed
- ✅ `Decisions: N` (N = number of aircraft)
- ✅ Each aircraft has decision: **CLEARED** or **HOLD** (only these two)
- ✅ Runway is one of: **07L, 07R, 25L, 25R, 26, 8**
- ✅ Confidence is between **0.0 and 1.0**

### For the whole run:
- ✅ Model initializes with "6 runways"
- ✅ At least 10 ticks process (duration = 10)
- ✅ No crashes or errors
- ✅ Logs saved message appears at end

**If PASS → Go to STEP 4**  
**If FAIL → Check error message. Most common: model dimension mismatch (run training again).**

---

## **STEP 4: Test Assistant Mode** (2 minutes)

**What it does:** Same as simulation but AI only advises (doesn't change runway state).

### Exact Command:
```bash
python scripts/runner.py --mode assistant --duration 5 --debug
```

### What You Should See:
```
ATC Engine Runtime - ASSISTANT Mode
======================================================================

[similar output as simulation]

Simulation Complete
Ticks processed: 6
Elapsed: 6.15s
Logs saved to: logs/atc_runtime.json
```

### What to verify:
- ✅ Mode shows **ASSISTANT** (not SIMULATION)
- ✅ Same decision format as Step 3
- ✅ Runs for ~5 seconds
- ✅ No state mutations (each tick is independent)

**If PASS → Go to STEP 5**  
**If FAIL → Check error message.**

---

## **STEP 5: Evaluation Test** (5 minutes)

**What it does:** Runs AI on 50 real labeled data points. Compares AI predictions to true runways.

### Exact Command:
```bash
python scripts/evaluate.py --input logs/ml_sample.csv --debug
```

### What You Should See:
```
======================================================================
ATC Engine Evaluation
======================================================================

✓ Loaded 50 rows from logs\ml_sample.csv
✓ Processing 47 unique timestamps

  ✓ ad61de    pred=26     true=8      conf=0.3950
  ✓ a114f4    pred=07R    true=07R   conf=0.8234
  ✗ ab4383    pred=25L    true=07L   conf=0.5612
  ... [first 10 samples shown] ...

======================================================================
Evaluation Results
======================================================================

✓ Total Samples: 45
✓ Accuracy: 73.33%
✓ Rejected (HOLD): 5 (10.0%)
✓ Degraded Mode Ticks: 2 (4.3%)
✓ Mean Confidence: 0.7234
✓ Confidence Range: [0.1520, 0.9850]

Confusion Matrix:
           07L    07R    25L    25R     26      8
07L         8      1      0      0      0      0
07R         0      7      1      0      0      0
25L         0      1      5      0      0      0
25R         0      0      0      6      0      0
26          0      0      0      0      4      0
8           0      0      0      0      0      3

======================================================================

✓ Results saved to evaluation_results.json
```

### What to verify:

**Data loading:**
- ✅ Loaded **50 rows**
- ✅ Processing **47 timestamps**

**Accuracy metrics:**
- ✅ Total Samples: **≥40** (valid predictions)
- ✅ Accuracy: **≥60%** (70%+ is good, 50-70% acceptable, <50% poor)
- ✅ Rejected (HOLD): **<20%** (how many decisions were not made)
- ✅ Mean Confidence: **>0.5** (0.7+ is good)
- ✅ Confidence Range: Has min and max values

**Confusion Matrix:**
- ✅ Shows **6×6 grid** (6 runways)
- ✅ Diagonal (correct predictions) is **higher than off-diagonal**
- ✅ No NaN or infinity values

### **Expected Accuracy Ranges:**

| Accuracy | What It Means |
|----------|--------------|
| **>80%** | Excellent - model is very well trained |
| **70-80%** | Good - model works well |
| **60-70%** | Acceptable - model is functional |
| **50-60%** | Marginal - model needs improvement |
| **<50%** | Poor - retraining needed |

**If PASS (accuracy ≥60%) → Go to STEP 6**  
**If FAIL (accuracy <50%) → This is OK for first test. Retraining with more data will help.**

---

## **STEP 6: Review Results** (1 minute)

### Check What Was Logged in Simulation:

```bash
python -c "import json; events=json.load(open('logs/atc_runtime.json')); types=set(e.get('event_type') for e in events); print(f'Total events: {len(events)}'); print(f'Event types: {types}')"
```

Expected:
```
Total events: 100+
Event types: {'inference', 'decision', 'clearance_issued', 'runway_states', ...}
```

### View Evaluation Results:

```bash
type evaluation_results.json
```

You should see a JSON file with all metrics.

---

## 🎯 WHAT EACH TEST TELLS YOU

| Step | Tests | Success Means |
|------|-------|--------------|
| 1 | Files exist | System installed correctly |
| 2 | Config alignment | Model + runtime are synchronized |
| 3 | Simulation | AI makes decisions in real-time |
| 4 | Assistant mode | AI gives recommendations safely |
| 5 | Evaluation | AI generalizes to unseen data |
| 6 | Logging | All outputs are recorded |

**If all 6 pass → Your system is fully operational and accurate.**

---

## 🚨 COMMON ISSUES & FIXES

### Issue: "Model not found"
```
FileNotFoundError: models/phx_local_controller.pt
```
**Fix:** Run `python scripts/train_controller.py`

### Issue: "27 features, expected 30"
```
ValueError: Feature mismatch
```
**Fix:** Retrain - training added new aircraft categories.

### Issue: "Feature order mismatch"
```
ValueError: Feature order mismatch!
```
**Fix:** Retrain model - feature order from training differs from runtime.

### Issue: Accuracy is 33% (random guessing)
- Model outputs same runway each time
- Training failed to converge
- **Fix:** Retrain with `USE_CACHED_FEATURES = True` to use existing feature data

### Issue: "No valid predictions generated"
- All decisions were HOLD (model had low confidence)
- **Not a failure** - system is being conservative
- **Fix:** Verify data quality or lower confidence threshold

---

## ✅ WHAT SUCCESS LOOKS LIKE

After all 6 steps:

1. ✅ `verify_system.py` shows all files present
2. ✅ Configs match: 30 features, 6 runways
3. ✅ Simulation runs without errors, makes decisions
4. ✅ Assistant mode runs without state changes
5. ✅ Evaluation shows accuracy ≥60%
6. ✅ Results logged to `logs/atc_runtime.json` and `evaluation_results.json`

**This means your AI system is trained, configured, and operational.**
