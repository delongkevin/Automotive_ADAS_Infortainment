# MIL (Model-in-the-Loop) Testing Framework

## Overview

The MIL Testing Framework provides comprehensive, scenario-based testing for all ADAS features in the ADAS SIL System. It enables validation of ADAS algorithms under realistic driving scenarios with performance metrics collection and reporting.

## Architecture

## Core Components

```text
MIL Testing Framework
├── core/mil_testing.py           # Framework implementation
├── scenarios/*.json               # Test scenario definitions (7 scenarios)
├── tests/test_mil.py             # Pytest-based MIL test suite
└── run_mil_tests.py              # Standalone test runner script
```text

## Framework Structure

```text
MILScenarioRunner
├── Scenario Loading
├── Feature Initialization
├── Event Processing
│   ├── Validation Events
│   ├── Feature Commands
│   ├── Vehicle Motion
│   └── Environment Setup
├── Metrics Collection
└── Result Analysis
    ├── Performance Metrics
    ├── Validation Results
    └── Report Generation
```text

## Test Scenarios

## 1. Blind Spot Detection (blind_spot_detection.json)

**Purpose:** Validate blind spot detection with vehicles approaching from multiple angles

**Duration:** 30 seconds

**Test Cases:**

- Vehicle approaching from left blind spot

- Vehicle approaching from right blind spot  

- Vehicle approaching from rear blind spot

- Warning activation/deactivation validation

**Success Criteria:**

- All validations pass

- Minimum accuracy: 95%

- Maximum latency: 100ms

## 2. Autonomous Parking - Parallel (autonomous_parking_parallel.json)

**Purpose:** Test parallel parking space detection and execution

**Duration:** 45 seconds

**Test Cases:**

- Parking space detection during forward drive

- Parking initiation

- Maneuver progression validation

- Completion verification

**Success Criteria:**

- Space detection accuracy >= 90%

- Progression from 0% to 100%

- Maximum latency: 150ms

## 3. Autonomous Parking - Perpendicular (autonomous_parking_perpendicular.json)  

**Purpose:** Test perpendicular parking maneuver

**Duration:** 50 seconds

**Test Cases:**

- Perpendicular space setup and detection

- Parking type validation (perpendicular vs parallel)

- Progressive maneuver execution

- Completion check

**Success Criteria:**

- Accurate space type detection

- Smooth progression through parking stages

- Maximum latency: 150ms

## 4. Trailer Assistance (trailer_assistance.json)

**Purpose:** Validate trailer detection and steering correction with PID control

**Duration:** 40 seconds

**Test Cases:**

- Trailer detection from sensor data

- Steering angle response

- PID correction validation

- Angle recovery after correction

**Success Criteria:**

- Trailer detected consistently

- Steering correction activated appropriately

- Angle control within tolerance

- Minimum accuracy: 92%

- Maximum latency: 80ms

## 5. Surround View Camera (surround_view_camera.json)

**Purpose:** Test all 9 camera view modes and auto-switching logic

**Duration:** 60 seconds

**Test Cases:**

- Front view (initial state)

- Rear view (reverse gear)

- Cargo view (parked)

- Side views (sharp turns)

- Bird's eye view (low speed parking)

- View transition smoothness

**Success Criteria:**

- Correct view selection for all conditions

- Accurate auto-switching logic

- Transition completeness

- Minimum accuracy: 98%

- Maximum latency: 50ms

## 6. Highway Cruise (highway_cruise.json)

**Purpose:** Test ACC in highway conditions

**Duration:** Variable

## 7. Emergency Braking (emergency_braking.json)

**Purpose:** Test AEB system response

**Duration:** Variable

## Usage

## Running All MIL Tests via Python Script

```bash
## Run complete MIL test suite
python run_mil_tests.py

## Run with custom output path
python run_mil_tests.py --output my_report.txt

## Run specific scenario
python run_mil_tests.py --scenario blind_spot_detection

## Verbose output
python run_mil_tests.py --verbose
```text

## Running Tests via Pytest

```bash
## Run all MIL tests
pytest ADAS_SIL_System/tests/test_mil.py -v

## Run specific test class
pytest ADAS_SIL_System/tests/test_mil.py::TestBlindSpotDetection -v

## Run with output
pytest ADAS_SIL_System/tests/test_mil.py -v --tb=short

## Generate JUnit report
pytest ADAS_SIL_System/tests/test_mil.py -v --junit-xml=mil_results.xml
```text

## Integration with CI/CD

The MIL test suite can be integrated into CI/CD pipelines:

```yaml
## Example GitHub Actions workflow

- name: Run MIL Tests

  run: |
    python -m pytest ADAS_SIL_System/tests/test_mil.py -v \
      --junit-xml=mil_results.xml \
      --cov=ADAS_SIL_System \
      --cov-report=xml
```text

## Scenario Definition Format

