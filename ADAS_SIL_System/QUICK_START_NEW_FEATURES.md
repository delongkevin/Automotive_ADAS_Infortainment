# Quick Start Guide - New ADAS Features

## Running the Tests

All new features include comprehensive tests. Run them with:

```bash
cd /workspaces/Automotive_ADAS_Infortainment
python -m pytest ADAS_SIL_System/tests/test_basic.py -v

# Run specific feature tests:
python -m pytest ADAS_SIL_System/tests/test_basic.py::TestBlindSpotDetection -v
python -m pytest ADAS_SIL_System/tests/test_basic.py::TestAutonomousParking -v
python -m pytest ADAS_SIL_System/tests/test_basic.py::TestSurroundViewCamera -v
```

## Feature-by-Feature Examples

### Blind Spot Detection (BSD)

Detect vehicles in blind spots on left, right, and rear:

```python
from ADAS_SIL_System import ADASSILSimulator

# Initialize simulator with BSD enabled
sim = ADASSILSimulator({
    'adas': {'bsd': {'enabled': True}}
})

# In simulation loop:
vehicle_state = sim.vehicle.get_state()
bsd_status = sim.adas_features['bsd'].update(
    vehicle_state, sensor_data, current_time
)

# Check for warnings:
if bsd_status['warning_active']:
    direction = bsd_status['warning_side']  # 'left', 'right', 'rear'
    print(f"⚠️  Vehicle in {direction} blind spot!")
```

### Autonomous Parking

Automatically detect and park in parking spaces:

```python
# Initialize with parking enabled
sim = ADASSILSimulator({
    'adas': {'parking': {'enabled': True}}
})

parking = sim.adas_features['parking']

# Simulate scanning for parking spaces
parking.enable()
status = parking.update(vehicle_state, sensor_data, time, dt)

# When space detected, start parking
if status['spaces_detected'] > 0:
    print(f"🅿️  Found {status['spaces_detected']} parking spaces")
    parking.start_parking()

# Monitor parking progress
print(f"Parking progress: {status['progress'] * 100:.1f}%")
print(f"Parking type: {status['parking_type']}")  # parallel or perpendicular

# Brake when complete
if status['stage'] == 'complete':
    print("✅ Parking complete!")
```

### Trailer Assistance

Guide trailer steering during reverse maneuvers:

```python
# Initialize with trailer features
sim = ADASSILSimulator({
    'adas': {'trailer': {'enabled': True}}
})

trailer = sim.adas_features['trailer_assistance']
trailer.enable()

# Set guidance mode
trailer.set_guidance_mode('auto', strength=0.8)

# Set target angle (align trailer straight)
import numpy as np
trailer.set_target_angle(np.deg2rad(0))  # 0 degrees = straight

# Update during reversing
vehicle_state['velocity']['vx'] = -2.0  # Negative = reversing
status = trailer.update(vehicle_state, sensor_data, time, dt)

if status['warning_active']:
    print(f"⚠️  Trailer angle critical: {status['current_trailer_angle']:.1f}°")
```

### Trailer Reverse Guidance

Guide vehicle-trailer through tight reverse maneuvers:

```python
reverse_guide = sim.adas_features['trailer_reverse']
reverse_guide.enable()

# Define path (series of waypoints)
path = [
    (0.0, 0.0),      # Start position
    (5.0, 2.0),      # First turn
    (10.0, 4.0),     # Second turn
    (10.0, 8.0)      # Final position
]

reverse_guide.set_target_path(path)
reverse_guide.start_guidance()

# During reverse maneuver:
status = reverse_guide.update(vehicle_state, sensor_data, time, dt)
steering_cmd = status['steering_command']
progress = status['path_progress']

print(f"Following path: {progress*100:.1f}% complete")
```

### Surround View Camera

Intelligent multi-camera view switching:

```python
from ADAS_SIL_System.core.adas_features import CameraViewMode

sim = ADASSILSimulator({
    'adas': {'surround_view': {'enabled': True}}
})

svc = sim.adas_features['surround_view']

# Auto-switching based on vehicle state (reverse, turning, etc.)
svc.enable_auto_switching(True)

# Or manual view control:
svc.set_view_mode(CameraViewMode.REAR)

# Configure display
svc.set_display_mode('pip')  # Picture-in-picture or 'split', 'single'

# Record video
svc.start_recording('front')
svc.start_recording()  # All cameras

# Monitor view state
status = svc.update(vehicle_state, sensor_data, time, dt)
current = status['current_view']  # 'front', 'rear', 'bird_eye', etc.
recording = status['cameras_recording']
print(f"📷 Current view: {current}, Recording {recording} streams")
```

## Common Scenarios

### Scenario 1: Highway Driving with BSD

