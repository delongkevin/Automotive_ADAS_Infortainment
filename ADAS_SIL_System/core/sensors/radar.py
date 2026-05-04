"""
Radar Sensor Simulator

Simulates automotive radar sensor (typically 77 GHz or 24 GHz).
Detects range, velocity, and angle of objects.

Copyright Magna Electronics. All rights reserved.
"""

import numpy as np
from typing import Dict, List, Any
from .base_sensor import BaseSensor
import logging

logger = logging.getLogger(__name__)


class RadarSensor(BaseSensor):
    """
    Radar sensor simulator with realistic characteristics.

    Features:
    - Range and doppler velocity measurement
    - Configurable FOV and resolution
    - Weather effects simulation
    - Multi-target tracking
    """

    def __init__(self, sensor_id: str, config: Dict):
        """Initialize radar sensor with specific parameters."""
        super().__init__(sensor_id, config)

        # Radar-specific parameters
        self.frequency = config.get('frequency', 77e9)  # Hz (77 GHz)
        self.range_resolution = config.get('range_resolution', 0.5)  # m
        self.velocity_resolution = config.get('velocity_resolution', 0.1)  # m/s
        self.angular_resolution = np.deg2rad(config.get('angular_resolution', 1.0))  # rad

        # Radar Cross Section (RCS) thresholds
        self.min_rcs = config.get('min_rcs', 1.0)  # m^2

        # Weather attenuation
        self.weather_attenuation = config.get('weather_attenuation', 0.0)  # dB/km

        logger.info(f"Radar sensor {sensor_id} initialized at {self.frequency/1e9:.1f} GHz")

    def sense(self, ego_vehicle: Any, environment: Dict, current_time: float) -> List[Dict]:
        """
        Perform radar sensing of environment.

        Args:
            ego_vehicle: Ego vehicle object with state
            environment: Dictionary with 'vehicles', 'obstacles', etc.
            current_time: Current simulation time

        Returns:
            List of radar detections
        """
        # Check update rate
        if current_time - self.last_update_time < 1.0 / self.update_rate:
            return self.detections

        self.last_update_time = current_time
        self.detections = []

        if not self.enabled:
            return self.detections

        ego_state = ego_vehicle.get_state()
        ego_pos = np.array([ego_state['position']['x'],
                           ego_state['position']['y'],
                           ego_state['position']['z']])
        ego_yaw = ego_state['orientation']['yaw']
        ego_velocity = np.array([ego_state['velocity']['vx'],
                                ego_state['velocity']['vy'],
                                0.0])

        # Detect vehicles
        for vehicle in environment.get('vehicles', []):
            detection = self._detect_object(vehicle, ego_pos, ego_yaw, ego_velocity)
            if detection:
                self.detections.append(detection)

        # Detect static obstacles
        for obstacle in environment.get('obstacles', []):
            detection = self._detect_object(obstacle, ego_pos, ego_yaw, ego_velocity, is_static=True)
            if detection:
                self.detections.append(detection)

        # Generate false alarms
        if np.random.random() < self.false_alarm_rate:
            self.detections.append(self.generate_false_alarm(ego_vehicle))

        return self.detections

    def _detect_object(self, obj: Dict, ego_pos: np.ndarray, ego_yaw: float,
                      ego_velocity: np.ndarray, is_static: bool = False) -> Dict:
        """
        Detect a single object with radar.

        Args:
            obj: Object dictionary with position and velocity
            ego_pos: Ego position [x, y, z]
            ego_yaw: Ego yaw angle
            ego_velocity: Ego velocity vector
            is_static: Whether object is static

        Returns:
            Detection dictionary or None
        """
        # Object position
        obj_pos = np.array([obj['position']['x'],
                           obj['position']['y'],
                           obj['position']['z']])

        # Check if in FOV
        if not self.is_in_fov(obj_pos, ego_pos, ego_yaw):
            return None

        # Apply detection probability
        if not self.apply_detection_probability():
            return None

        # Calculate relative position in sensor frame
        dx = obj_pos[0] - ego_pos[0]
        dy = obj_pos[1] - ego_pos[1]
        dz = obj_pos[2] - ego_pos[2]

        # Rotate to ego frame
        cos_yaw = np.cos(ego_yaw)
        sin_yaw = np.sin(ego_yaw)
        dx_ego = dx * cos_yaw + dy * sin_yaw
        dy_ego = -dx * sin_yaw + dy * cos_yaw

        # Sensor frame (accounting for mounting position)
        dx_sensor = dx_ego - self.position[0]
        dy_sensor = dy_ego - self.position[1]
        dz_sensor = dz - ego_pos[2] - self.position[2]

        # Range calculation
        range_val = np.sqrt(dx_sensor**2 + dy_sensor**2 + dz_sensor**2)

        # Weather attenuation
        weather_loss = self.weather_attenuation * range_val / 1000.0
        if weather_loss > 10.0:  # Too much attenuation
            return None

        # Angles
        azimuth = np.arctan2(dy_sensor, dx_sensor)
        elevation = np.arctan2(dz_sensor, np.sqrt(dx_sensor**2 + dy_sensor**2))

        # Relative velocity (doppler)
        if is_static:
            obj_velocity = np.array([0.0, 0.0, 0.0])
        else:
            obj_velocity = np.array([obj['velocity']['vx'],
                                    obj['velocity']['vy'],
                                    0.0])

        rel_velocity = obj_velocity - ego_velocity

        # Radial velocity (doppler)
        rel_pos_norm = np.array([dx, dy, 0.0])
        if np.linalg.norm(rel_pos_norm) > 0:
            rel_pos_norm = rel_pos_norm / np.linalg.norm(rel_pos_norm)
            radial_velocity = np.dot(rel_velocity, rel_pos_norm)
        else:
            radial_velocity = 0.0

        # Create detection
        detection = {
            'sensor_id': self.sensor_id,
            'sensor_type': 'radar',
            'object_id': obj.get('id', -1),
            'timestamp': self.last_update_time,
            'range': range_val,
            'azimuth': azimuth,
            'elevation': elevation,
            'radial_velocity': radial_velocity,
            'rcs': obj.get('rcs', 10.0),  # Radar cross section
            'false_alarm': False
        }

        # Add noise
        detection = self.add_noise(detection)

        # Quantize to sensor resolution
        detection['range'] = np.round(detection['range'] / self.range_resolution) * self.range_resolution
        detection['radial_velocity'] = np.round(detection['radial_velocity'] / self.velocity_resolution) * self.velocity_resolution

        return detection