## Example Scenario Structure

```json
{
  "name": "Feature Test Scenario",
  "description": "Detailed description",
  "duration": 30.0,
  "environment": {
    "weather": "clear",
    "road_type": "highway",
    "visibility": 300.0
  },
  "vehicle_config": {
    "initial_speed": 25.0,
    "initial_position": [0.0, -1.8],
    "enabled_features": ["feature_name"]
  },
  "events": [
    {
      "name": "Event description",
      "time": 2.0,
      "type": "validation|feature_command|vehicle_motion|environment_setup",
      "parameters": {}
    }
  ],
  "success_criteria": {
    "all_validations_pass": true,
    "min_accuracy": 0.95,
    "max_latency_ms": 100
  }
}
```text

## Event Types

## # # 1. Validation Events

Checks feature behavior against expected values:

```json
{
  "type": "validation",
  "parameters": {
    "feature": "bsd",
    "check_field": "left_occupied",
    "expected": true,
    "tolerance": 0.0
  }
}
```text

Validation operators:

- `expected`: Exact value match

- `expected_min`: Minimum threshold

- `expected_max_abs`: Maximum absolute value

- `expected_min_abs`: Minimum absolute value

## # # 2. Feature Commands

Enable/disable or configure features:

```json
{
  "type": "feature_command",
  "parameters": {
    "feature": "parking",
    "command": "start_parking"
  }
}
```text

Available commands:

- `enable`: Activate feature

- `disable`: Deactivate feature

- `set_guidance_mode`: Configure guidance parameters

- Custom feature-specific commands

## # # 3. Vehicle Motion

Simulate vehicle movements:

```json
{
  "type": "vehicle_motion",
  "parameters": {
    "speed_target": 15.0,
    "steering_angle": 0.3,
    "duration": 5.0,
    "gear": "D"
  }
}
```text

## # # 4. Environment Setup

Configure environment conditions:

```json
{
  "type": "environment_setup",
  "parameters": {
    "parking_space_type": "parallel",
    "position": [15.0, 0.0],
    "length": 6.0,
    "width": 2.5
  }
}
```text

## Metrics Collection

## PerformanceMetrics

Each feature's performance is tracked across multiple dimensions:

```python
@dataclass
class PerformanceMetrics:
    feature_name: str
    test_name: str
    
    # Execution metrics
    duration_ms: float                  # Total test duration
    step_count: int                     # Simulation steps executed
    avg_step_time_ms: float            # Average step duration
    max_step_time_ms: float            # Maximum step duration
    min_step_time_ms: float            # Minimum step duration
    
    # Validation metrics
    validations_passed: int             # Count of passed validations
    validations_failed: int             # Count of failed validations
    validation_accuracy: float          # Pass rate percentage
    
    # Latency metrics
    max_latency_ms: float              # Maximum feature latency
    avg_latency_ms: float              # Average feature latency
    
    # Result
    passed: bool                        # Test passed/failed
    failure_reason: str                 # Reason for failure if any
```text

## Validation Results

Individual validation checks are tracked:

```python
@dataclass
class ValidationResult:
    name: str              # Validation name
    time: float            # Simulation time when check occurred
    passed: bool           # Result
    expected: Any          # Expected value
    actual: Any            # Actual value
    error_msg: str         # Error message if failed
    latency_ms: float      # Latency to complete check
```text

## Reports

## Report Contents

The MIL test report includes:

```text
MIL (Model-in-the-Loop) TEST REPORT
Generated: 2026-05-11 14:32:15

SUMMARY
-------
Total Scenarios: 7
Passed: 7
Failed: 0
Success Rate: 100.0%

DETAILED RESULTS
----------------
Scenario: Blind Spot Detection Test Scenario
Status: PASSED
Duration: 30.00s
Validations: 8/8

  Feature: bsd
    Status: PASS
    Step Count: 3000
    Avg Step Time: 0.010ms
    Max Step Time: 0.150ms
    Validation Accuracy: 100.0%
```text

## Generating Reports

```python
## Programmatically
runner = MILScenarioRunner(simulator)
results = runner.run_scenario('scenarios/scenario.json')
report = runner.generate_report('output/report.txt')

## Via command line
python run_mil_tests.py --output my_report.txt
```text

## Python API

## Basic Usage

```python
from ADAS_SIL_System import ADASSILSimulator
from ADAS_SIL_System.core.mil_testing import MILScenarioRunner

## Initialize simulator
config = {
    'dt': 0.01,
    'adas': {
        'bsd': {'enabled': True},
        'parking': {'enabled': True},
        # ... other features
    }
}
simulator = ADASSILSimulator(config)

## Create runner
runner = MILScenarioRunner(simulator)

## Run scenario
results = runner.run_scenario('scenarios/blind_spot_detection.json')

## Check results
if results.overall_pass:
    print("✓ Scenario passed")
else:
    print("✗ Scenario failed")

## Generate report
report = runner.generate_report('mil_report.txt')
```text

