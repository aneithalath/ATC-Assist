# ATC Assist - AI Air Traffic Control Engine

A fully runnable AI-powered Air Traffic Control runtime engine for Phoenix Sky Harbor International Airport (PHX).

## Features

- **Real-time Inference**: Runway assignment decisions every 1 second
- **Dual Operating Modes**:
  - **Simulation Mode**: AI updates and manages runway state
  - **Assistant Mode**: AI provides recommendations without state mutation
- **Safety-First Design**:
  - Runway occupancy management with dynamic locking
  - Wake turbulence separation enforcement
  - Collision risk detection
  - Safety violation logging and alerts
- **Robust Handling of Missing Data**:
  - Automatic feature imputation with training medians
  - Degradation tracking and threshold adjustment
  - Never crashes due to missing sensor data
- **Structured JSON Output**: All decisions and events logged as structured JSON
- **Debuggable**: Rich debug mode with feature vectors, confidence scores, and queue states
- **Evaluatable**: Compare AI predictions against ground truth labels

## System Architecture

### Core Components

- **`controller_engine.py`**: Main inference orchestrator
- **`feature_builder.py`**: Constructs normalized feature vectors for inference
- **`runway_manager.py`**: Manages runway states, occupancy, and queuing
- **`safety_validator.py`**: Enforces safety constraints and rules
- **`state_tracker.py`**: Tracks aircraft and runway state during operation
- **`runtime_logger.py`**: Structured event logging to JSON
- **`runner.py`**: CLI entry point for simulation/batch/assistant modes
- **`evaluate.py`**: Performance evaluation against labeled data

### Model & Configuration

- **`models/phx_local_controller.pt`**: Trained PyTorch neural network (30 inputs → 6 outputs)
- **`models/feature_config.json`**: Feature definitions, medians, and runway mappings
- **`models/runway_label_map.json`**: Runway ID to label index mapping

### Data

- **`logs/atc_runtime.json`**: Structured event log from latest run
- **`logs/feature.csv`**: Training feature data (if available)
- **`logs/ml_sample.csv`**: Small sample for evaluation

## Quick Start

### Setup

1. **Install dependencies** (from project root):
   ```bash
   pip install -r requirements.txt
   ```

2. **Activate virtual environment** (optional but recommended):
   ```bash
   venv\Scripts\activate   # Windows
   source venv/bin/activate  # Linux/Mac
   ```

### Running the System

#### Simulation Mode
Run interactive simulation with synthetic aircraft data:
```bash
python scripts/runner.py --mode simulation --duration 60 --debug
```

**Options:**
- `--duration 60`: Run for 60 seconds of simulation time (default: 60)
- `--debug`: Print detailed per-tick information
- `--mode simulation`: Controller updates runway state (default)

#### Assistant Mode
Run in recommendation-only mode (no state mutation):
```bash
python scripts/runner.py --mode assistant --duration 30
```

#### Batch Mode
Process data from CSV file:
```bash
python scripts/runner.py --batch logs/ml_sample.csv --output decisions.json
```

**CSV Format Required:**
- `timestamp`: Unix seconds
- `aircraft_id`: Unique identifier
- `lat`, `lon`: Position in degrees
- `altitude_ft`: Altitude in feet
- `ground_speed_knots`: Ground speed
- `operation`: 'landing' or 'takeoff'
- Additional optional: heading_deg, vertical_rate_fpm, aircraft_category, etc.

### Evaluation

Evaluate inference accuracy against true runway labels:
```bash
python scripts/evaluate.py --input logs/ml_sample.csv --output eval_results.json
```

**CSV Format For Evaluation:**
- All features from batch mode PLUS
- `runway`: True assigned runway (label for evaluation)

Output includes:
- Accuracy percentage
- Confusion matrix
- Rejection rate (HOLD decisions)
- Degradation statistics

## System Behavior

### Decision Logic

For each aircraft per tick:

1. **Feature Construction**: Build normalized feature vector
2. **Degradation Check**: If >30% features missing, raise confidence threshold
3. **Inference**: Neural network predicts runway
4. **Safety Validation**: Check wake separation, collisions, runway conflicts
5. **Runway Occupancy**: Verify runway is not occupied
6. **Queue Management**: Add to landing/takeoff queue if occupied
7. **Decision**:
   - ✓ **CLEARED**: Runway available, safety passed → issue clearance
   - 🟡 **HOLD**: Uncertain confidence, safety violation, or occupied → wait
   - 🔴 **DEGRADED**: Feature quality poor → use degraded mode

### Runway Management

- **Locked by default**: Prevents accidental operations
- **Can be unlocked**: Controller must authorize operation
- **Occupancy timing**:
  - **Landing**: Occupied for 50 seconds (rollout time)
  - **Takeoff**: Occupied for 60 seconds (separation time)
- **Emergency override**: Allows clearance on locked runway (logged)

### Safety Rules

- **Wake Separation**: Based on aircraft category
  - Heavy → Light: 8 minutes
  - Medium → Light: 5 minutes
  - etc.
- **Time Separation**: 2 minutes minimum between same-type operations
- **No Mixed Operations**: No landing while takeoff in progress
- **Collision Detection**: <1nm horizontal + <500ft vertical = critical

### Missing Data Handling

