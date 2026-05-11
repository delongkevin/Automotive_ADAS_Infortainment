"""
Traffic Sign Recognition (TSR) System

Recognizes and processes traffic signs to inform driver assistance systems.
Supports speed limits, stop signs, warning signs, and informational signs.

Copyright Magna Electronics. All rights reserved.
"""

from enum import Enum
from typing import Dict, List, Optional, Tuple
import numpy as np


class TrafficSignType(Enum):
    """Types of traffic signs recognized"""
    SPEED_LIMIT_20 = "speed_limit_20"
    SPEED_LIMIT_30 = "speed_limit_30"
    SPEED_LIMIT_40 = "speed_limit_40"
    SPEED_LIMIT_50 = "speed_limit_50"
    SPEED_LIMIT_60 = "speed_limit_60"
    SPEED_LIMIT_70 = "speed_limit_70"
    SPEED_LIMIT_80 = "speed_limit_80"
    SPEED_LIMIT_90 = "speed_limit_90"
    SPEED_LIMIT_100 = "speed_limit_100"
    SPEED_LIMIT_110 = "speed_limit_110"
    SPEED_LIMIT_120 = "speed_limit_120"
    SPEED_LIMIT_130 = "speed_limit_130"
    
    STOP_SIGN = "stop_sign"
    YIELD_SIGN = "yield_sign"
    DO_NOT_ENTER = "do_not_enter"
    ONE_WAY = "one_way"
    
    CURVE_RIGHT = "curve_right"
    CURVE_LEFT = "curve_left"
    SHARP_CURVE = "sharp_curve"
    SLIPPERY_ROAD = "slippery_road"
    PEDESTRIAN_CROSSING = "pedestrian_crossing"
    SCHOOL_ZONE = "school_zone"
    CONSTRUCTION_ZONE = "construction_zone"
    
    LANE_ENDS = "lane_ends"
    MERGE = "merge"
    EXIT = "exit"
    
    def get_speed_limit(self) -> Optional[float]:
        """Extract speed limit in km/h if this is a speed limit sign"""
        speed_map = {
            TrafficSignType.SPEED_LIMIT_20: 20.0,
            TrafficSignType.SPEED_LIMIT_30: 30.0,
            TrafficSignType.SPEED_LIMIT_40: 40.0,
            TrafficSignType.SPEED_LIMIT_50: 50.0,
            TrafficSignType.SPEED_LIMIT_60: 60.0,
            TrafficSignType.SPEED_LIMIT_70: 70.0,
            TrafficSignType.SPEED_LIMIT_80: 80.0,
            TrafficSignType.SPEED_LIMIT_90: 90.0,
            TrafficSignType.SPEED_LIMIT_100: 100.0,
            TrafficSignType.SPEED_LIMIT_110: 110.0,
            TrafficSignType.SPEED_LIMIT_120: 120.0,
            TrafficSignType.SPEED_LIMIT_130: 130.0,
        }
        return speed_map.get(self)


class TrafficSign:
    """Represents a detected traffic sign"""
    
    def __init__(
        self,
        sign_type: TrafficSignType,
        position: Tuple[float, float],
        distance: float,
        confidence: float = 1.0,
        direction: str = "ahead"
    ):
        """
        Args:
            sign_type: Type of traffic sign
            position: (x, y) position in global coordinates
            distance: Distance to sign in meters
            confidence: Detection confidence (0-1)
            direction: Direction relative to vehicle (ahead, left, right, behind)
        """
        self.sign_type = sign_type
        self.position = position
        self.distance = distance
        self.confidence = confidence
        self.direction = direction
    
    def is_speed_limit_sign(self) -> bool:
        """Check if this is a speed limit sign"""
        return "speed_limit" in self.sign_type.value


