"""
Adaptive Cruise Control (ACC) System

Maintains desired speed and safe following distance from lead vehicle.
Automatically adjusts speed to maintain safe gap.

Copyright Magna Electronics. All rights reserved.
"""

import numpy as np
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class AdaptiveCruiseControl:
    """
    Adaptive Cruise Control (ACC) ADAS feature.

    Maintains set speed and automatically adjusts to maintain
    safe following distance from lead vehicle.
    """

    def __init__(self, config: Dict = None):
        """
        Initialize ACC system.

        Args:
            config: Configuration dictionary
        """
        self.config = config or {}

        # ACC parameters
        self.min_speed = self.config.get('min_speed', 30.0 / 3.6)  # 30 km/h
        self.max_speed = self.config.get('max_speed', 180.0 / 3.6)  # 180 km/h

        # Following distance (time gap)
        self.time_gap_settings = [1.0, 1.5, 2.0, 2.5]  # seconds
        self.time_gap_index = 2  # Default to 2.0 seconds
        self.min_following_distance = 5.0  # m

        # Control parameters
        self.max_acceleration = self.config.get('max_acceleration', 2.0)  # m/s^2
        self.max_deceleration = self.config.get('max_deceleration', -3.0)  # m/s^2
        self.comfortable_deceleration = -2.0  # m/s^2

        # PID controller gains
        self.kp_speed = 0.5
        self.ki_speed = 0.1
        self.kd_speed = 0.2

        self.kp_distance = 0.3
        self.ki_distance = 0.05
        self.kd_distance = 0.15

        # State
        self.enabled = False
        self.active = False
        self.set_speed = 100.0 / 3.6  # 100 km/h default
        self.target_speed = self.set_speed
        self.target_acceleration = 0.0

        # Lead vehicle tracking
        self.lead_vehicle = None
        self.lead_vehicle_distance = float('inf')
        self.lead_vehicle_velocity = 0.0

        # PID controller states
        self.speed_error_integral = 0.0
        self.speed_error_prev = 0.0
        self.distance_error_integral = 0.0
        self.distance_error_prev = 0.0

        logger.info("ACC system initialized")

    def update(self, vehicle_state: Dict, sensor_data: List[Dict],
               current_time: float, dt: float) -> Dict:
        """
        Update ACC system and calculate target acceleration.

        Args:
            vehicle_state: Current vehicle state
            sensor_data: List of sensor detections
            current_time: Current simulation time (s)
            dt: Time step (s)

        Returns:
            Dictionary with ACC status and control commands
        """
        if not self.enabled:
            self.active = False
            return self._get_status()

        current_speed = vehicle_state['velocity']['speed']

        # Find lead vehicle from sensor data
        self._find_lead_vehicle(sensor_data, vehicle_state)

        # Determine control mode
        if self.lead_vehicle is not None:
            # Following mode
            self._update_following_mode(current_speed, dt)
        else:
            # Speed control mode
            self._update_speed_control_mode(current_speed, dt)

        self.active = True
        return self._get_status()

    def _find_lead_vehicle(self, sensor_data: List[Dict], vehicle_state: Dict):
        """
        Identify lead vehicle from sensor detections.

        Args:
            sensor_data: List of sensor detections
            vehicle_state: Current vehicle state
        """
        # Filter radar detections in front of vehicle
        radar_detections = [d for d in sensor_data
                           if d.get('sensor_type') == 'radar'
                           and not d.get('false_alarm', False)]

        # Find closest vehicle in lane
        closest_distance = float('inf')
        closest_vehicle = None

        for detection in radar_detections:
            # Check if in lane (azimuth close to 0)
            azimuth = detection.get('azimuth', 0.0)
            if abs(azimuth) < np.deg2rad(5.0):  # Within 5 degrees of straight ahead
                distance = detection.get('range', float('inf'))
                if distance < closest_distance and distance > 0:
                    closest_distance = distance
                    closest_vehicle = detection

        if closest_vehicle:
            self.lead_vehicle = closest_vehicle
            self.lead_vehicle_distance = closest_distance
            # Relative velocity (positive = lead vehicle moving away)
            self.lead_vehicle_velocity = vehicle_state['velocity']['speed'] + closest_vehicle.get('radial_velocity', 0.0)
        else:
            self.lead_vehicle = None
            self.lead_vehicle_distance = float('inf')
            self.lead_vehicle_velocity = 0.0

    def _update_following_mode(self, current_speed: float, dt: float):
        """
        Update ACC in following mode (lead vehicle present).

        Args:
            current_speed: Current vehicle speed (m/s)
            dt: Time step (s)
        """
        # Desired following distance
        time_gap = self.time_gap_settings[self.time_gap_index]
        desired_distance = max(current_speed * time_gap, self.min_following_distance)

        # Distance error
        distance_error = self.lead_vehicle_distance - desired_distance

        # Velocity error (relative velocity)
        velocity_error = self.lead_vehicle_velocity - current_speed

        # PID control for distance
        self.distance_error_integral += distance_error * dt
        self.distance_error_integral = np.clip(self.distance_error_integral, -10.0, 10.0)

        distance_error_derivative = (distance_error - self.distance_error_prev) / dt if dt > 0 else 0.0
        self.distance_error_prev = distance_error

        # Calculate target acceleration
        accel_distance = (self.kp_distance * distance_error +
                         self.ki_distance * self.distance_error_integral +
                         self.kd_distance * distance_error_derivative)

        # Speed matching component
        accel_speed = velocity_error * 0.5

        # Combine
        self.target_acceleration = accel_distance + accel_speed

        # Limit acceleration
        self.target_acceleration = np.clip(self.target_acceleration,
                                          self.max_deceleration,
                                          self.max_acceleration)

        # Target speed is lead vehicle speed (capped at set speed)
        self.target_speed = min(self.lead_vehicle_velocity, self.set_speed)

    def _update_speed_control_mode(self, current_speed: float, dt: float):
        """
        Update ACC in speed control mode (no lead vehicle).

        Args:
            current_speed: Current vehicle speed (m/s)
            dt: Time step (s)
        """
        # Speed error
        speed_error = self.set_speed - current_speed

        # PID control
        self.speed_error_integral += speed_error * dt
        self.speed_error_integral = np.clip(self.speed_error_integral, -10.0, 10.0)

        speed_error_derivative = (speed_error - self.speed_error_prev) / dt if dt > 0 else 0.0
        self.speed_error_prev = speed_error

        self.target_acceleration = (self.kp_speed * speed_error +
                                   self.ki_speed * self.speed_error_integral +
                                   self.kd_speed * speed_error_derivative)

        # Limit acceleration
        self.target_acceleration = np.clip(self.target_acceleration,
                                          self.max_deceleration,
                                          self.max_acceleration)

        self.target_speed = self.set_speed

    def set_speed_target(self, speed: float):
        """
        Set target cruise speed.

        Args:
            speed: Target speed (m/s)
        """
        self.set_speed = np.clip(speed, self.min_speed, self.max_speed)
        logger.info(f"ACC set speed: {self.set_speed * 3.6:.1f} km/h")

    def increase_speed(self, delta: float = 5.0 / 3.6):
        """Increase set speed by delta (default 5 km/h)."""
        self.set_speed_target(self.set_speed + delta)

    def decrease_speed(self, delta: float = 5.0 / 3.6):
        """Decrease set speed by delta (default 5 km/h)."""
        self.set_speed_target(self.set_speed - delta)

    def set_time_gap(self, gap_index: int):
        """
        Set following time gap.

        Args:
            gap_index: Index into time_gap_settings (0-3)
        """
        self.time_gap_index = np.clip(gap_index, 0, len(self.time_gap_settings) - 1)
        logger.info(f"ACC time gap: {self.time_gap_settings[self.time_gap_index]:.1f}s")

    def increase_time_gap(self):
        """Increase following time gap."""
        self.set_time_gap(self.time_gap_index + 1)

    def decrease_time_gap(self):
        """Decrease following time gap."""
        self.set_time_gap(self.time_gap_index - 1)

    def enable(self, current_speed: float):
        """
        Enable ACC system.

        Args:
            current_speed: Current vehicle speed (m/s)
        """
        if current_speed >= self.min_speed:
            self.enabled = True
            self.set_speed = current_speed
            logger.info(f"ACC enabled at {current_speed * 3.6:.1f} km/h")
        else:
            logger.warning(f"ACC requires minimum speed of {self.min_speed * 3.6:.1f} km/h")

    def disable(self):
        """Disable ACC system."""
        self.enabled = False
        self.active = False
        self.target_acceleration = 0.0
        # Reset PID states
        self.speed_error_integral = 0.0
        self.speed_error_prev = 0.0
        self.distance_error_integral = 0.0
        self.distance_error_prev = 0.0
        logger.info("ACC disabled")

    def _get_status(self) -> Dict:
        """
        Get current ACC status.

        Returns:
            Status dictionary
        """
        return {
            'feature': 'ACC',
            'enabled': self.enabled,
            'active': self.active,
            'set_speed': self.set_speed,
            'target_speed': self.target_speed,
            'target_acceleration': self.target_acceleration,
            'lead_vehicle_detected': self.lead_vehicle is not None,
            'lead_vehicle_distance': self.lead_vehicle_distance if self.lead_vehicle else None,
            'time_gap': self.time_gap_settings[self.time_gap_index]
        }
