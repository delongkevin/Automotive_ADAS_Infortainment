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
            'fov_horizontal': np.deg2rad(20.0),
            'fov_vertical': np.deg2rad(10.0)
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


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