class TrafficSignRecognition:
    """
    Traffic Sign Recognition system
    
    Detects and recognizes traffic signs from camera data.
    Provides information to driver assistance features for adaptation.
    """
    
    def __init__(self, config: Dict = None):
        """
        Initialize TSR system
        
        Args:
            config: Configuration dictionary with:
                - max_detection_range: Maximum sign detection distance (default: 200m)
                - min_confidence: Minimum confidence threshold (default: 0.7)
                - update_rate: Update frequency in Hz (default: 10)
                - enable_speed_adaptation: Enable ACC speed adaptation (default: True)
                - active_sign_timeout: Time to keep active sign in memory (default: 5.0s)
        """
        self.config = config or {}
        self.enabled = False
        self.status = {
            'system': 'traffic_sign_recognition',
            'enabled': False,
            'active': False,
            'signs_detected': 0,
            'current_speed_limit': None,
            'next_speed_limit': None,
            'warning_signs': [],
            'detected_signs': [],
            'confidence': 0.0,
            'sign_distance': 0.0,
            'speed_limit_kmh': None,
            'speed_limit_mps': None
        }
        
        # Parameters
        self.max_detection_range = self.config.get('max_detection_range', 200.0)
        self.min_confidence = self.config.get('min_confidence', 0.7)
        self.update_rate = self.config.get('update_rate', 10)
        self.enable_speed_adaptation = self.config.get('enable_speed_adaptation', True)
        self.active_sign_timeout = self.config.get('active_sign_timeout', 5.0)
        
        # State tracking
        self.detected_signs: List[TrafficSign] = []
        self.current_speed_limit: Optional[float] = None
        self.last_speed_limit_update_time = 0.0
        self.warning_signs: List[TrafficSign] = []
        self.last_update_time = 0.0
    
    def enable(self) -> None:
        """Enable TSR system"""
        self.enabled = True
        self.status['enabled'] = True
    
    def disable(self) -> None:
        """Disable TSR system"""
        self.enabled = False
        self.status['enabled'] = False
    
    def update(
        self,
        vehicle_state: Dict,
        sensor_data: List[Dict],
        current_time: float,
        dt: float = 0.01
    ) -> Dict:
        """
        Update TSR system with sensor data
        
        Args:
            vehicle_state: Current vehicle state
            sensor_data: List of sensor detections
            current_time: Simulation time
            dt: Time step
        
        Returns:
            Status dictionary with TSR information
        """
        if not self.enabled:
            return self.status
        
        # Process camera/sensor data for sign detection
        signs = self._detect_signs_from_sensors(sensor_data, vehicle_state)
        
        # Update detected signs list
        self.detected_signs = signs
        
        # Extract and update speed limit
        self._update_speed_limit(current_time)
        
        # Extract and update warning signs
        self._update_warning_signs()
        
        # Update status
        self.status['active'] = len(signs) > 0
        self.status['signs_detected'] = len(signs)
        self.status['current_speed_limit'] = self.current_speed_limit
        self.status['warning_signs'] = [s.sign_type.value for s in self.warning_signs]
        self.status['detected_signs'] = [
            {
                'type': s.sign_type.value,
                'distance': s.distance,
                'confidence': s.confidence,
                'direction': s.direction
            }
            for s in self.detected_signs
        ]
        
        if self.detected_signs:
            closest_sign = min(self.detected_signs, key=lambda s: s.distance)
            self.status['confidence'] = closest_sign.confidence
            self.status['sign_distance'] = closest_sign.distance
        
        # Convert to m/s if speed limit exists
        if self.current_speed_limit:
            self.status['speed_limit_kmh'] = self.current_speed_limit
            self.status['speed_limit_mps'] = self.current_speed_limit / 3.6
        else:
            self.status['speed_limit_kmh'] = None
            self.status['speed_limit_mps'] = None
        
        self.last_update_time = current_time
        return self.status
    
    def _detect_signs_from_sensors(
        self,
        sensor_data: List[Dict],
        vehicle_state: Dict
    ) -> List[TrafficSign]:
        """
        Detect traffic signs from sensor data
        
        Args:
            sensor_data: List of sensor detections
            vehicle_state: Vehicle state
        
        Returns:
            List of detected traffic signs
        """
        detected_signs = []
        
        for detection in sensor_data:
            if detection.get('sensor_type') != 'camera':
                continue
            
            # Check if this is a traffic sign detection
            sign_class = detection.get('sign_class')
            if not sign_class:
                continue
            
            # Map detected class to TrafficSignType
            sign_type = self._classify_sign(sign_class)
            if not sign_type:
                continue
            
            # Extract detection parameters
            distance = detection.get('distance', 50.0)
            confidence = detection.get('confidence', 0.9)
            direction = detection.get('direction', 'ahead')
            x = detection.get('x', vehicle_state.get('position', [0, 0])[0])
            y = detection.get('y', vehicle_state.get('position', [0, 0])[1])
            
            # Apply filtering
            if confidence < self.min_confidence:
                continue
            
            if distance > self.max_detection_range:
                continue
            
            # Create sign object
            sign = TrafficSign(
                sign_type=sign_type,
                position=(x, y),
                distance=distance,
                confidence=confidence,
                direction=direction
            )
            
            detected_signs.append(sign)
        
        return detected_signs
    
    def _classify_sign(self, sign_class: str) -> Optional[TrafficSignType]:
        """
        Classify sign from detected class string
        
        Args:
            sign_class: Sign class string from camera
        
        Returns:
            TrafficSignType or None if unknown
        """
        # Map common sign class strings to TrafficSignType
        classification_map = {
            'speed_20': TrafficSignType.SPEED_LIMIT_20,
            'speed_30': TrafficSignType.SPEED_LIMIT_30,
            'speed_40': TrafficSignType.SPEED_LIMIT_40,
            'speed_50': TrafficSignType.SPEED_LIMIT_50,
            'speed_60': TrafficSignType.SPEED_LIMIT_60,
            'speed_70': TrafficSignType.SPEED_LIMIT_70,
            'speed_80': TrafficSignType.SPEED_LIMIT_80,
            'speed_90': TrafficSignType.SPEED_LIMIT_90,
            'speed_100': TrafficSignType.SPEED_LIMIT_100,
            'speed_110': TrafficSignType.SPEED_LIMIT_110,
            'speed_120': TrafficSignType.SPEED_LIMIT_120,
            'speed_130': TrafficSignType.SPEED_LIMIT_130,
            'stop': TrafficSignType.STOP_SIGN,
            'yield': TrafficSignType.YIELD_SIGN,
            'pedestrian': TrafficSignType.PEDESTRIAN_CROSSING,
            'construction': TrafficSignType.CONSTRUCTION_ZONE,
            'school': TrafficSignType.SCHOOL_ZONE,
            'curve_left': TrafficSignType.CURVE_LEFT,
            'curve_right': TrafficSignType.CURVE_RIGHT,
            'slippery': TrafficSignType.SLIPPERY_ROAD,
            'merge': TrafficSignType.MERGE,
            'exit': TrafficSignType.EXIT,
        }
        
        return classification_map.get(sign_class)
    
    def _update_speed_limit(self, current_time: float) -> None:
        """Extract speed limit from detected signs"""
        speed_limit_signs = [
            s for s in self.detected_signs
            if s.is_speed_limit_sign() and s.direction == 'ahead'
        ]
        
        if speed_limit_signs:
            # Get closest speed limit sign
            closest_sign = min(speed_limit_signs, key=lambda s: s.distance)
            speed_limit = closest_sign.sign_type.get_speed_limit()
            
            if speed_limit:
                self.current_speed_limit = speed_limit
                self.last_speed_limit_update_time = current_time
        else:
            # Clear speed limit if no signs detected and timeout elapsed
            if current_time - self.last_speed_limit_update_time > self.active_sign_timeout:
                self.current_speed_limit = None
    
    def _update_warning_signs(self) -> None:
        """Extract warning signs from detected signs"""
        warning_types = [
            TrafficSignType.STOP_SIGN,
            TrafficSignType.YIELD_SIGN,
            TrafficSignType.PEDESTRIAN_CROSSING,
            TrafficSignType.CONSTRUCTION_ZONE,
            TrafficSignType.SCHOOL_ZONE,
            TrafficSignType.SLIPPERY_ROAD,
            TrafficSignType.SHARP_CURVE,
            TrafficSignType.CURVE_LEFT,
            TrafficSignType.CURVE_RIGHT,
        ]
        
        self.warning_signs = [
            s for s in self.detected_signs
            if s.sign_type in warning_types and s.distance < 150.0
        ]
        
        # Sort by distance
        self.warning_signs.sort(key=lambda s: s.distance)
    
    def get_recommended_speed(self) -> Optional[float]:
        """Get recommended speed based on detected speed limit signs (m/s)"""
        if self.current_speed_limit:
            return self.current_speed_limit / 3.6
        return None
    
    def get_closest_warning_sign(self) -> Optional[TrafficSign]:
        """Get closest warning sign"""
        if self.warning_signs:
            return self.warning_signs[0]
        return None
    
    def should_stop(self) -> bool:
        """Check if vehicle should stop based on detected signs"""
        for sign in self.warning_signs:
            if sign.sign_type == TrafficSignType.STOP_SIGN and sign.distance < 30.0:
                return True
            if sign.sign_type == TrafficSignType.YIELD_SIGN and sign.distance < 25.0:
                return True
        return False
    
    def should_yield(self) -> bool:
        """Check if vehicle should yield based on detected signs"""
        for sign in self.warning_signs:
            if sign.sign_type == TrafficSignType.YIELD_SIGN and sign.distance < 40.0:
                return True
        return False
    
    def is_school_zone(self) -> bool:
        """Check if vehicle is in school zone"""
        for sign in self.detected_signs:
            if sign.sign_type == TrafficSignType.SCHOOL_ZONE and sign.distance < 100.0:
                return True
        return False
    
    def is_construction_zone(self) -> bool:
        """Check if vehicle is in construction zone"""
        for sign in self.detected_signs:
            if sign.sign_type == TrafficSignType.CONSTRUCTION_ZONE and sign.distance < 150.0:
                return True
        return False
