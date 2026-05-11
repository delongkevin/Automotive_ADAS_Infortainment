"""
Blind Spot Detection (BSD) System

Detects vehicles in blind spots and alerts the driver.
Monitors side and rear areas that are not visible in mirrors.

Copyright Magna Electronics. All rights reserved.
"""

import numpy as np
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class BlindSpotDetection:
    """
    Blind Spot Detection (BSD) ADAS feature.

    Monitors vehicle blind spots and provides warnings when
    other vehicles are detected in these regions.
    """

    def __init__(self, config: Dict = None):
        """
        Initialize BSD system.

        Args:
            config: Configuration dictionary
        """
        self.config = config or {}

        # Detection parameters
        self.min_speed = self.config.get('min_speed', 20.0 / 3.6)  # 20 km/h
        self.max_speed = self.config.get('max_speed', 200.0 / 3.6)  # 200 km/h

        # Blind spot zones (relative to vehicle)
        # Left blind spot: -45 to -90 degrees, 1.5-5m side offset
        # Right blind spot: 45 to 90 degrees, 1.5-5m side offset
        # Rear coverage: 90-180 degrees, all distances
        self.left_zone_angle_min = -np.deg2rad(120)  # -120 degrees
        self.left_zone_angle_max = -np.deg2rad(30)   # -30 degrees
        self.left_zone_range_min = 0.5   # m
        self.left_zone_range_max = 10.0  # m

        self.right_zone_angle_min = np.deg2rad(30)   # 30 degrees
        self.right_zone_angle_max = np.deg2rad(120)  # 120 degrees
        self.right_zone_range_min = 0.5   # m
        self.right_zone_range_max = 10.0  # m

        self.rear_zone_angle_min = np.deg2rad(100)   # 100 degrees
        self.rear_zone_angle_max = np.deg2rad(260)   # 260 degrees
        self.rear_zone_range_max = 20.0  # m

        # System state
        self.enabled = True
        self.left_blind_spot_occupied = False
        self.right_blind_spot_occupied = False
        self.rear_blind_spot_occupied = False
        self.warning_active = False
        self.warning_side = None  # 'left', 'right', or 'rear'

        # Detection tracking
        self.detected_vehicles = {}  # object_id -> detection info

        logger.info("BSD system initialized")

    def update(self, vehicle_state: Dict, sensor_data: List[Dict],
               current_time: float, dt: float = 0.0) -> Dict:
        """
        Update BSD system and monitor blind spots.

        Args:
            vehicle_state: Current vehicle state
            sensor_data: List of sensor detections
            current_time: Current simulation time (s)
            dt: Simulation time step (unused, kept for interface consistency)

        Returns:
            Dictionary with BSD status and warnings
        """
        # Reset blind spot states
        self.left_blind_spot_occupied = False
        self.right_blind_spot_occupied = False
        self.rear_blind_spot_occupied = False
        self.warning_active = False
        self.warning_side = None

        # Check if system is active
        speed = vehicle_state['velocity']['speed']
        if not self.enabled or speed < self.min_speed or speed > self.max_speed:
            return self._get_status()

        # Get vehicle position and heading
        vehicle_pos = np.array([vehicle_state['position']['x'],
                               vehicle_state['position']['y']])
        vehicle_yaw = vehicle_state['orientation']['yaw']

        # Analyze each detection
        for detection in sensor_data:
            if detection.get('false_alarm', False):
                continue

            sensor_type = detection.get('sensor_type', '')
            obj_id = detection.get('object_id', 'unknown')

            # Only process radar and camera detections of vehicles
            if sensor_type not in ['radar', 'camera']:
                continue

            classification = detection.get('classification', '')
            if 'vehicle' not in classification.lower():
                continue

            # Get detection position in vehicle frame
            target_pos = np.array([detection.get('x', 0.0),
                                  detection.get('y', 0.0)])

            # Convert to ego vehicle frame
            rel_x, rel_y = self._global_to_vehicle_frame(
                target_pos, vehicle_pos, vehicle_yaw
            )

            # Calculate angle and range
            angle = np.arctan2(rel_y, rel_x)
            range_dist = np.sqrt(rel_x**2 + rel_y**2)

            # Check blind spot zones
            if self._is_in_left_zone(angle, range_dist):
                self.left_blind_spot_occupied = True
                self.warning_active = True
                self.warning_side = 'left'
                logger.info(f"BSD: Vehicle detected in LEFT blind spot")

            elif self._is_in_right_zone(angle, range_dist):
                self.right_blind_spot_occupied = True
                self.warning_active = True
                self.warning_side = 'right'
                logger.info(f"BSD: Vehicle detected in RIGHT blind spot")

            elif self._is_in_rear_zone(angle, range_dist):
                self.rear_blind_spot_occupied = True
                if not self.left_blind_spot_occupied and not self.right_blind_spot_occupied:
                    self.warning_active = True
                    self.warning_side = 'rear'
                logger.info(f"BSD: Vehicle detected in REAR zone")

            # Track detection
            self.detected_vehicles[obj_id] = {
                'angle': angle,
                'range': range_dist,
                'velocity': detection.get('velocity', 0.0),
                'timestamp': current_time
            }

        return self._get_status()

    def _is_in_left_zone(self, angle: float, range_dist: float) -> bool:
        """Check if detection is in left blind spot zone."""
        return (self.left_zone_angle_min <= angle <= self.left_zone_angle_max and
                self.left_zone_range_min <= range_dist <= self.left_zone_range_max)

    def _is_in_right_zone(self, angle: float, range_dist: float) -> bool:
        """Check if detection is in right blind spot zone."""
        return (self.right_zone_angle_min <= angle <= self.right_zone_angle_max and
                self.right_zone_range_min <= range_dist <= self.right_zone_range_max)

    def _is_in_rear_zone(self, angle: float, range_dist: float) -> bool:
        """Check if detection is in rear zone."""
        # Normalize angle to 0-360
        norm_angle = angle % (2 * np.pi)
        is_rear = (norm_angle >= self.rear_zone_angle_min or
                   norm_angle <= (self.rear_zone_angle_max - 2*np.pi))
        return is_rear and range_dist <= self.rear_zone_range_max

    def _global_to_vehicle_frame(self, global_pos: np.ndarray,
                                 vehicle_pos: np.ndarray,
                                 vehicle_yaw: float) -> tuple:
        """
        Convert global position to vehicle-centric frame.

        Args:
            global_pos: Position in global frame [x, y]
            vehicle_pos: Vehicle position in global frame [x, y]
            vehicle_yaw: Vehicle heading angle (radians)

        Returns:
            (relative_x, relative_y) in vehicle frame
        """
        # Translate to vehicle origin
        rel_pos = global_pos - vehicle_pos

        # Rotate by vehicle yaw to align with vehicle heading
        cos_yaw = np.cos(vehicle_yaw)
        sin_yaw = np.sin(vehicle_yaw)

        rel_x = rel_pos[0] * cos_yaw + rel_pos[1] * sin_yaw
        rel_y = -rel_pos[0] * sin_yaw + rel_pos[1] * cos_yaw

        return rel_x, rel_y

    def enable(self):
        """Enable BSD system."""
        self.enabled = True
        logger.info("BSD system enabled")

    def disable(self):
        """Disable BSD system."""
        self.enabled = False
        self.left_blind_spot_occupied = False
        self.right_blind_spot_occupied = False
        self.rear_blind_spot_occupied = False
        self.warning_active = False
        logger.info("BSD system disabled")

    def _get_status(self) -> Dict:
        """Get current BSD system status."""
        return {
            'system': 'blind_spot_detection',
            'enabled': self.enabled,
            'left_occupied': self.left_blind_spot_occupied,
            'right_occupied': self.right_blind_spot_occupied,
            'rear_occupied': self.rear_blind_spot_occupied,
            'warning_active': self.warning_active,
            'warning_side': self.warning_side,
            'detected_vehicles_count': len(self.detected_vehicles)
        }
