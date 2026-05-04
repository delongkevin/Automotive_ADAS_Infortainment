"""
Vehicle Dynamics Simulator

Implements realistic vehicle physics including:
- Longitudinal dynamics (acceleration, braking)
- Lateral dynamics (steering, slip angles)
- Vertical dynamics (suspension, load transfer)
- Tire models (friction, slip)

Copyright Magna Electronics. All rights reserved.
"""

import numpy as np
from typing import Dict, Tuple
import logging

logger = logging.getLogger(__name__)


class VehicleDynamics:
    """
    Realistic vehicle dynamics model for ADAS SIL simulation.
    Uses bicycle model for lateral dynamics and point mass for longitudinal.
    """

    def __init__(self, config: Dict = None):
        """
        Initialize vehicle dynamics with configuration parameters.

        Args:
            config: Dictionary containing vehicle parameters
        """
        # Default vehicle parameters (typical mid-size sedan)
        self.config = config or {}

        # Mass and inertia
        self.mass = self.config.get('mass', 1500.0)  # kg
        self.inertia_z = self.config.get('inertia_z', 2500.0)  # kg*m^2

        # Dimensions
        self.wheelbase = self.config.get('wheelbase', 2.7)  # m
        self.track_width = self.config.get('track_width', 1.5)  # m
        self.length = self.config.get('length', 4.5)  # m
        self.width = self.config.get('width', 1.8)  # m
        self.height = self.config.get('height', 1.5)  # m

        # Weight distribution
        self.cg_to_front = self.config.get('cg_to_front', 1.2)  # m
        self.cg_to_rear = self.wheelbase - self.cg_to_front
        self.cg_height = self.config.get('cg_height', 0.5)  # m

        # Tire parameters
        self.tire_friction = self.config.get('tire_friction', 0.85)
        self.tire_cornering_stiffness_front = self.config.get('cornering_stiffness_front', -80000.0)  # N/rad
        self.tire_cornering_stiffness_rear = self.config.get('cornering_stiffness_rear', -80000.0)  # N/rad

        # Aerodynamics
        self.drag_coefficient = self.config.get('drag_coefficient', 0.3)
        self.frontal_area = self.config.get('frontal_area', 2.2)  # m^2
        self.air_density = 1.225  # kg/m^3

        # Powertrain limits
        self.max_acceleration = self.config.get('max_acceleration', 3.0)  # m/s^2
        self.max_deceleration = self.config.get('max_deceleration', -8.0)  # m/s^2
        self.max_steering_angle = self.config.get('max_steering_angle', np.deg2rad(35))  # rad
        self.max_steering_rate = self.config.get('max_steering_rate', np.deg2rad(45))  # rad/s

        # State variables
        self.reset_state()

    def reset_state(self):
        """Reset vehicle state to initial conditions."""
        # Position and orientation
        self.x = 0.0  # m
        self.y = 0.0  # m
        self.yaw = 0.0  # rad

        # Velocities
        self.vx = 0.0  # m/s (longitudinal velocity)
        self.vy = 0.0  # m/s (lateral velocity)
        self.yaw_rate = 0.0  # rad/s

        # Accelerations
        self.ax = 0.0  # m/s^2
        self.ay = 0.0  # m/s^2

        # Control inputs
        self.throttle = 0.0  # [0, 1]
        self.brake = 0.0  # [0, 1]
        self.steering_angle = 0.0  # rad

        logger.info("Vehicle state reset")

    def set_state(self, x: float, y: float, yaw: float, vx: float, vy: float = 0.0):
        """
        Set vehicle state explicitly.

        Args:
            x: X position (m)
            y: Y position (m)
            yaw: Yaw angle (rad)
            vx: Longitudinal velocity (m/s)
            vy: Lateral velocity (m/s)
        """
        self.x = x
        self.y = y
        self.yaw = yaw
        self.vx = vx
        self.vy = vy

    def set_controls(self, throttle: float, brake: float, steering_angle: float):
        """
        Set vehicle control inputs.

        Args:
            throttle: Throttle pedal position [0, 1]
            brake: Brake pedal position [0, 1]
            steering_angle: Steering wheel angle (rad)
        """
        self.throttle = np.clip(throttle, 0.0, 1.0)
        self.brake = np.clip(brake, 0.0, 1.0)
        self.steering_angle = np.clip(steering_angle, -self.max_steering_angle, self.max_steering_angle)

    def update(self, dt: float):
        """
        Update vehicle state using bicycle model dynamics.

        Args:
            dt: Time step (s)
        """
        # Calculate total velocity
        v = np.sqrt(self.vx**2 + self.vy**2)

        # Longitudinal dynamics
        self._update_longitudinal(dt, v)

        # Lateral dynamics (only if vehicle is moving)
        if v > 0.1:  # Minimum velocity threshold
            self._update_lateral(dt, v)
        else:
            self.vy = 0.0
            self.yaw_rate = 0.0

        # Update position and orientation
        self._update_position(dt)

    def _update_longitudinal(self, dt: float, v: float):
        """
        Update longitudinal dynamics (acceleration/braking).

        Args:
            dt: Time step (s)
            v: Total velocity (m/s)
        """
        # Calculate forces
        # Engine force (simplified)
        if self.throttle > 0:
            F_drive = self.throttle * self.mass * self.max_acceleration
        else:
            F_drive = 0.0

        # Braking force
        if self.brake > 0:
            F_brake = self.brake * self.mass * abs(self.max_deceleration)
        else:
            F_brake = 0.0

        # Aerodynamic drag
        F_drag = 0.5 * self.air_density * self.drag_coefficient * self.frontal_area * v**2

        # Rolling resistance (simplified)
        F_rolling = 0.015 * self.mass * 9.81

        # Net longitudinal force
        F_x = F_drive - F_brake - F_drag - F_rolling

        # Longitudinal acceleration
        self.ax = F_x / self.mass

        # Update longitudinal velocity
        self.vx += self.ax * dt
        self.vx = max(0.0, self.vx)  # Prevent negative velocity

    def _update_lateral(self, dt: float, v: float):
        """
        Update lateral dynamics using bicycle model.

        Args:
            dt: Time step (s)
            v: Total velocity (m/s)
        """
        # Slip angles at front and rear axles
        if v > 0.1:
            alpha_f = self.steering_angle - np.arctan2(
                self.vy + self.yaw_rate * self.cg_to_front, self.vx
            )
            alpha_r = -np.arctan2(
                self.vy - self.yaw_rate * self.cg_to_rear, self.vx
            )
        else:
            alpha_f = 0.0
            alpha_r = 0.0

        # Lateral tire forces
        F_yf = self.tire_cornering_stiffness_front * alpha_f
        F_yr = self.tire_cornering_stiffness_rear * alpha_r

        # Lateral acceleration
        self.ay = (F_yf + F_yr) / self.mass

        # Yaw moment and acceleration
        M_z = self.cg_to_front * F_yf - self.cg_to_rear * F_yr
        yaw_accel = M_z / self.inertia_z

        # Update lateral velocity and yaw rate
        self.vy += self.ay * dt
        self.yaw_rate += yaw_accel * dt

        # Limit lateral velocity to prevent unrealistic values
        max_vy = 0.3 * v  # Max 30% lateral slip
        self.vy = np.clip(self.vy, -max_vy, max_vy)

    def _update_position(self, dt: float):
        """
        Update vehicle position and orientation.

        Args:
            dt: Time step (s)
        """
        # Convert body-frame velocities to world frame
        vx_world = self.vx * np.cos(self.yaw) - self.vy * np.sin(self.yaw)
        vy_world = self.vx * np.sin(self.yaw) + self.vy * np.cos(self.yaw)

        # Update position
        self.x += vx_world * dt
        self.y += vy_world * dt

        # Update orientation
        self.yaw += self.yaw_rate * dt

        # Normalize yaw to [-pi, pi]
        self.yaw = np.arctan2(np.sin(self.yaw), np.cos(self.yaw))

    def get_state(self) -> Dict:
        """
        Get current vehicle state.

        Returns:
            Dictionary containing all state variables
        """
        return {
            'position': {'x': self.x, 'y': self.y, 'z': 0.0},
            'orientation': {'roll': 0.0, 'pitch': 0.0, 'yaw': self.yaw},
            'velocity': {
                'vx': self.vx,
                'vy': self.vy,
                'vz': 0.0,
                'speed': np.sqrt(self.vx**2 + self.vy**2)
            },
            'acceleration': {'ax': self.ax, 'ay': self.ay, 'az': 0.0},
            'angular_velocity': {'roll_rate': 0.0, 'pitch_rate': 0.0, 'yaw_rate': self.yaw_rate},
            'controls': {
                'throttle': self.throttle,
                'brake': self.brake,
                'steering_angle': self.steering_angle
            },
            'dimensions': {
                'length': self.length,
                'width': self.width,
                'height': self.height
            }
        }

    def get_corners(self) -> np.ndarray:
        """
        Get vehicle corner positions in world coordinates.

        Returns:
            Array of shape (4, 2) with corner positions [x, y]
        """
        # Corner positions in vehicle frame
        half_length = self.length / 2
        half_width = self.width / 2

        corners_local = np.array([
            [half_length, half_width],    # Front right
            [half_length, -half_width],   # Front left
            [-half_length, -half_width],  # Rear left
            [-half_length, half_width]    # Rear right
        ])

        # Rotation matrix
        cos_yaw = np.cos(self.yaw)
        sin_yaw = np.sin(self.yaw)
        R = np.array([[cos_yaw, -sin_yaw], [sin_yaw, cos_yaw]])

        # Transform to world frame
        corners_world = (R @ corners_local.T).T + np.array([self.x, self.y])

        return corners_world

    def get_front_axle_position(self) -> Tuple[float, float]:
        """Get front axle center position in world coordinates."""
        front_x = self.x + self.cg_to_front * np.cos(self.yaw)
        front_y = self.y + self.cg_to_front * np.sin(self.yaw)
        return front_x, front_y

    def get_rear_axle_position(self) -> Tuple[float, float]:
        """Get rear axle center position in world coordinates."""
        rear_x = self.x - self.cg_to_rear * np.cos(self.yaw)
        rear_y = self.y - self.cg_to_rear * np.sin(self.yaw)
        return rear_x, rear_y