## Advanced Usage - Custom Scenarios

```python
## Create custom scenario
scenario = {
    'name': 'Custom Test',
    'duration': 30.0,
    'vehicle_config': {
        'enabled_features': ['bsd', 'parking']
    },
    'events': [
        {
            'name': 'Enable feature',
            'time': 1.0,
            'type': 'feature_command',
            'parameters': {
                'feature': 'bsd',
                'command': 'enable'
            }
        },
        # ... more events
    ],
    'success_criteria': {
        'all_validations_pass': True,
        'min_accuracy': 0.90
    }
}

## Save and run
import json
with open('custom_scenario.json', 'w') as f:
    json.dump(scenario, f, indent=2)

results = runner.run_scenario('custom_scenario.json')
```text

## Performance Expectations

## Real-time Compliance

The MIL testing framework is designed for real-time or better-than-real-time execution:

- **Simulator Update Rate:** 100 Hz (10ms timestep)

- **Feature Latency:** < 150ms target

- **Step Time:** < 1ms average

- **Validation Latency:** < 100ms typical

## Resource Usage

- **Memory:** ~500MB per simulator instance

- **CPU:** Single-threaded execution on 1 core

- **IO:** Minimal disk I/O except for report generation

## Extending the Framework

## Adding New Scenarios

1. Create JSON scenario file in `scenarios/`
2. Define events and validation points
3. Run with existing test runner

## Adding New Test Classes

```python
from ADAS_SIL_System.core.mil_testing import MILScenarioRunner

class TestMyFeature:
    def test_my_scenario(self, runner, scenarios_dir):
        scenario_file = scenarios_dir / 'my_feature.json'
        results = runner.run_scenario(str(scenario_file))
        
        assert results.overall_pass
        assert results.metrics['my_feature'].passed
```text

## Custom Metrics

```python
## Extend ScenarioValidator for custom metrics
class CustomValidator(ScenarioValidator):
    def validate_custom_metric(self, feature_data):
        # Custom validation logic
        pass
```text

## Troubleshooting

## Scenario Failing

**Problem:** Validation failure

**Solution:**
1. Check scenario JSON format
2. Verify feature is enabled
3. Review event parameters
4. Check success criteria thresholds

## High Latency

**Problem:** Feature latency exceeds max_latency_ms

**Solution:**
1. Check simulator timestep (dt)
2. Reduce feature processing complexity
3. Profile feature implementation
4. Increase max_latency_ms criteria if acceptable

## Missing Metrics

**Problem:** No metrics collected for feature

**Solution:**
1. Verify feature is in enabled_features
2. Ensure feature has proper status methods
3. Check scenario duration is sufficient
4. Verify metrics initialization

## Best Practices

1. **Scenario Design**
   - Keep scenarios focused (test one feature per scenario)

   - Use realistic timings and distances

   - Include edge cases and boundary conditions

2. **Validation**
   - Validate at multiple progress points

   - Check both positive and negative cases

   - Include timing and performance checks

3. **Performance**
   - Set realistic accuracy thresholds (85-98%)

   - Account for simulator limitations

   - Profile slow operations

4. **Reporting**
   - Generate reports for CI/CD

   - Archive reports for trend analysis

   - Monitor metrics over time

## Integration Examples

## GitHub Actions CI/CD

```yaml
name: MIL Testing

on: [push, pull_request]

jobs:
  mil-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2

      - uses: actions/setup-python@v2

        with:
          python-version: '3.10'
      
      - name: Install dependencies

        run: pip install -r ADAS_SIL_System/requirements.txt
      
      - name: Run MIL Tests

        run: python run_mil_tests.py --output mil_report.txt
      
      - name: Upload report

        if: always()
        uses: actions/upload-artifact@v2
        with:
          name: mil-report
          path: mil_report.txt
```text

## Local Development Workflow

```bash
## 1. Make code changes
## 2. Run unit tests
pytest ADAS_SIL_System/tests/test_basic.py -v

## 3. Run MIL tests
python run_mil_tests.py

## 4. Review results
less mil_test_report.txt

## 5. Fix issues and iterate
```text

## Summary

The MIL Testing Framework provides:

✅ **Comprehensive Testing**

- 7 pre-built scenarios covering all ADAS features

- Scenario-based approach for realistic testing

- Support for all 9 ADAS features

✅ **Performance Metrics**

- Real-time metric collection

- Latency and accuracy tracking

- Step-level performance analysis

✅ **Validation & Reporting**

- Automated validation checks

- Detailed HTML/text reports

- Success/failure criteria

✅ **Easy Integration**

- pytest compatibility

- Python API

- Standalone script execution

- CI/CD ready

✅ **Extensibility**

- Custom scenario support

- New test class creation

- Metric customization
