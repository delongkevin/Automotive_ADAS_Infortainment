# ADAS SIL (Software-in-the-Loop) System

A standalone ADAS simulation system with 2D and 3D visualization hooks for testing Advanced Driver Assistance Systems in a software-in-the-loop environment.

## Features

### ADAS Functions Supported
- **Lane Departure Warning (LDW)** - Detects lane drift and warns driver
- **Adaptive Cruise Control (ACC)** - Maintains safe following distance
- **Automatic Emergency Braking (AEB)** - Prevents or mitigates collisions

### Visualization Capabilities
- 2D bird's-eye view with real-time vehicle positioning
- Sensor coverage visualization for the implemented radar/camera suite
- Unity/Unreal Engine WebSocket bridge for external 3D rendering

### Simulation Features
- Realistic vehicle dynamics model
- Multi-sensor simulation (radar, camera)
- JSON scenarios with timed synthetic events
- Configurable test scenarios in JSON format
- Data logging and replay capabilities

## Architecture

```
ADAS_SIL_System/
├── core/                          # Core simulation engine
│   ├── vehicle_dynamics.py        # Vehicle physics model
│   ├── sensors/                   # Sensor simulators
│   │   ├── base_sensor.py
│   │   ├── radar.py
│   │   ├── camera.py
│   ├── adas_features/             # ADAS algorithm implementations
│   │   ├── ldw.py                 # Lane Departure Warning
│   │   ├── acc.py                 # Adaptive Cruise Control
│   │   ├── aeb.py                 # Automatic Emergency Braking
├── simulator.py                   # Simulator orchestration
├── visualization/                 # Visualization components
│   ├── bird_eye_view.py           # 2D top-down view
│   └── unity_bridge.py            # Unity/Unreal integration
├── scenarios/                     # Test scenario definitions
│   ├── highway_cruise.json
│   └── emergency_braking.json
├── config/
│   └── default_config.json        # Default simulator configuration
├── tests/                         # Unit and integration tests
├── main.py                        # Main application entry
├── requirements.txt               # Python dependencies
└── README.md                      # This file
```

## Installation

```bash
# Install Python dependencies
pip install -r ADAS_SIL_System/requirements.txt
```

## Quick Start

### Running a Basic Simulation

```python
import json

from ADAS_SIL_System import ADASSILSimulator

# Initialize simulator
sim = ADASSILSimulator()

# Load a scenario dictionary
with open('ADAS_SIL_System/scenarios/highway_cruise.json', 'r') as scenario_file:
    scenario = json.load(scenario_file)
sim.load_scenario(scenario)

# Run simulation
sim.run(duration=60.0, real_time=False)

# Access results
results = sim.get_results()
print(f"ADAS Events: {results['adas_events']}")
```

### Running with 2D Visualization

```bash
python -m ADAS_SIL_System.main --scenario highway_cruise --viz-2d
```

### Running with Unity Integration

```bash
# Start Unity bridge server
python -m ADAS_SIL_System.main --scenario highway_cruise --unity-bridge --port 5555
```

Then connect your Unity application to `localhost:5555`.

## Configuration

Edit `config/default_config.json` to customize:
- Vehicle dimensions, mass, and steering limits
- Radar/camera field of view, range, and noise models
- ADAS feature activation thresholds
- Warning timing parameters
- Control authority limits

## Creating Custom Scenarios

Scenarios are defined in JSON format:

```json
{
  "name": "Highway Cruise",
  "duration": 60.0,
  "initial_conditions": {
    "ego_vehicle": {
      "position": [0, 0, 0],
      "velocity": 27.8,
      "lane": 1
    }
  },
  "events": [
    {
      "time": 5.0,
      "type": "spawn_vehicle",
      "params": {
        "position": [50, 0, 0],
        "velocity": 22.2
      }
    }
  ]
}
```

## Unity/Unreal Integration

The system provides a JSON-based socket API for real-time communication with Unity/Unreal:

### Message Format
```json
{
  "type": "state_update",
  "timestamp": 1234567890.123,
  "vehicle": {
    "position": {"x": 12.3, "y": 0.0, "z": 0.0},
    "rotation": {"roll": 0.0, "pitch": 0.0, "yaw": 0.1},
    "velocity": {"vx": 20.0, "vy": 0.0, "vz": 0.0, "speed": 20.0},
    "controls": {"throttle": 0.2, "brake": 0.0, "steering_angle": 0.0}
  },
  "adas": {
    "ldw": {"warning_active": false, "warning_side": null},
    "acc": {"active": true, "target_speed": 27.8},
    "aeb": {"warning_active": false, "braking_active": false}
  }
}
```

## Testing

```bash
# Run all tests
python -m pytest ADAS_SIL_System/tests/

# Run specific test suite
python -m pytest ADAS_SIL_System/tests/test_basic.py
```

## Performance

- Real-time simulation at 100Hz update rate
- Supports multiple concurrent sensors
- Efficient scenario event processing
- Low-latency Unity/Unreal bridge for external 3D renderers

## Integration with Existing Frameworks

This ADAS SIL system is designed to be standalone but can optionally integrate with:
- **GM VIP Automation Framework**: shared scenario concepts or signal definitions, where applicable
- **Stellantis STLA assets**: reusable scenario data or sensor assumptions, where applicable

## Contributing

This is part of the Automotive_ADAS_Infotainment repository maintained by Magna Electronics.

## License

Copyright Magna Electronics. All rights reserved.

## Support

For questions or issues, please contact the Automotive ADAS team.