```python
vehicle_state = {
    'position': {'x': 0.0, 'y': 0.0},
    'orientation': {'yaw': 0.0},
    'velocity': {'speed': 25.0},  # 25 m/s = 90 km/h
    'controls': {'steering_angle': 0.0}
}

sensor_data = [
    {
        'sensor_type': 'radar',
        'classification': 'vehicle',
        'azimuth': np.deg2rad(90),  # Right side
        'range': 2.0,               # 2m away
        'x': -2.0, 'y': 2.0,
        'velocity': 23.0
    }
]

bsd = sim.adas_features['bsd']
status = bsd.update(vehicle_state, sensor_data, 0.0)

if status['right_occupied']:
    print("⚠️  Car in right blind spot - use caution changing lanes!")
```

### Scenario 2: Parking Lot Maneuver

```python
# Switch to rear view automatically
vehicle_state['transmission'] = {'gear': 'R'}
vehicle_state['velocity'] = {'speed': 0.0}

parking = sim.adas_features['parking']
svc = sim.adas_features['surround_view']

# Surround view should auto-switch to bird's eye for parking
svc.enable_auto_switching(True)

# Detect and execute parking
for i in range(100):  # Simulate 100 steps
    status = parking.update(vehicle_state, sensor_data, i*0.01, 0.01)
    if status['spaces_detected'] > 0:
        print(f"Space found: {status['parking_type']}")
        break
```

### Scenario 3: Trailer Reversing

```python
vehicle_state['velocity']['vx'] = -1.5  # Reversing
vehicle_state['controls']['steering_angle'] = np.deg2rad(15)

trailer = sim.adas_features['trailer_assistance']
reverse_guide = sim.adas_features['trailer_reverse']

# Enable assistance
trailer.set_guidance_mode('auto')
reverse_guide.set_target_path([(0, 0), (2, 2), (4, 4)])
reverse_guide.start_guidance()

# Execute reverse maneuver
for step in range(200):
    t_status = trailer.update(vehicle_state, sensor_data, step*0.01, 0.01)
    r_status = reverse_guide.update(vehicle_state, sensor_data, step*0.01, 0.01)
    
    # Apply steering correction from reverse guidance
    vehicle_state['controls']['steering_angle'] = r_status['steering_command']
    
    if t_status['critical_angle']:
        print("⚠️  Trailer angle critical!")
```

## Configuration Tips

### Enable All Features at Once

```python
config = {
    'adas': {
        'ldw': {'enabled': True},
        'acc': {'enabled': True},
        'aeb': {'enabled': True},
        'bsd': {'enabled': True},
        'parking': {'enabled': True},
        'trailer': {'enabled': True},
        'surround_view': {'enabled': True}
    }
}

sim = ADASSILSimulator(config)
```

### Customize Feature Parameters

```python
config = {
    'adas': {
        'bsd': {
            'enabled': True,
            'min_speed': 15.0 / 3.6,      # 15 km/h minimum
            'max_speed': 200.0 / 3.6      # 200 km/h maximum
        },
        'parking': {
            'enabled': True,
            'min_space_width': 5.5,       # Minimum space width (m)
            'vehicle_length': 4.7,        # Vehicle length (m)
            'vehicle_width': 1.8          # Vehicle width (m)
        },
        'trailer': {
            'enabled': True,
            'trailer_length': 5.0,        # Trailer length (m)
            'max_trailer_angle': np.deg2rad(45)  # Max angle
        }
    }
}
```

## Performance Notes

- All features run at 100 Hz (0.01s time step)
- Typical execution time: <5ms per update cycle
- Can be used simultaneously in same simulation
- Modular design allows enabling/disabling individually

## Troubleshooting

### Feature not responding to sensor data

Ensure sensor data includes correct dictionary keys:
```python
sensor_data = [{
    'sensor_type': 'radar',           # Required
    'classification': 'vehicle',      # For BSD and parking
    'azimuth': angle,                 # Required
    'range': distance,                # Required
    'x': global_x,                    # For parking
    'y': global_y,                    # For parking
    'velocity': speed,                # For BSD
    'false_alarm': False              # To filter noise
}]
```

### View not switching automatically

Enable auto-switching explicitly:
```python
svc = sim.adas_features['surround_view']
svc.enable_auto_switching(True)
svc.switching_mode = 'context_aware'
```

### Parking not detecting spaces

Ensure ultrasonic/radar sensors are in configuration:
```python
'sensors': {
    'front_radar': {'enabled': True},
    'side_ultrasonic': {'enabled': True}  # For parking detection
}
```

## Further Reading

- [NEW_FEATURES_SUMMARY.md](NEW_FEATURES_SUMMARY.md) - Detailed feature documentation
- [README.md](README.md) - ADAS SIL System overview
- [tests/test_basic.py](../tests/test_basic.py) - Test examples and usage patterns
