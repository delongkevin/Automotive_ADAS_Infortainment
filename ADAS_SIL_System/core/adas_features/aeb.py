"""
Automatic Emergency Braking (AEB) System

Detects imminent collision and automatically applies brakes
to prevent or mitigate impact.

Copyright Magna Electronics. All rights reserved.
"""

import numpy as np
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class AutomaticEmergencyBraking:
    """
    Automatic Emergency Braking (AEB) ADAS feature.

    Monitors forward collision risk and automatically applies
    brakes when collision is imminent.
    """

    def __init__(self, config: Dict = None):
        """
        Initialize AEB system.

        Args:
            config: Configuration dictionary
        """
        self.config = config or {}

        # AEB parameters
        self.min_speed = self.config.get('min_speed', 10.0 / 3.6)  # 10 km/h
        self.max_speed = self.config.get('max_speed', 80.0 / 3.6)  # 80 km/h

        # Time-to-collision thresholds
        self.ttc_warning = self.config.get('ttc_warning', 2.5)  # seconds
        self.ttc_partial_braking = self.config.get('ttc_partial_braking', 1.5)  # seconds
        self.ttc_full_braking = self.config.get('ttc_full_braking', 0.8)  # seconds

        # Braking parameters
        self.max_deceleration = self.config.get('max_deceleration', -9.0)  # m/s^2
        self.partial_braking_decel = -4.0  # m/s^2
        self.full_braking_decel = -9.0  # m/s^2

        # State
        self.enabled = True
        self.warning_active = False
        self.braking_active = False
        self.braking_level = 0.0  # 0.0 to 1.0
        self.target_deceleration = 0.0

        # Threat tracking
        self.threat_object = None
        self.ttc = float('inf')

        logger.info("AEB system initialized")

    def update(self, vehicle_state: Dict, sensor_data: List[Dict],
               current_time: float, dt: float = 0.0) -> Dict:
        """
        Update AEB system and determine braking action.

        Args:
            vehicle_state: Current vehicle state
            sensor_data: List of sensor detections
            current_time: Current simulation time (s)
            dt: Simulation time step (unused, kept for interface consistency)

        Returns:
            Dictionary with AEB status and control commands
        """
        if not self.enabled:
            self.warning_active = False
            self.braking_active = False
            return self._get_status()

        current_speed = vehicle_state['velocity']['speed']

        # Check speed range
        if current_speed < self.min_speed or current_speed > self.max_speed:
            self.warning_active = False
            self.braking_active = False
            return self._get_status()

        # Find most critical threat
        self._find_threat(sensor_data, vehicle_state)

        # Determine action based on TTC
        if self.ttc < self.ttc_full_braking:
            # Full emergency braking
            self.warning_active = True
            self.braking_active = True
            self.braking_level = 1.0
            self.target_deceleration = self.full_braking_decel
            logger.warning(f"AEB: FULL BRAKING! TTC={self.ttc:.2f}s")

        elif self.ttc < self.ttc_partial_braking:
            # Partial braking
            self.warning_active = True
            self.braking_active = True
            self.braking_level = 0.5
            self.target_deceleration = self.partial_braking_decel
            logger.warning(f"AEB: Partial braking, TTC={self.ttc:.2f}s")

        elif self.ttc < self.ttc_warning:
            # Warning only
            self.warning_active = True
            self.braking_active = False
            self.braking_level = 0.0
            self.target_deceleration = 0.0
            logger.info(f"AEB: Warning - potential collision, TTC={self.ttc:.2f}s")

        else:
            # No threat
            self.warning_active = False
            self.braking_active = False
            self.braking_level = 0.0
            self.target_deceleration = 0.0

        return self._get_status()

    def _find_threat(self, sensor_data: List[Dict], vehicle_state: Dict):
        """
        Find most critical threat from sensor data.

        Args:
            sensor_data: List of sensor detections
            vehicle_state: Current vehicle state
        """
        current_speed = vehicle_state['velocity']['speed']

        # Filter detections in front of vehicle
        forward_detections = []

        for detection in sensor_data:
            if detection.get('false_alarm', False):
                continue

            sensor_type = detection.get('sensor_type')

            if sensor_type == 'radar':
                azimuth = detection.get('azimuth', 0.0)
                if abs(azimuth) < np.deg2rad(10.0):  # Within 10 degrees
                    forward_detections.append(detection)

            elif sensor_type == 'camera':
                if detection.get('classification') in ['vehicle', 'pedestrian']:
                    azimuth = detection.get('azimuth', 0.0)
                    if abs(azimuth) < np.deg2rad(15.0):
                        forward_detections.append(detection)

        # Calculate TTC for each detection
        min_ttc = float('inf')
        threat = None

        for detection in forward_detections:
            distance = detection.get('range', float('inf'))

            if distance < 1.0:  # Too close, already colliding
                continue

            # Get relative velocity
            if detection.get('sensor_type') == 'radar':
                radial_velocity = detection.get('radial_velocity', 0.0)
            else:
                # For camera, estimate from object tracking (simplified)
                radial_velocity = -current_speed * 0.5  # Assume object moving slower

            # Closing velocity (negative = approaching)
            closing_velocity = -radial_velocity

            if closing_velocity > 0.5:  # Approaching
                ttc = distance / closing_velocity

                if ttc < min_ttc:
                    min_ttc = ttc
                    threat = detection

        self.ttc = min_ttc
        self.threat_object = threat

    def _get_status(self) -> Dict:
        """
        Get current AEB status.

        Returns:
            Status dictionary
        """
        return {
            'feature': 'AEB',
            'enabled': self.enabled,
            'warning_active': self.warning_active,
            'braking_active': self.braking_active,
            'braking_level': self.braking_level,
            'target_deceleration': self.target_deceleration,
            'ttc': self.ttc if self.ttc != float('inf') else None,
            'threat_detected': self.threat_object is not None
        }

    def enable(self):
        """Enable AEB system."""
        self.enabled = True
        logger.info("AEB enabled")

    def disable(self):
        """Disable AEB system."""
        self.enabled = False
        self.warning_active = False
        self.braking_active = False
        logger.info("AEB disabled")
