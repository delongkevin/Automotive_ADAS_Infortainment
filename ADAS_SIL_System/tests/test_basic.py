"""
ADAS SIL System - Unit Tests

Basic unit tests for core components.

Copyright Magna Electronics. All rights reserved.
"""

import pytest
import numpy as np
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from ADAS_SIL_System.simulator import ADASSILSimulator
from core.vehicle_dynamics import VehicleDynamics
from core.sensors import RadarSensor, CameraSensor
from core.adas_features import LaneDepartureWarning, AdaptiveCruiseControl, AutomaticEmergencyBraking


class TestVehicleDynamics:
    """Test vehicle dynamics simulation."""

    def test_initialization(self):
        """Test vehicle initialization."""
        vehicle = VehicleDynamics()
        assert vehicle.mass > 0
        assert vehicle.wheelbase > 0

    def test_reset_state(self):
        """Test state reset."""
        vehicle = VehicleDynamics()
        vehicle.x = 100.0
        vehicle.vx = 20.0
        vehicle.reset_state()
        assert vehicle.x == 0.0
        assert vehicle.vx == 0.0

    def test_set_state(self):
        """Test setting vehicle state."""
        vehicle = VehicleDynamics()
        vehicle.set_state(x=10.0, y=5.0, yaw=np.pi/4, vx=15.0)
        assert vehicle.x == 10.0
        assert vehicle.y == 5.0
        assert vehicle.yaw == np.pi/4
        assert vehicle.vx == 15.0

    def test_update(self):
        """Test vehicle dynamics update."""
        vehicle = VehicleDynamics()
        vehicle.set_controls(throttle=0.5, brake=0.0, steering_angle=0.0)

        initial_x = vehicle.x
        vehicle.update(dt=0.1)

        # Vehicle should have moved forward
        assert vehicle.vx > 0
        assert vehicle.x > initial_x

    def test_configured_steering_angle_accepts_degrees(self):
        """Test steering angle config is interpreted correctly."""
        vehicle = VehicleDynamics({'max_steering_angle': 35.0})
        vehicle.set_controls(throttle=0.0, brake=0.0, steering_angle=10.0)
        assert vehicle.steering_angle == pytest.approx(np.deg2rad(35.0))


class TestRadarSensor:
    """Test radar sensor."""

    def test_initialization(self):
        """Test radar sensor initialization."""
        config = {
            'position': [3.0, 0.0, 0.5],
            'max_range': 200.0,
            'fov_horizontal': 20.0
        }
        sensor = RadarSensor('test_radar', config)
        assert sensor.sensor_id == 'test_radar'
        assert sensor.max_range == 200.0

    def test_fov_check(self):
        """Test field of view checking."""
        config = {
            'position': [0.0, 0.0, 0.0],
            'max_range': 100.0,
            'min_range': 1.0,
            'fov_horizontal': 20.0,
            'fov_vertical': 10.0
        }
        sensor = RadarSensor('test_radar', config)

        # Object directly in front - should be in FOV
        assert sensor.is_in_fov(
            np.array([50.0, 0.0, 0.0]),
            np.array([0.0, 0.0, 0.0]),
            0.0
        )

        # Object too far to the side - should not be in FOV
        assert not sensor.is_in_fov(
            np.array([50.0, 50.0, 0.0]),
            np.array([0.0, 0.0, 0.0]),
            0.0
        )

    def test_rcs_threshold_filters_detections(self):
        """Test weak radar targets are filtered by minimum RCS."""
        vehicle = VehicleDynamics()
        sensor = RadarSensor('test_radar', {
            'position': [0.0, 0.0, 0.0],
            'max_range': 100.0,
            'fov_horizontal': 20.0,
            'fov_vertical': 10.0,
            'detection_probability': 1.0,
            'false_alarm_rate': 0.0,
            'update_rate': 1.0,
            'min_rcs': 20.0
        })
        sensor.last_update_time = -1.0

        detections = sensor.sense(vehicle, {
            'vehicles': [{
                'id': 1,
                'position': {'x': 30.0, 'y': 0.0, 'z': 0.0},
                'velocity': {'vx': 0.0, 'vy': 0.0, 'vz': 0.0},
                'rcs': 10.0
            }],
            'obstacles': []
        }, 0.0)

        assert detections == []


