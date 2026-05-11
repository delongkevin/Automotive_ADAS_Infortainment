"""
Trailer Assistance System

Provides active steering guidance for trailers and reverse guidance.
Assists with trailer angle alignment and reverse maneuvering.

Copyright Magna Electronics. All rights reserved.
"""

import numpy as np
from typing import Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class TrailerAssistance:
    """
    Trailer Assistance ADAS feature.

    Provides active steering control and guidance for vehicles
    with trailers, helping maintain proper angles during maneuvers.
    """

    def __init__(self, config: Dict = None):
        """
        Initialize trailer assistance system.

        Args:
            config: Configuration dictionary
        """
        self.config = config or {}

        # System parameters
        self.enabled = False  # Disabled by default until trailer detected
        self.active = False
        self.min_speed = 0.0  # m/s
        self.max_speed = self.config.get('max_speed', 30.0 / 3.6)  # 30 km/h

        # Trailer parameters
        self.trailer_detected = False
        self.trailer_length = self.config.get('trailer_length', 5.0)  # m
        self.hitch_distance = self.config.get('hitch_distance', 0.5)  # m from rear axle
        self.max_trailer_angle = np.deg2rad(45)  # Maximum acceptable angle

        # Steering control
        self.target_trailer_angle = 0.0  # radians
        self.current_trailer_angle = 0.0
        self.steering_correction = 0.0
        self.max_steering_correction = np.deg2rad(35.0)

        # PID controller for trailer angle
        self.kp_trailer = 0.5
        self.ki_trailer = 0.1
        self.kd_trailer = 0.2
        self.trailer_angle_integral = 0.0
        self.trailer_angle_prev = 0.0

        # Guidance mode
        self.guidance_mode = 'off'  # off, auto, manual_assist
        self.target_path = None  # Desired trailer path
        self.guidance_strength = 0.0  # 0.0 to 1.0

        # Status tracking
        self.warning_active = False
        self.critical_angle = False  # Angle too extreme

        logger.info("Trailer Assistance system initialized")

    def update(self, vehicle_state: Dict, sensor_data: List[Dict],
               current_time: float, dt: float = 0.1) -> Dict:
        """
        Update trailer assistance system.

        Args:
            vehicle_state: Current vehicle state
            sensor_data: List of sensor detections
            current_time: Current simulation time (s)
            dt: Time step (s)

        Returns:
            Dictionary with trailer assistance status
        """
        current_speed = vehicle_state['velocity']['speed']

        # Detect trailer from sensor data
        self._detect_trailer(sensor_data)

        # System only active if trailer is detected and reversing
        is_reversing = current_speed < -0.5  # Negative speed = reversing
        self.active = self.enabled and self.trailer_detected and is_reversing

        if not self.active:
            self.guidance_mode = 'off'
            self.steering_correction = 0.0
            return self._get_status()

        # Update trailer angle estimation
        self._update_trailer_angle(vehicle_state, sensor_data)

        # Calculate steering correction
        if self.guidance_mode != 'off':
            self._calculate_steering_correction(dt)

        # Check for critical conditions
        self.critical_angle = abs(self.current_trailer_angle) > self.max_trailer_angle
        self.warning_active = self.critical_angle

        if self.warning_active:
            logger.warning(f"Trailer Assistance: Critical angle {np.rad2deg(self.current_trailer_angle):.1f}°")

        return self._get_status()

    def _detect_trailer(self, sensor_data: List[Dict]):
        """
        Detect if a trailer is attached.

        Args:
            sensor_data: List of sensor detections
        """
        old_trailer_state = self.trailer_detected

        # Look for rear obstacle detections or specific trailer signatures
        rear_detections = [d for d in sensor_data
                          if d.get('sensor_type') in ['radar', 'camera']
                          and d.get('azimuth', 0.0) > np.deg2rad(150)]  # Rear-facing

        if rear_detections and len(rear_detections) > 3:
            # Consistent detections suggest trailer
            self.trailer_detected = True
            self.enabled = True
        else:
            self.trailer_detected = False
            if old_trailer_state:
                logger.info("Trailer Assistance: Trailer disconnected")

    def _update_trailer_angle(self, vehicle_state: Dict,
                             sensor_data: List[Dict]):
        """
        Estimate current trailer angle from geometry and sensors.

        Args:
            vehicle_state: Current vehicle state
            sensor_data: List of sensor detections
        """
        # Trailer angle can be estimated from:
        # 1. Difference between vehicle heading and trailer hitch point direction
        # 2. Camera/radar detections of trailer edges
        # 3. Kinematic model of trailer following

        vehicle_yaw = vehicle_state['orientation']['yaw']
        vehicle_velocity = vehicle_state['velocity']
        vx = vehicle_velocity.get('vx', 0.0)
        vy = vehicle_velocity.get('vy', 0.0)

        # Simple kinematic model
        # Trailer angle changes based on steering input and speed
        steering_angle = vehicle_state.get('controls', {}).get('steering_angle', 0.0)

        # Trailer follows with delay - use simple first-order model
        trailer_angle_rate = (vx / self.trailer_length) * np.sin(
            vehicle_yaw - self.current_trailer_angle - steering_angle
        )

        # Store previous angle for derivative
        self.trailer_angle_prev = self.current_trailer_angle

        # Update angle (simplified model)
        self.current_trailer_angle += trailer_angle_rate * 0.01  # Small dt for stability

        # Clamp angle
        self.current_trailer_angle = np.clip(
            self.current_trailer_angle,
            -np.pi,
            np.pi
        )

    def _calculate_steering_correction(self, dt: float):
        """
        Calculate steering correction using PID control.

        Args:
            dt: Time step (s)
        """
        angle_error = self.target_trailer_angle - self.current_trailer_angle

        # PID control
        self.trailer_angle_integral += angle_error * dt
        angle_derivative = (self.current_trailer_angle - self.trailer_angle_prev) / max(dt, 0.001)

        correction = (self.kp_trailer * angle_error +
                     self.ki_trailer * self.trailer_angle_integral -
                     self.kd_trailer * angle_derivative)

        # Scale by guidance strength
        self.steering_correction = np.clip(
            correction * self.guidance_strength,
            -self.max_steering_correction,
            self.max_steering_correction
        )

    def set_guidance_mode(self, mode: str, strength: float = 1.0):
        """
        Set trailer guidance mode.

        Args:
            mode: 'off', 'auto', or 'manual_assist'
            strength: Guidance strength 0.0-1.0
        """
        self.guidance_mode = mode
        self.guidance_strength = np.clip(strength, 0.0, 1.0)
        logger.info(f"Trailer Assistance: Mode={mode}, Strength={self.guidance_strength:.1f}")

    def set_target_angle(self, angle: float):
        """
        Set target trailer angle.

        Args:
            angle: Target angle in radians
        """
        self.target_trailer_angle = np.clip(angle, -self.max_trailer_angle,
                                           self.max_trailer_angle)

    def enable(self):
        """Enable trailer assistance system."""
        self.enabled = True
        logger.info("Trailer Assistance enabled")

    def disable(self):
        """Disable trailer assistance system."""
        self.enabled = False
        self.active = False
        self.guidance_mode = 'off'
        logger.info("Trailer Assistance disabled")

    def _get_status(self) -> Dict:
        """Get current trailer assistance status."""
        return {
            'system': 'trailer_assistance',
            'enabled': self.enabled,
            'active': self.active,
            'trailer_detected': self.trailer_detected,
            'guidance_mode': self.guidance_mode,
            'current_trailer_angle': np.rad2deg(self.current_trailer_angle),
            'target_trailer_angle': np.rad2deg(self.target_trailer_angle),
            'steering_correction': np.rad2deg(self.steering_correction),
            'critical_angle': self.critical_angle,
            'warning_active': self.warning_active
        }


