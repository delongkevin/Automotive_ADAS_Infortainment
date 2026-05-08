"""
Base Sensor Class

Defines the abstract base class for all sensor types in the ADAS SIL system.

Copyright Magna Electronics. All rights reserved.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any
import numpy as np
import logging

logger = logging.getLogger(__name__)


class BaseSensor(ABC):
    """
    Abstract base class for all sensor types.

    Provides common functionality for:
    - Sensor placement and orientation
    - Field of view calculations
    - Detection filtering
    - Noise modeling
    """

    def __init__(self, sensor_id: str, config: Dict):
        """
        Initialize base sensor.

        Args:
            sensor_id: Unique identifier for this sensor
            config: Sensor configuration dictionary
        """
        self.sensor_id = sensor_id
        self.config = config

        # Mounting position relative to vehicle center (m)
        self.position = np.array(config.get('position', [0.0, 0.0, 0.0]))

        # Mounting orientation (roll, pitch, yaw in radians)
        self.orientation = np.array(config.get('orientation', [0.0, 0.0, 0.0]))

        # Sensor characteristics
        self.max_range = config.get('max_range', 100.0)  # m
        self.min_range = config.get('min_range', 0.5)  # m
        self.fov_horizontal = np.deg2rad(config.get('fov_horizontal', 60.0))  # rad
        self.fov_vertical = np.deg2rad(config.get('fov_vertical', 20.0))  # rad

        # Performance parameters
        self.update_rate = config.get('update_rate', 10.0)  # Hz
        self.detection_probability = config.get('detection_probability', 0.95)
        self.false_alarm_rate = config.get('false_alarm_rate', 0.01)

        # Noise parameters
        self.range_noise_std = config.get('range_noise_std', 0.1)  # m
        self.angle_noise_std = np.deg2rad(config.get('angle_noise_std', 0.5))  # rad
        self.velocity_noise_std = config.get('velocity_noise_std', 0.2)  # m/s

        # State
        self.enabled = True
        self.last_update_time = 0.0
        self.detections = []

        logger.info(f"Initialized {self.__class__.__name__} sensor: {sensor_id}")

    @abstractmethod
    def sense(self, ego_vehicle: Any, environment: Dict, current_time: float) -> List[Dict]:
        """
        Perform sensor measurement.

        Args:
            ego_vehicle: Ego vehicle object with state information
            environment: Dictionary containing environment objects
            current_time: Current simulation time (s)

        Returns:
            List of detection dictionaries
        """
        pass

    def is_in_fov(self, position: np.ndarray, ego_position: np.ndarray, ego_yaw: float) -> bool:
        """
        Check if a position is within sensor field of view.

        Args:
            position: Target position [x, y, z] in world frame
            ego_position: Ego vehicle position [x, y, z]
            ego_yaw: Ego vehicle yaw angle (rad)

        Returns:
            True if position is in FOV
        """
        # Transform target to ego vehicle frame
        dx = position[0] - ego_position[0]
        dy = position[1] - ego_position[1]
        dz = position[2] - ego_position[2]

        # Rotate to ego frame
        cos_yaw = np.cos(ego_yaw)
        sin_yaw = np.sin(ego_yaw)

        dx_ego = dx * cos_yaw + dy * sin_yaw
        dy_ego = -dx * sin_yaw + dy * cos_yaw
        dz_ego = dz

        # Transform to sensor frame
        dx_sensor = dx_ego - self.position[0]
        dy_sensor = dy_ego - self.position[1]
        dz_sensor = dz_ego - self.position[2]

        # Calculate range and angles
        range_xy = np.sqrt(dx_sensor**2 + dy_sensor**2)
        total_range = np.sqrt(dx_sensor**2 + dy_sensor**2 + dz_sensor**2)

        # Check range
        if total_range < self.min_range or total_range > self.max_range:
            return False

        # Check horizontal FOV
        horizontal_angle = np.arctan2(dy_sensor, dx_sensor)
        if abs(horizontal_angle) > self.fov_horizontal / 2:
            return False

        # Check vertical FOV
        vertical_angle = np.arctan2(dz_sensor, range_xy)
        if abs(vertical_angle) > self.fov_vertical / 2:
            return False

        return True

    def add_noise(self, detection: Dict) -> Dict:
        """
        Add sensor noise to detection.

        Args:
            detection: Clean detection dictionary

        Returns:
            Detection with added noise
        """
        noisy_detection = detection.copy()

        # Add range noise
        if 'range' in noisy_detection:
            noisy_detection['range'] += np.random.normal(0, self.range_noise_std)
            noisy_detection['range'] = max(self.min_range, noisy_detection['range'])

        # Add angle noise
        if 'azimuth' in noisy_detection:
            noisy_detection['azimuth'] += np.random.normal(0, self.angle_noise_std)

        if 'elevation' in noisy_detection:
            noisy_detection['elevation'] += np.random.normal(0, self.angle_noise_std)

        # Add velocity noise
        for key in ('velocity', 'radial_velocity'):
            if key in noisy_detection:
                noisy_detection[key] += np.random.normal(0, self.velocity_noise_std)

        return noisy_detection

    def apply_detection_probability(self) -> bool:
        """
        Simulate detection probability.

        Returns:
            True if detection occurs
        """
        return np.random.random() < self.detection_probability

    def generate_false_alarm(self, ego_vehicle: Any) -> Dict:
        """
        Generate a false alarm detection.

        Args:
            ego_vehicle: Ego vehicle object

        Returns:
            False alarm detection dictionary
        """
        # Random position within sensor FOV
        range_fa = np.random.uniform(self.min_range, self.max_range)
        azimuth_fa = np.random.uniform(-self.fov_horizontal/2, self.fov_horizontal/2)
        elevation_fa = np.random.uniform(-self.fov_vertical/2, self.fov_vertical/2)

        return {
            'sensor_id': self.sensor_id,
            'object_id': -1,  # Negative ID indicates false alarm
            'range': range_fa,
            'azimuth': azimuth_fa,
            'elevation': elevation_fa,
            'velocity': np.random.uniform(-10, 10),
            'false_alarm': True
        }

    def get_sensor_position_world(self, ego_position: np.ndarray, ego_yaw: float) -> np.ndarray:
        """
        Get sensor position in world coordinates.

        Args:
            ego_position: Ego vehicle position [x, y, z]
            ego_yaw: Ego vehicle yaw angle (rad)

        Returns:
            Sensor position in world frame [x, y, z]
        """
        cos_yaw = np.cos(ego_yaw)
        sin_yaw = np.sin(ego_yaw)

        # Rotate sensor position to world frame
        x_world = ego_position[0] + self.position[0] * cos_yaw - self.position[1] * sin_yaw
        y_world = ego_position[1] + self.position[0] * sin_yaw + self.position[1] * cos_yaw
        z_world = ego_position[2] + self.position[2]

        return np.array([x_world, y_world, z_world])

    def get_info(self) -> Dict:
        """
        Get sensor information and current state.

        Returns:
            Dictionary with sensor information
        """
        return {
            'sensor_id': self.sensor_id,
            'type': self.__class__.__name__,
            'enabled': self.enabled,
            'position': self.position.tolist(),
            'orientation': self.orientation.tolist(),
            'max_range': self.max_range,
            'fov_horizontal': np.rad2deg(self.fov_horizontal),
            'fov_vertical': np.rad2deg(self.fov_vertical),
            'update_rate': self.update_rate,
            'num_detections': len(self.detections)
        }
