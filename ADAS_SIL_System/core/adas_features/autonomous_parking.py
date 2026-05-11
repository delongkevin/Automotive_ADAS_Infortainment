"""
Autonomous Parking System

Provides autonomous parallel and perpendicular parking assistance.
Detects parking spaces and automatically steers vehicle into space.

Copyright Magna Electronics. All rights reserved.
"""

import numpy as np
from typing import Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class AutonomousParking:
    """
    Autonomous Parking ADAS feature.

    Detects suitable parking spaces and provides automatic steering
    control to park the vehicle in parallel or perpendicular spaces.
    """

    def __init__(self, config: Dict = None):
        """
        Initialize autonomous parking system.

        Args:
            config: Configuration dictionary
        """
        self.config = config or {}

        # Parking parameters
        self.min_speed = 0.0  # m/s
        self.max_speed = self.config.get('max_speed', 20.0 / 3.6)  # 20 km/h
        self.min_space_width = self.config.get('min_space_width', 5.5)  # m (1.1x vehicle width)
        self.min_space_length = self.config.get('min_space_length', 6.0)  # m (parallel)
        self.min_perp_space_width = self.config.get('min_perp_space_width', 2.8)  # m (perpendicular)

        # Vehicle dimensions (typical sedan)
        self.vehicle_length = self.config.get('vehicle_length', 4.7)  # m
        self.vehicle_width = self.config.get('vehicle_width', 1.8)  # m
        self.wheelbase = self.config.get('wheelbase', 2.8)  # m

        # Control parameters
        self.max_steering_angle = np.deg2rad(35.0)  # degrees
        self.max_speed_parking = 10.0 / 3.6  # 10 km/h
        self.parking_tolerance = 0.1  # m (distance from slot center)

        # System state
        self.enabled = True
        self.active = False
        self.parking_type = None  # 'parallel' or 'perpendicular'
        self.detected_spaces = []  # List of available parking spaces
        self.selected_space = None
        self.parking_progress = 0.0  # 0.0 to 1.0
        self.stage = 'idle'  # idle, scanning, positioning, parking, complete

        # Control outputs
        self.target_steering_angle = 0.0
        self.target_speed = 0.0
        self.brake_active = False

        logger.info("Autonomous Parking system initialized")

    def update(self, vehicle_state: Dict, sensor_data: List[Dict],
               current_time: float, dt: float = 0.1) -> Dict:
        """
        Update autonomous parking system.

        Args:
            vehicle_state: Current vehicle state
            sensor_data: List of sensor detections
            current_time: Current simulation time (s)
            dt: Time step (s)

        Returns:
            Dictionary with parking status and control commands
        """
        current_speed = vehicle_state['velocity']['speed']

        # Check if system is active and conditions are met
        if not self.enabled or current_speed > self.max_speed:
            self.active = False
            self.stage = 'idle'
            return self._get_status()

        # Scan for parking spaces if not actively parking
        if self.stage == 'idle' or self.stage == 'scanning':
            self._scan_for_spaces(sensor_data, vehicle_state)
            self.stage = 'scanning'

            if self.selected_space is not None:
                self.stage = 'positioning'
                self.active = True
                logger.info(f"Parking space detected: {self.parking_type}")

        # Execute parking maneuver
        if self.stage == 'positioning' or self.stage == 'parking':
            self._execute_parking_maneuver(vehicle_state, current_time, dt)
            self.stage = 'parking'

        # Check if parking is complete
        if self._is_parking_complete(vehicle_state):
            self.stage = 'complete'
            self.active = False
            logger.info("Parking complete!")

        return self._get_status()

    def _scan_for_spaces(self, sensor_data: List[Dict], vehicle_state: Dict):
        """
        Scan ultrasonic/radar data for parking spaces.

        Args:
            sensor_data: List of sensor detections
            vehicle_state: Current vehicle state
        """
        self.detected_spaces = []

        # Group detections by side
        left_distances = []
        right_distances = []

        vehicle_yaw = vehicle_state['orientation']['yaw']

        for detection in sensor_data:
            sensor_type = detection.get('sensor_type', '')

            if sensor_type not in ['ultrasonic', 'radar']:
                continue

            # Classify detection side based on angle
            angle = detection.get('azimuth', 0.0)

            if -np.pi/2 < angle < 0:  # Right side
                right_distances.append(detection.get('range', float('inf')))
            elif 0 < angle < np.pi/2:  # Left side
                left_distances.append(detection.get('range', float('inf')))

        # Analyze gaps in distance measurements for parallel parking
        self._detect_parallel_spaces(left_distances, vehicle_state, 'left')
        self._detect_parallel_spaces(right_distances, vehicle_state, 'right')

        # Analyze perpendicular spaces
        self._detect_perpendicular_spaces(sensor_data, vehicle_state)

    def _detect_parallel_spaces(self, distances: List[float],
                               vehicle_state: Dict, side: str):
        """
        Detect parallel parking spaces from side distance measurements.

        Args:
            distances: List of distance measurements
            vehicle_state: Current vehicle state
            side: 'left' or 'right'
        """
        if len(distances) < 3:
            return

        # Sort and analyze for gaps (free space)
        sorted_dist = sorted(distances)
        max_gap = 0.0
        gap_start = 0.0

        for i in range(1, len(sorted_dist)):
            gap = sorted_dist[i] - sorted_dist[i-1]
            if gap > max_gap:
                max_gap = gap
                gap_start = sorted_dist[i-1]

        # If gap is large enough for parallel parking
        if max_gap >= self.min_space_length:
            space = {
                'type': 'parallel',
                'side': side,
                'position': gap_start + max_gap / 2,
                'width': max_gap,
                'vehicle_x': vehicle_state['position']['x'],
                'vehicle_y': vehicle_state['position']['y'],
                'confidence': 0.8
            }
            self.detected_spaces.append(space)

            if not self.selected_space:
                self.selected_space = space
                self.parking_type = 'parallel'

    def _detect_perpendicular_spaces(self, sensor_data: List[Dict],
                                     vehicle_state: Dict):
        """
        Detect perpendicular (head-in) parking spaces.

        Args:
            sensor_data: List of sensor detections
            vehicle_state: Current vehicle state
        """
        # Simple detection based on front clearance
        forward_clearance = self._get_forward_clearance(sensor_data)

        if forward_clearance >= self.min_perp_space_width:
            space = {
                'type': 'perpendicular',
                'position': forward_clearance / 2,
                'width': forward_clearance,
                'confidence': 0.7
            }
            self.detected_spaces.append(space)

            # Prefer perpendicular if parallel not available
            if not self.selected_space:
                self.selected_space = space
                self.parking_type = 'perpendicular'

    def _get_forward_clearance(self, sensor_data: List[Dict]) -> float:
        """Get forward clearance from front sensors."""
        min_range = float('inf')

        for detection in sensor_data:
            if detection.get('sensor_type') in ['radar', 'ultrasonic']:
                angle = detection.get('azimuth', 0.0)
                if abs(angle) < np.deg2rad(20):  # Forward-facing
                    range_val = detection.get('range', float('inf'))
                    min_range = min(min_range, range_val)

        return min_range if min_range != float('inf') else 0.0

    def _execute_parking_maneuver(self, vehicle_state: Dict,
                                 current_time: float, dt: float):
        """
        Execute the actual parking maneuver.

        Args:
            vehicle_state: Current vehicle state
            current_time: Current simulation time
            dt: Time step
        """
        if not self.selected_space:
            return

        # Simple parking control:
        # 1. Align to space
        # 2. Enter space with appropriate steering
        # 3. Straighten and center

        distance_to_space = self._calculate_distance_to_space(vehicle_state)

        if self.parking_type == 'parallel':
            self._execute_parallel_parking(vehicle_state, distance_to_space)
        elif self.parking_type == 'perpendicular':
            self._execute_perpendicular_parking(vehicle_state, distance_to_space)

        self.parking_progress = min(1.0, self.parking_progress + dt / 10.0)  # 10s to park
        self.target_speed = self.max_speed_parking

    def _execute_parallel_parking(self, vehicle_state: Dict,
                                 distance_to_space: float):
        """Execute parallel parking maneuver."""
        phase = int(self.parking_progress * 3)  # 3 phases

        if phase == 0:  # Approach and align
            self.target_steering_angle = np.deg2rad(20)  # Start at angle
        elif phase == 1:  # Enter space
            self.target_steering_angle = -np.deg2rad(30)  # Counter-steer
        else:  # Straighten and center
            self.target_steering_angle = 0.0

    def _execute_perpendicular_parking(self, vehicle_state: Dict,
                                      distance_to_space: float):
        """Execute perpendicular parking maneuver."""
        # Move forward into space with minimal steering
        self.target_steering_angle = 0.0
        self.target_speed = self.max_speed_parking

    def _calculate_distance_to_space(self, vehicle_state: Dict) -> float:
        """Calculate distance to selected parking space."""
        if not self.selected_space:
            return float('inf')

        vehicle_pos = np.array([vehicle_state['position']['x'],
                               vehicle_state['position']['y']])

        space_x = self.selected_space.get('vehicle_x', 0.0)
        space_y = self.selected_space.get('vehicle_y', 0.0)
        space_pos = np.array([space_x, space_y])

        return np.linalg.norm(space_pos - vehicle_pos)

    def _is_parking_complete(self, vehicle_state: Dict) -> bool:
        """Check if parking maneuver is complete."""
        if self.parking_progress < 0.9:
            return False

        current_speed = vehicle_state['velocity']['speed']

        # Parking complete when vehicle is stationary, aligned, and centered
        return (abs(current_speed) < 0.5 and  # Nearly stopped
                self.parking_progress >= 0.95)

    def enable(self):
        """Enable autonomous parking system."""
        self.enabled = True
        logger.info("Autonomous Parking enabled")

    def disable(self):
        """Disable autonomous parking system."""
        self.enabled = False
        self.active = False
        self.stage = 'idle'
        logger.info("Autonomous Parking disabled")

    def start_parking(self):
        """Manually trigger parking sequence."""
        if self.selected_space:
            self.active = True
            self.stage = 'positioning'
            logger.info("Starting parking maneuver")

    def cancel_parking(self):
        """Cancel ongoing parking maneuver."""
        self.active = False
        self.stage = 'idle'
        self.target_steering_angle = 0.0
        self.target_speed = 0.0
        logger.info("Parking cancelled")

    def _get_status(self) -> Dict:
        """Get current parking system status."""
        return {
            'system': 'autonomous_parking',
            'enabled': self.enabled,
            'active': self.active,
            'parking_type': self.parking_type,
            'stage': self.stage,
            'spaces_detected': len(self.detected_spaces),
            'progress': self.parking_progress,
            'target_steering_angle': self.target_steering_angle,
            'target_speed': self.target_speed,
            'brake_active': self.brake_active
        }