class TrailerReverseGuidance:
    """
    Trailer Reverse Guidance ADAS feature.

    Automated reverse steering control for trailers, guiding
    the vehicle-trailer combination into tight spaces.
    """

    def __init__(self, config: Dict = None):
        """
        Initialize trailer reverse guidance system.

        Args:
            config: Configuration dictionary
        """
        self.config = config or {}

        # System state
        self.enabled = False
        self.active = False
        self.guidance_active = False

        # Target path
        self.target_path = None  # List of waypoints
        self.path_index = 0
        self.path_progress = 0.0

        # Control parameters
        self.max_reverse_speed = self.config.get('max_reverse_speed', 10.0 / 3.6)
        self.steering_sensitivity = self.config.get('steering_sensitivity', 0.8)
        self.path_tolerance = self.config.get('path_tolerance', 0.2)  # m

        # Trailer reference (from TrailerAssistance)
        self.trailer_length = 5.0
        self.hitch_offset = 0.5

        logger.info("Trailer Reverse Guidance initialized")

    def update(self, vehicle_state: Dict, sensor_data: List[Dict],
               current_time: float, dt: float = 0.1) -> Dict:
        """
        Update trailer reverse guidance.

        Args:
            vehicle_state: Current vehicle state
            sensor_data: List of sensor detections
            current_time: Current simulation time (s)
            dt: Time step (s)

        Returns:
            Dictionary with guidance status
        """
        current_speed = vehicle_state['velocity']['speed']

        # Only active when reversing
        is_reversing = current_speed < -0.5
        self.active = self.enabled and is_reversing and self.guidance_active

        if not self.active or not self.target_path:
            return self._get_status()

        # Calculate steering to follow target path
        steering_command = self._calculate_path_following_steering(vehicle_state)

        return {
            'system': 'trailer_reverse_guidance',
            'enabled': self.enabled,
            'active': self.active,
            'guidance_active': self.guidance_active,
            'steering_command': steering_command,
            'path_progress': self.path_progress,
            'waypoint_index': self.path_index
        }

    def _calculate_path_following_steering(self, vehicle_state: Dict) -> float:
        """
        Calculate steering angle to follow target path.

        Args:
            vehicle_state: Current vehicle state

        Returns:
            Steering angle in radians
        """
        if not self.target_path or self.path_index >= len(self.target_path):
            return 0.0

        # Get current position
        current_pos = np.array([vehicle_state['position']['x'],
                               vehicle_state['position']['y']])

        # Get target waypoint
        target_pos = np.array(self.target_path[self.path_index])

        # Calculate cross-track error
        direction = target_pos - current_pos
        distance = np.linalg.norm(direction)

        # Move to next waypoint if close enough
        if distance < self.path_tolerance:
            self.path_index = min(self.path_index + 1, len(self.target_path) - 1)
            self.path_progress = self.path_index / len(self.target_path)

        # Simple proportional steering
        if distance > 0.01:
            angle_error = np.arctan2(direction[1], direction[0])
            steering = np.clip(angle_error * self.steering_sensitivity, -0.6, 0.6)
            return steering

        return 0.0

    def set_target_path(self, path: List[Tuple[float, float]]):
        """
        Set target path for reverse guidance.

        Args:
            path: List of (x, y) waypoints
        """
        self.target_path = path
        self.path_index = 0
        self.path_progress = 0.0
        logger.info(f"Trailer Reverse Guidance: Target path set with {len(path)} waypoints")

    def start_guidance(self):
        """Start reverse guidance."""
        self.guidance_active = True
        logger.info("Trailer Reverse Guidance: Started")

    def stop_guidance(self):
        """Stop reverse guidance."""
        self.guidance_active = False
        logger.info("Trailer Reverse Guidance: Stopped")

    def enable(self):
        """Enable system."""
        self.enabled = True

    def disable(self):
        """Disable system."""
        self.enabled = False
        self.active = False
        self.guidance_active = False

    def _get_status(self) -> Dict:
        """Get system status."""
        return {
            'system': 'trailer_reverse_guidance',
            'enabled': self.enabled,
            'active': self.active,
            'guidance_active': self.guidance_active,
            'has_target_path': self.target_path is not None,
            'path_progress': self.path_progress
        }
