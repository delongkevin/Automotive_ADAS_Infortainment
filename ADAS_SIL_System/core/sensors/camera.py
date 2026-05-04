"""
Camera Sensor Simulator

Simulates automotive camera sensor with vision-based detection.
Provides object detection, classification, and lane detection.

Copyright Magna Electronics. All rights reserved.
"""

import numpy as np
from typing import Dict, List, Any
from .base_sensor import BaseSensor
import logging

logger = logging.getLogger(__name__)


class CameraSensor(BaseSensor):
    """
    Camera sensor simulator for vision-based ADAS features.

    Features:
    - Object detection and classification
    - Lane marking detection
    - Traffic sign detection
    - Lighting condition sensitivity
    """

    def __init__(self, sensor_id: str, config: Dict):
        """Initialize camera sensor with specific parameters."""
        super().__init__(sensor_id, config)

        # Camera-specific parameters
        self.resolution_width = config.get('resolution_width', 1920)
        self.resolution_height = config.get('resolution_height', 1080)
        self.focal_length = config.get('focal_length', 6.0)  # mm

        # Detection capabilities
        self.object_classes = config.get('object_classes',
                                        ['vehicle', 'pedestrian', 'bicycle', 'traffic_sign'])
        self.min_object_size = config.get('min_object_size', 0.5)  # m

        # Performance under different conditions
        self.detection_prob_day = config.get('detection_prob_day', 0.98)
        self.detection_prob_night = config.get('detection_prob_night', 0.70)
        self.detection_prob_rain = config.get('detection_prob_rain', 0.85)

        # Lane detection parameters
        self.lane_detection_enabled = config.get('lane_detection_enabled', True)
        self.lane_detection_range = config.get('lane_detection_range', 80.0)  # m

        logger.info(f"Camera sensor {sensor_id} initialized with resolution {self.resolution_width}x{self.resolution_height}")

    def sense(self, ego_vehicle: Any, environment: Dict, current_time: float) -> List[Dict]:
        """
        Perform camera sensing of environment.

        Args:
            ego_vehicle: Ego vehicle object with state
            environment: Dictionary with 'vehicles', 'obstacles', 'lanes', etc.
            current_time: Current simulation time

        Returns:
            List of camera detections
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

        # Get environmental conditions
        lighting = environment.get('lighting', 'day')  # 'day', 'night', 'twilight'
        weather = environment.get('weather', 'clear')  # 'clear', 'rain', 'fog', 'snow'

        # Adjust detection probability based on conditions
        self.detection_probability = self._get_detection_probability(lighting, weather)

        # Detect vehicles
        for vehicle in environment.get('vehicles', []):
            detection = self._detect_object(vehicle, ego_pos, ego_yaw, 'vehicle')
            if detection:
                self.detections.append(detection)

        # Detect pedestrians
        for pedestrian in environment.get('pedestrians', []):
            detection = self._detect_object(pedestrian, ego_pos, ego_yaw, 'pedestrian')
            if detection:
                self.detections.append(detection)

        # Detect traffic signs
        for sign in environment.get('traffic_signs', []):
            detection = self._detect_traffic_sign(sign, ego_pos, ego_yaw)
            if detection:
                self.detections.append(detection)

        # Detect lane markings
        if self.lane_detection_enabled:
            lane_detections = self._detect_lanes(environment.get('lanes', []), ego_pos, ego_yaw)
            self.detections.extend(lane_detections)

        return self.detections

    def _get_detection_probability(self, lighting: str, weather: str) -> float:
        """
        Calculate detection probability based on conditions.

        Args:
            lighting: Lighting condition
            weather: Weather condition

        Returns:
            Detection probability [0, 1]
        """
        # Base probability from lighting
        if lighting == 'day':
            prob = self.detection_prob_day
        elif lighting == 'night':
            prob = self.detection_prob_night
        else:  # twilight
            prob = (self.detection_prob_day + self.detection_prob_night) / 2

        # Weather degradation
        if weather in ['rain', 'snow']:
            prob *= 0.85
        elif weather == 'fog':
            prob *= 0.60

        return prob

    def _detect_object(self, obj: Dict, ego_pos: np.ndarray, ego_yaw: float,
                      obj_class: str) -> Dict:
        """
        Detect a single object with camera.

        Args:
            obj: Object dictionary
            ego_pos: Ego position
            ego_yaw: Ego yaw angle
            obj_class: Object classification

        Returns:
            Detection dictionary or None
        """
        obj_pos = np.array([obj['position']['x'],
                           obj['position']['y'],
                           obj['position']['z']])

        # Check if in FOV
        if not self.is_in_fov(obj_pos, ego_pos, ego_yaw):
            return None

        # Apply detection probability
        if not self.apply_detection_probability():
            return None

        # Calculate relative position
        dx = obj_pos[0] - ego_pos[0]
        dy = obj_pos[1] - ego_pos[1]
        dz = obj_pos[2] - ego_pos[2]

        cos_yaw = np.cos(ego_yaw)
        sin_yaw = np.sin(ego_yaw)
        dx_ego = dx * cos_yaw + dy * sin_yaw
        dy_ego = -dx * sin_yaw + dy * cos_yaw

        # Sensor frame
        dx_sensor = dx_ego - self.position[0]
        dy_sensor = dy_ego - self.position[1]
        dz_sensor = dz - ego_pos[2] - self.position[2]

        range_val = np.sqrt(dx_sensor**2 + dy_sensor**2 + dz_sensor**2)
        azimuth = np.arctan2(dy_sensor, dx_sensor)
        elevation = np.arctan2(dz_sensor, np.sqrt(dx_sensor**2 + dy_sensor**2))

        # Estimate image coordinates (normalized)
        image_x = np.tan(azimuth) / np.tan(self.fov_horizontal / 2)
        image_y = np.tan(elevation) / np.tan(self.fov_vertical / 2)

        # Estimate bounding box size (simplified)
        obj_width = obj.get('width', 1.8)
        obj_height = obj.get('height', 1.5)

        # Angular size
        angular_width = 2 * np.arctan(obj_width / (2 * range_val))
        angular_height = 2 * np.arctan(obj_height / (2 * range_val))

        # Bounding box in normalized coordinates
        bbox_width = angular_width / self.fov_horizontal
        bbox_height = angular_height / self.fov_vertical

        detection = {
            'sensor_id': self.sensor_id,
            'sensor_type': 'camera',
            'object_id': obj.get('id', -1),
            'timestamp': self.last_update_time,
            'classification': obj_class,
            'confidence': self.detection_probability * np.random.uniform(0.9, 1.0),
            'range': range_val,
            'azimuth': azimuth,
            'elevation': elevation,
            'bbox': {
                'center_x': image_x,
                'center_y': image_y,
                'width': bbox_width,
                'height': bbox_height
            },
            'false_alarm': False
        }

        return detection

    def _detect_traffic_sign(self, sign: Dict, ego_pos: np.ndarray, ego_yaw: float) -> Dict:
        """
        Detect traffic sign.

        Args:
            sign: Traffic sign dictionary
            ego_pos: Ego position
            ego_yaw: Ego yaw angle

        Returns:
            Detection dictionary or None
        """
        sign_pos = np.array([sign['position']['x'],
                            sign['position']['y'],
                            sign['position']['z']])

        if not self.is_in_fov(sign_pos, ego_pos, ego_yaw):
            return None

        if not self.apply_detection_probability():
            return None

        dx = sign_pos[0] - ego_pos[0]
        dy = sign_pos[1] - ego_pos[1]

        cos_yaw = np.cos(ego_yaw)
        sin_yaw = np.sin(ego_yaw)
        dx_ego = dx * cos_yaw + dy * sin_yaw

        range_val = np.sqrt(dx**2 + dy**2)

        detection = {
            'sensor_id': self.sensor_id,
            'sensor_type': 'camera',
            'detection_type': 'traffic_sign',
            'timestamp': self.last_update_time,
            'sign_type': sign.get('type', 'unknown'),
            'sign_value': sign.get('value', None),  # e.g., speed limit value
            'range': range_val,
            'confidence': np.random.uniform(0.85, 0.99),
            'false_alarm': False
        }

        return detection

    def _detect_lanes(self, lanes: List[Dict], ego_pos: np.ndarray, ego_yaw: float) -> List[Dict]:
        """
        Detect lane markings.

        Args:
            lanes: List of lane marking dictionaries
            ego_pos: Ego position
            ego_yaw: Ego yaw angle

        Returns:
            List of lane detections
        """
        lane_detections = []

        for lane in lanes:
            # Check if lane is visible (within range and FOV)
            # Simplified: check a few points along the lane
            lane_points = lane.get('points', [])

            if len(lane_points) < 2:
                continue

            # Check first point
            first_point = np.array(lane_points[0])
            if not self.is_in_fov(first_point, ego_pos, ego_yaw):
                continue

            # Polynomial coefficients for lane (e.g., c0 + c1*x + c2*x^2 + c3*x^3)
            coeffs = lane.get('coefficients', [0, 0, 0, 0])

            detection = {
                'sensor_id': self.sensor_id,
                'sensor_type': 'camera',
                'detection_type': 'lane_marking',
                'timestamp': self.last_update_time,
                'lane_id': lane.get('id', -1),
                'lane_type': lane.get('type', 'solid'),  # 'solid', 'dashed', etc.
                'side': lane.get('side', 'unknown'),  # 'left', 'right', 'center'
                'coefficients': coeffs,
                'confidence': np.random.uniform(0.80, 0.95),
                'false_alarm': False
            }

            lane_detections.append(detection)

        return lane_detections