class TestCameraSensor:
    """Test camera sensor behavior."""

    def test_lane_detection_uses_coefficients_without_points(self):
        """Test lane detection works when scenarios only provide polynomial coefficients."""
        sensor = CameraSensor('test_camera', {
            'position': [0.0, 0.0, 0.0],
            'max_range': 100.0,
            'fov_horizontal': 50.0,
            'fov_vertical': 30.0
        })

        detections = sensor._detect_lanes(
            [{
                'id': 1,
                'type': 'dashed',
                'side': 'left',
                'coefficients': [1.75, 0.0, 0.0, 0.0],
                'points': []
            }],
            np.array([0.0, 0.0, 0.0]),
            0.0
        )

        assert len(detections) == 1
        assert detections[0]['coefficients'][0] == pytest.approx(1.75)


class TestADASFeatures:
    """Test ADAS feature implementations."""

    def test_ldw_initialization(self):
        """Test LDW initialization."""
        ldw = LaneDepartureWarning()
        assert ldw.enabled == True
        assert ldw.warning_active == False

    def test_acc_initialization(self):
        """Test ACC initialization."""
        acc = AdaptiveCruiseControl()
        assert acc.enabled == False
        assert acc.active == False

    def test_aeb_initialization(self):
        """Test AEB initialization."""
        aeb = AutomaticEmergencyBraking()
        assert aeb.enabled == True
        assert aeb.braking_active == False

    def test_acc_enable_disable(self):
        """Test ACC enable/disable."""
        acc = AdaptiveCruiseControl()

        # Enable ACC at valid speed
        acc.enable(current_speed=20.0)
        assert acc.enabled == True

        # Disable ACC
        acc.disable()
        assert acc.enabled == False
        assert acc.active == False


class TestSimulator:
    """Test simulator integration behavior."""

    def test_step_accepts_mixed_feature_signatures_and_processes_events(self):
        """Test simulator steps without TypeError and applies scenario events."""
        simulator = ADASSILSimulator({
            'dt': 0.1,
            'vehicle': {'max_steering_angle': 35.0},
            'sensors': {
                'front_radar': {
                    'enabled': True,
                    'position': [0.0, 0.0, 0.0],
                    'max_range': 100.0,
                    'min_range': 0.5,
                    'fov_horizontal': 20.0,
                    'fov_vertical': 10.0,
                    'update_rate': 50.0,
                    'detection_probability': 1.0,
                    'false_alarm_rate': 0.0
                },
                'front_camera': {
                    'enabled': True,
                    'position': [0.0, 0.0, 0.0],
                    'max_range': 100.0,
                    'min_range': 0.5,
                    'fov_horizontal': 50.0,
                    'fov_vertical': 30.0,
                    'update_rate': 50.0,
                    'detection_probability': 1.0
                }
            }
        })
        simulator.load_scenario({
            'name': 'event_test',
            'initial_conditions': {
                'ego_vehicle': {'position': [0.0, 0.0, 0.0], 'velocity': 20.0, 'yaw': 0.0}
            },
            'environment': {
                'vehicles': [{
                    'id': 1,
                    'position': {'x': 10.0, 'y': 0.0, 'z': 0.0},
                    'velocity': {'vx': 5.0, 'vy': 0.0, 'vz': 0.0},
                    'rcs': 25.0
                }],
                'lanes': [
                    {'id': 1, 'type': 'dashed', 'side': 'left', 'coefficients': [1.75, 0.0, 0.0, 0.0], 'points': []},
                    {'id': 2, 'type': 'solid', 'side': 'right', 'coefficients': [-1.75, 0.0, 0.0, 0.0], 'points': []}
                ]
            },
            'events': [{
                'time': 0.0,
                'type': 'vehicle_acceleration',
                'vehicle_id': 1,
                'acceleration': 1.0,
                'duration': 0.2
            }]
        })

        simulator.step()
        lead_vehicle = simulator.environment['vehicles'][0]
        assert lead_vehicle['velocity']['vx'] > 5.0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