| Data | Action |
|------|--------|
| Missing: lat, lon, timestamp | Drop tick (cannot process) |
| Missing: heading, vertical_rate, wind, weather | Impute with training median (from feature_config.json) + add _missing flag |
| Missing: altitude, category, or operation | Fallback to 0.0, log as degraded |
| >30% features missing | Raise confidence threshold, log degraded mode |
| NaN detected | Replace with 0.0, log error |

## Output Format

### Structured Decision Output

```json
{
  "timestamp": 1609459200,
  "datetime": "2021-01-01T00:00:00+00:00",
  "mode": "simulation",
  "decisions": [
    {
      "aircraft_id": "AAL123",
      "decision": "CLEARED",
      "assigned_runway": "25L",
      "operation": "landing",
      "confidence": 0.95,
      "reason": "Runway available, safety checks passed"
    }
  ],
  "runway_states": {
    "25L": {
      "occupied": true,
      "occupancy_remaining_sec": 45.5,
      "current_operation": "landing",
      "landing_queue_count": 2,
      "takeoff_queue_count": 0,
      "locked": false,
      "emergency_override": false
    }
  },
  "safety_alerts": [
    {
      "aircraft_id": "SWA456",
      "violation_type": "wake_separation",
      "severity": "warning",
      "message": "Insufficient wake separation..."
    }
  ],
  "system_flags": {
    "degraded_mode": false
  }
}
```

## Debug Mode

Enable with `--debug` flag to see:

```
[OK] ControllerEngine initialized (mode=simulation, device=cpu)
[OK] Model loaded with 6 runways

[Tick 0] 2021-01-01T00:00:00+00:00
  Decisions: 2
    AAL123          → CLEARED    25L   (conf=0.950)
    SWA456          → HOLD       25R   (conf=0.320)

[WARNING] missing_data: aircraft_id=AAL123, missing=['heading_deg'], imputed=['wind_along_runway']
[DEBUG] inference: aircraft_id=AAL123, confidence=0.950, predicted_runway=25L
[WARNING] safety_violation: aircraft_id=SWA456, violation_type=wake_separation
```

## File Structure

```
/ATC-Assist
  /scripts
    controller_engine.py      # Main inference orchestrator
    feature_builder.py        # Feature vector construction
    runway_manager.py         # Runway state management
    safety_validator.py       # Safety constraint enforcement
    state_tracker.py          # Aircraft/runway tracking
    runtime_logger.py         # Structured logging
    runner.py                 # CLI entry point
    evaluate.py               # Performance evaluation
    train_controller.py       # Training pipeline (generates config)
    trace_processor.py        # Historical trace processing
    runways.py                # PHX runway definitions
  /models
    phx_local_controller.pt   # Trained neural network
    feature_config.json       # Feature definitions & medians
    runway_label_map.json     # Runway ID mapping
  /logs
    atc_runtime.json          # Latest run event log
    feature.csv               # Training features (if available)
    ml_sample.csv             # Evaluation sample
    training_log.txt          # Training run log
  /operations_data
    operations*.csv           # Historical operation data
  /weather_data
    kphx_weather_filtered.csv # Historical weather
  requirements.txt            # Python dependencies
  README.md                   # This file
```

## Configuration

Edit `feature_config.json` to tune system behavior:

```json
{
  "confidence_threshold": 0.6,  // Default confidence required for clearance
  "allow_missing": [...],        // Features that can be safely imputed
  "critical_columns": [...]      // Features that must not be missing
}
```

Edit runway occupancy in `runway_manager.py`:

```python
rollout_time_sec: int = 50      # Landing rollout duration
separation_time_sec: int = 60   # Minimum time between operations
```

## Monitoring & Safety

### Safety Guarantees

The system **NEVER**:
- ✓ Issues clearance on occupied runway
- ✓ Allows wake violation
- ✓ Allows runway conflict  
- ✓ Crashes from missing data
- ✓ Mutates state in assistant mode
- ✓ Produces NaN features

### Default Behavior When Uncertain

→ **HOLD** (defer decision)

### Confidence Threshold

- **Default**: 0.6 (60%)
- **Degraded Mode**: 1.5x multiplier (0.9 minimum)

### Logs

All events logged to structured JSON:

```bash
tail -f logs/atc_runtime.json
```

Event types:
- `inference`: Model output details
- `decision`: Runway assignment
- `clearance_issued`: Clearance given
- `safety_violation`: Safety rule violation
- `missing_data`: Imputation record
- `degraded_mode_active`: Feature quality poor
- `runway_states`: Runway occupancy snapshot

## Training (Optional)

To retrain the model:

```bash
python scripts/train_controller.py
```

This will:
1. Load historical operations data
2. Process traces from OpenSky/archives
3. Generate feature vectors
4. Train neural network
5. **Export `feature_config.json`** ← used by runtime
6. Save model to `/models/phx_local_controller.pt`

## Performance

- **Inference latency**: <100ms per tick (CPU)
- **Memory**: ~50MB (model + features loaded once at startup)
- **No redundant I/O**: Config/model loaded once at startup, feature_order.json validated for alignment
- **Parallelizable**: Per-aircraft processing is independent

## Future Enhancements

- [ ] Web UI integration for visualization
- [ ] Real OpenSky API data integration
- [ ] Multi-airport support
- [ ] Reinforcement learning fine-tuning
- [ ] Historical replay for backtesting

## License

Proprietary - Arizona Department of Aviation

## Support

For issues or questions:
1. Check logs: `logs/atc_runtime.json`
2. Run with `--debug` flag
3. Review evaluation results: `evaluation_results.json`
