# ADAS SIL (Software-in-the-Loop) System

A comprehensive standalone ADAS simulation system with 3D visualization capabilities for testing Advanced Driver Assistance Systems in a software-in-the-loop environment.

## Features

### ADAS Functions Supported
- **Lane Departure Warning (LDW)** - Detects lane drift and warns driver
- **Adaptive Cruise Control (ACC)** - Maintains safe following distance
- **Automatic Emergency Braking (AEB)** - Prevents or mitigates collisions
- **Blind Spot Detection (BSD)** - Monitors blind spot zones
- **Traffic Sign Recognition (TSR)** - Identifies and interprets traffic signs
- **Lane Keep Assist (LKA)** - Actively maintains lane position

### Visualization Capabilities
- 3D vehicle and environment rendering (Unity/Unreal Engine ready)
- 2D bird's-eye view with real-time vehicle positioning
- Dashboard display with ADAS indicators and warnings
- Sensor coverage visualization (radar, camera, lidar FOV)
- Real-time data plots and metrics

### Simulation Features
- Realistic vehicle dynamics model
- Multi-sensor simulation (radar, camera, lidar, ultrasonic)
- Synthetic scenario generation
- CAN bus simulation with automotive message protocols
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
│   │   ├── lidar.py
│   │   └── ultrasonic.py
│   ├── adas_features/             # ADAS algorithm implementations
│   │   ├── ldw.py                 # Lane Departure Warning
│   │   ├── acc.py                 # Adaptive Cruise Control
│   │   ├── aeb.py                 # Automatic Emergency Braking
│   │   ├── bsd.py                 # Blind Spot Detection
│   │   ├── tsr.py                 # Traffic Sign Recognition
│   │   └── lka.py                 # Lane Keep Assist
│   └── scenario_engine.py         # Scenario management
├── can_interface/                 # CAN bus simulation
│   ├── can_simulator.py
│   ├── can_database.py
│   └── message_definitions.py
├── visualization/                 # Visualization components
│   ├── dashboard.py               # Main dashboard
│   ├── bird_eye_view.py           # 2D top-down view
│   ├── sensor_overlay.py          # Sensor visualization
│   ├── data_plotter.py            # Real-time plots
│   └── unity_bridge.py            # Unity/Unreal integration
├── scenarios/                     # Test scenario definitions
│   ├── highway_cruise.json
│   ├── urban_traffic.json
│   ├── lane_change.json
│   └── emergency_braking.json
├── config/                        # Configuration files
│   ├── vehicle_config.json
│   ├── sensor_config.json
│   └── adas_config.json
├── tests/                         # Unit and integration tests
├── utils/                         # Utility functions
│   ├── logger.py
│   ├── data_recorder.py
│   └── metrics.py
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
from ADAS_SIL_System import ADASSILSimulator

# Initialize simulator
sim = ADASSILSimulator()

# Load a scenario
sim.load_scenario('scenarios/highway_cruise.json')

# Run simulation
sim.run(duration=60.0, visualization=True)

# Access results
results = sim.get_results()
print(f"ADAS Events: {results['adas_events']}")
```

### Running with 2D Visualization

```bash
python ADAS_SIL_System/main.py --scenario highway_cruise --viz-2d
```

### Running with Unity Integration

```bash
# Start Unity bridge server
python ADAS_SIL_System/main.py --scenario highway_cruise --unity-bridge --port 5555
```

Then connect your Unity application to `localhost:5555`.

## Configuration

### Vehicle Configuration
Edit `config/vehicle_config.json` to customize:
- Vehicle dimensions and mass
- Performance characteristics
- Sensor mounting positions

### Sensor Configuration
Edit `config/sensor_config.json` to customize:
- Sensor types and quantities
- Field of view and range
- Detection accuracy and noise models

### ADAS Configuration
Edit `config/adas_config.json` to customize:
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

## CAN Bus Integration

The system simulates standard automotive CAN messages compatible with Vector CANoe:

```python
from ADAS_SIL_System.can_interface import CANSimulator

can_sim = CANSimulator()
can_sim.start()

# Access CAN messages
vehicle_speed = can_sim.get_signal('VehicleSpeed')
steering_angle = can_sim.get_signal('SteeringWheelAngle')
```

## Unity/Unreal Integration

The system provides a JSON-based socket API for real-time communication with Unity/Unreal:

### Message Format
```json
{
  "timestamp": 1234567890.123,
  "vehicle": {
    "position": [x, y, z],
    "rotation": [roll, pitch, yaw],
    "velocity": [vx, vy, vz]
  },
  "sensors": {
    "radar": [...],
    "camera": [...],
    "lidar": [...]
  },
  "adas_status": {
    "ldw": {"active": true, "warning": false},
    "acc": {"active": true, "target_distance": 50.0},
    "aeb": {"active": true, "braking": false}
  }
}
```

## Testing

```bash
# Run all tests
python -m pytest ADAS_SIL_System/tests/

# Run specific test suite
python -m pytest ADAS_SIL_System/tests/test_adas_features.py

# Run with coverage
python -m pytest --cov=ADAS_SIL_System ADAS_SIL_System/tests/
```

## Performance

- Real-time simulation at 100Hz update rate
- Supports multiple concurrent sensors
- Efficient scenario event processing
- Low-latency Unity/Unreal bridge (<10ms)

## Integration with Existing Frameworks

This ADAS SIL system is designed to be standalone but can optionally integrate with:
- **GM VIP Automation Framework**: CAN message compatibility
- **Stellantis STLA test assets**: Scenario definitions and sensor models
- **Vector CANoe**: CAN database export/import

## Contributing

This is part of the Automotive_ADAS_Infotainment repository maintained by Magna Electronics.

## License

Copyright Magna Electronics. All rights reserved.

## Support

For questions or issues, please contact the Automotive ADAS team.
