"""
Lane Departure Warning (LDW) System

Monitors vehicle position relative to lane markings and warns
driver when unintended lane departure is detected.

Copyright Magna Electronics. All rights reserved.
"""

import numpy as np
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class LaneDepartureWarning:
    """
    Lane Departure Warning (LDW) ADAS feature.

    Monitors lane position and provides warnings when vehicle
    drifts toward lane boundaries without turn signal active.
    """

    def __init__(self, config: Dict = None):
        """
        Initialize LDW system.

        Args:
            config: Configuration dictionary
        """
        self.config = config or {}

        # Warning thresholds
        self.warning_lateral_offset = self.config.get('warning_lateral_offset', 0.3)  # m from lane edge
        self.warning_ttb_threshold = self.config.get('warning_ttb_threshold', 0.8)  # seconds (Time To Boundary)
        self.min_speed = self.config.get('min_speed', 60.0 / 3.6)  # 60 km/h minimum

        # System state
        self.enabled = True
        self.warning_active = False
        self.warning_side = None  # 'left' or 'right'
        self.last_warning_time = 0.0
        self.warning_cooldown = 2.0  # seconds

        # Lane tracking
        self.left_lane = None
        self.right_lane = None
        self.lane_width = 3.5  # m (default)
        self.lateral_offset = 0.0  # m from lane center

        logger.info("LDW system initialized")

    def update(self, vehicle_state: Dict, sensor_data: List[Dict],
               current_time: float, dt: float = 0.0) -> Dict:
        """
        Update LDW system and generate warnings if needed.

        Args:
            vehicle_state: Current vehicle state
            sensor_data: List of sensor detections
            current_time: Current simulation time (s)
            dt: Simulation time step (unused, kept for interface consistency)

        Returns:
            Dictionary with LDW status and warnings
        """
        # Check if system is active
        speed = vehicle_state['velocity']['speed']
        if not self.enabled or speed < self.min_speed:
            self.warning_active = False
            return self._get_status()

        # Extract lane detections from camera
        lane_detections = [d for d in sensor_data
                          if d.get('detection_type') == 'lane_marking']

        if not lane_detections:
            # No lane markings detected
            self.warning_active = False
            return self._get_status()

        # Update lane information
        self._update_lanes(lane_detections)

        if self.left_lane is None or self.right_lane is None:
            self.warning_active = False
            return self._get_status()

        # Calculate lateral offset and time to boundary
        self._calculate_lateral_position(vehicle_state)

        # Check turn signal status
        turn_signal_left = vehicle_state.get('turn_signal_left', False)
        turn_signal_right = vehicle_state.get('turn_signal_right', False)

        # Determine if warning should be issued
        warning_issued = self._check_warning_conditions(
            vehicle_state,
            current_time,
            turn_signal_left,
            turn_signal_right
        )

        return self._get_status()

    def _update_lanes(self, lane_detections: List[Dict]):
        """
        Update lane marking information from detections.

        Args:
            lane_detections: List of lane marking detections
        """
        for detection in lane_detections:
            side = detection.get('side')
            if side == 'left':
                self.left_lane = detection
            elif side == 'right':
                self.right_lane = detection

    def _calculate_lateral_position(self, vehicle_state: Dict):
        """
        Calculate vehicle's lateral position within lane.

        Args:
            vehicle_state: Current vehicle state
        """
        # Simplified calculation using lane polynomial coefficients
        # In reality, this would use lane geometry and vehicle position

        # For simulation, we'll use a simplified model
        # Lateral offset: positive means right of center, negative means left

        if self.left_lane and self.right_lane:
            # Estimate lane center as midpoint
            # This is a simplification - real implementation uses polynomial curves
            left_coeff = self.left_lane.get('coefficients', [0, 0, 0, 0])
            right_coeff = self.right_lane.get('coefficients', [0, 0, 0, 0])

            # At vehicle position (x=0 in vehicle frame), evaluate lane position
            left_y = left_coeff[0]  # Lateral offset of left lane
            right_y = right_coeff[0]  # Lateral offset of right lane

            lane_center = (left_y + right_y) / 2.0
            self.lane_width = abs(left_y - right_y)

            # Vehicle lateral offset from lane center
            # (In vehicle frame, vehicle is at y=0)
            self.lateral_offset = 0.0 - lane_center

    def _check_warning_conditions(self, vehicle_state: Dict, current_time: float,
                                  turn_signal_left: bool, turn_signal_right: bool) -> bool:
        """
        Check if warning conditions are met.

        Args:
            vehicle_state: Current vehicle state
            current_time: Current time
            turn_signal_left: Left turn signal status
            turn_signal_right: Right turn signal status

        Returns:
            True if warning was issued
        """
        # Check cooldown period
        if current_time - self.last_warning_time < self.warning_cooldown:
            return False

        speed = vehicle_state['velocity']['speed']
        lateral_velocity = vehicle_state['velocity']['vy']

        # Calculate distance to lane boundaries
        dist_to_left = (self.lane_width / 2.0) - self.lateral_offset
        dist_to_right = (self.lane_width / 2.0) + self.lateral_offset

        # Calculate time to boundary (TTB)
        if abs(lateral_velocity) > 0.01:
            if lateral_velocity < 0:  # Moving left
                ttb_left = dist_to_left / abs(lateral_velocity)
                if ttb_left < self.warning_ttb_threshold and dist_to_left < self.warning_lateral_offset:
                    if not turn_signal_left:
                        self.warning_active = True
                        self.warning_side = 'left'
                        self.last_warning_time = current_time
                        logger.warning(f"LDW: Left lane departure warning! TTB={ttb_left:.2f}s")
                        return True

            elif lateral_velocity > 0:  # Moving right
                ttb_right = dist_to_right / abs(lateral_velocity)
                if ttb_right < self.warning_ttb_threshold and dist_to_right < self.warning_lateral_offset:
                    if not turn_signal_right:
                        self.warning_active = True
                        self.warning_side = 'right'
                        self.last_warning_time = current_time
                        logger.warning(f"LDW: Right lane departure warning! TTB={ttb_right:.2f}s")
                        return True

        # No warning conditions met
        self.warning_active = False
        self.warning_side = None
        return False

    def _get_status(self) -> Dict:
        """
        Get current LDW status.

        Returns:
            Status dictionary
        """
        return {
            'feature': 'LDW',
            'enabled': self.enabled,
            'warning_active': self.warning_active,
            'warning_side': self.warning_side,
            'lateral_offset': self.lateral_offset,
            'lane_width': self.lane_width,
            'left_lane_detected': self.left_lane is not None,
            'right_lane_detected': self.right_lane is not None
        }

    def enable(self):
        """Enable LDW system."""
        self.enabled = True
        logger.info("LDW enabled")

    def disable(self):
        """Disable LDW system."""
        self.enabled = False
        self.warning_active = False
        logger.info("LDW disabled")
