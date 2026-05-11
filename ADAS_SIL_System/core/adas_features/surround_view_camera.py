"""
Surround View Camera System

Multi-camera system providing 360-degree surround views with selectable perspectives.
Supports automated view switching based on vehicle state.

Copyright Magna Electronics. All rights reserved.
"""

import numpy as np
from typing import Dict, List, Optional
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class CameraViewMode(Enum):
    """Available camera view modes."""
    FRONT = "front"
    REAR = "rear"
    LEFT = "left"
    RIGHT = "right"
    BIRD_EYE = "bird_eye"
    PANORAMIC_FRONT = "panoramic_front"
    PANORAMIC_REAR = "panoramic_rear"
    FULL_SURROUND = "full_surround"


class SurroundViewController:
    """
    Camera view mode selection and switching controller.

    Manages view transitions, automatic mode selection, and
    camera stream prioritization based on active driving task.
    """

    def __init__(self):
        """Initialize surround view controller."""
        self.current_view = CameraViewMode.FRONT
        self.previous_view = CameraViewMode.FRONT
        self.requested_view = None
        self.transition_in_progress = False
        self.transition_progress = 0.0
        self.transition_duration = 0.3  # seconds
        self.last_transition_time = 0.0

    def request_view(self, view_mode: CameraViewMode):
        """
        Request a camera view change.

        Args:
            view_mode: Desired view mode
        """
        if view_mode != self.current_view:
            self.requested_view = view_mode
            self.transition_in_progress = True
            self.transition_progress = 0.0
            self.previous_view = self.current_view
            logger.info(f"View transition: {self.current_view.value} -> {view_mode.value}")

    def update(self, dt: float) -> bool:
        """
        Update view transition state.

        Args:
            dt: Time step (s)

        Returns:
            True if transition is in progress
        """
        if self.transition_in_progress:
            self.transition_progress += dt / self.transition_duration
            self.transition_progress = min(1.0, self.transition_progress)

            if self.transition_progress >= 1.0:
                self.current_view = self.requested_view or self.current_view
                self.transition_in_progress = False
                return False

        return self.transition_in_progress

    def get_current_view(self) -> CameraViewMode:
        """Get currently active view mode."""
        return self.current_view

    def get_blend_views(self) -> Optional[tuple]:
        """
        Get views being blended during transition.

        Returns:
            (from_view, to_view, blend_factor) or None if not transitioning
        """
        if self.transition_in_progress:
            return (self.previous_view, self.requested_view or self.current_view,
                   self.transition_progress)
        return None


class SurroundViewCamera:
    """
    Surround View Camera System ADAS feature.

    Manages multiple camera streams and provides intelligent view
    switching based on driving context and vehicle state.
    """

    def __init__(self, config: Dict = None):
        """
        Initialize surround view camera system.

        Args:
            config: Configuration dictionary
        """
        self.config = config or {}

        # System state
        self.enabled = True
        self.active = True

        # Camera configuration
        self.cameras = self._initialize_cameras()
        self.view_controller = SurroundViewController()

        # Auto-switching parameters
        self.auto_switch_enabled = self.config.get('auto_switch_enabled', True)
        self.switching_mode = 'context_aware'  # context_aware, manual, assist

        # Context state for automatic switching
        self.last_gear = 'P'  # P, R, N, D
        self.last_speed = 0.0
        self.steering_angle = 0.0
        self.turn_signal = None  # 'left', 'right', None

        # Display modes
        self.display_mode = 'single'  # single, split, pip (picture-in-picture)
        self.pip_size = 0.25  # 0.1 to 0.5 (fraction of screen)
        self.pip_position = 'bottom_right'  # Corner position

        # Recording states
        self.recordings = {}  # camera_id -> recording state
        self.all_cameras_recording = False

        logger.info("Surround View Camera system initialized")

    def _initialize_cameras(self) -> Dict[str, Dict]:
        """
        Initialize camera definitions.

        Returns:
            Dictionary of camera definitions
        """
        cameras = {
            'front': {
                'name': 'Front Camera',
                'position': [2.5, 0.0, 1.2],
                'fov_h': 50.0,  # degrees horizontal
                'fov_v': 40.0,  # degrees vertical
                'resolution': [1920, 1440],
                'frame_rate': 30,
                'enabled': True,
                'video_stream': None
            },
            'rear': {
                'name': 'Rear Camera',
                'position': [-0.8, 0.0, 0.9],
                'fov_h': 120.0,  # Wider for parking
                'fov_v': 80.0,
                'resolution': [1920, 1440],
                'frame_rate': 30,
                'enabled': True,
                'video_stream': None
            },
            'left': {
                'name': 'Left Side Camera',
                'position': [0.0, 0.95, 1.1],  # Left side mirror
                'fov_h': 70.0,
                'fov_v': 50.0,
                'resolution': [1280, 960],
                'frame_rate': 30,
                'enabled': True,
                'video_stream': None
            },
            'right': {
                'name': 'Right Side Camera',
                'position': [0.0, -0.95, 1.1],  # Right side mirror
                'fov_h': 70.0,
                'fov_v': 50.0,
                'resolution': [1280, 960],
                'frame_rate': 30,
                'enabled': True,
                'video_stream': None
            }
        }

        return cameras

    def update(self, vehicle_state: Dict, sensor_data: List[Dict],
               current_time: float, dt: float = 0.033) -> Dict:
        """
        Update surround view camera system.

        Args:
            vehicle_state: Current vehicle state
            sensor_data: List of sensor data
            current_time: Current simulation time (s)
            dt: Time step (s)

        Returns:
            Dictionary with camera and view status
        """
        if not self.enabled or not self.active:
            return self._get_status()

        # Extract vehicle state
        gear = vehicle_state.get('transmission', {}).get('gear', 'P')
        speed = vehicle_state.get('velocity', {}).get('speed', 0.0)
        steering_angle = vehicle_state.get('controls', {}).get('steering_angle', 0.0)
        turn_signal = vehicle_state.get('signals', {}).get('turn_signal', None)

        # Update automatic view switching
        if self.auto_switch_enabled and self.switching_mode == 'context_aware':
            self._update_automatic_view_switching(
                gear, speed, steering_angle, turn_signal, current_time
            )

        # Update view transition
        self.view_controller.update(dt)

        # Simulate camera frame updates
        self._update_camera_streams(current_time)

        return self._get_status()

    def _update_automatic_view_switching(self, gear: str, speed: float,
                                        steering_angle: float,
                                        turn_signal: Optional[str],
                                        current_time: float):
        """
        Automatically select view based on driving context.

        Args:
            gear: Current gear (P, R, N, D)
            speed: Current vehicle speed (m/s)
            steering_angle: Current steering angle (rad)
            turn_signal: Turn signal state
            current_time: Current simulation time
        """
        # Store history
        self.last_gear = gear
        self.last_speed = speed
        self.steering_angle = steering_angle
        self.turn_signal = turn_signal

        # Automatic view selection logic
        if gear == 'R':  # Reversing
            if abs(speed) > 2.0:  # Moving backwards faster
                self.view_controller.request_view(CameraViewMode.REAR)
            else:
                # Low speed reverse - show bird's eye for parking
                self.view_controller.request_view(CameraViewMode.BIRD_EYE)

        elif turn_signal == 'left' and abs(steering_angle) > np.deg2rad(10):
            # Turning left - show left side view
            self.view_controller.request_view(CameraViewMode.LEFT)

        elif turn_signal == 'right' and abs(steering_angle) > np.deg2rad(10):
            # Turning right - show right side view
            self.view_controller.request_view(CameraViewMode.RIGHT)

        elif abs(steering_angle) > np.deg2rad(20):
            # Sharp turn - panoramic view
            if steering_angle > 0:
                self.view_controller.request_view(CameraViewMode.PANORAMIC_FRONT)
            else:
                self.view_controller.request_view(CameraViewMode.PANORAMIC_FRONT)

        elif speed < 5.0 / 3.6:  # Less than 5 km/h - low speed maneuver
            self.view_controller.request_view(CameraViewMode.FULL_SURROUND)

        else:  # Normal driving
            self.view_controller.request_view(CameraViewMode.FRONT)

    def _update_camera_streams(self, current_time: float):
        """
        Simulate camera stream updates.

        Args:
            current_time: Current simulation time
        """
        for camera_id, camera in self.cameras.items():
            if camera['enabled']:
                # Simulate frame capture at specified frame rate
                frame_period = 1.0 / camera['frame_rate']
                if current_time % frame_period < 0.001:  # Just captured a frame
                    camera['last_frame_time'] = current_time

    def set_view_mode(self, view_mode: CameraViewMode):
        """
        Manually request a specific view mode.

        Args:
            view_mode: Desired view mode
        """
        self.view_controller.request_view(view_mode)
        self.auto_switch_enabled = False  # Disable auto-switching on manual request
        logger.info(f"Manual view selection: {view_mode.value}")

    def set_display_mode(self, mode: str):
        """
        Set display mode for camera output.

        Args:
            mode: 'single', 'split', or 'pip'
        """
        if mode in ['single', 'split', 'pip']:
            self.display_mode = mode
            logger.info(f"Display mode: {mode}")

    def enable_auto_switching(self, enable: bool = True):
        """
        Enable/disable automatic view switching.

        Args:
            enable: True to enable auto-switching
        """
        self.auto_switch_enabled = enable
        self.switching_mode = 'context_aware' if enable else 'manual'
        logger.info(f"Auto-switching: {enable}")

    def select_cameras_for_display(self, camera_list: List[str]):
        """
        Select which cameras to display.

        Args:
            camera_list: List of camera IDs to display
        """
        for cam_id in self.cameras:
            self.cameras[cam_id]['display_enabled'] = cam_id in camera_list
        logger.info(f"Display cameras: {camera_list}")

    def start_recording(self, camera_id: str = None):
        """
        Start recording from camera(s).

        Args:
            camera_id: Specific camera ID, or None for all
        """
        if camera_id:
            if camera_id in self.cameras:
                self.recordings[camera_id] = {'started': True, 'frames': 0}
                logger.info(f"Recording started: {camera_id}")
        else:
            for cam_id in self.cameras:
                self.recordings[cam_id] = {'started': True, 'frames': 0}
            self.all_cameras_recording = True
            logger.info("Recording started: All cameras")

    def stop_recording(self, camera_id: str = None):
        """
        Stop recording from camera(s).

        Args:
            camera_id: Specific camera ID, or None for all
        """
        if camera_id:
            if camera_id in self.recordings:
                del self.recordings[camera_id]
                logger.info(f"Recording stopped: {camera_id}")
        else:
            self.recordings.clear()
            self.all_cameras_recording = False
            logger.info("Recording stopped: All cameras")

    def enable(self):
        """Enable system."""
        self.enabled = True
        self.active = True
        logger.info("Surround View Camera enabled")

    def disable(self):
        """Disable system."""
        self.enabled = False
        self.active = False
        logger.info("Surround View Camera disabled")

    def _get_status(self) -> Dict:
        """Get current system status."""
        current_view = self.view_controller.get_current_view()
        blend_info = self.view_controller.get_blend_views()

        return {
            'system': 'surround_view_camera',
            'enabled': self.enabled,
            'active': self.active,
            'current_view': current_view.value if current_view else 'front',
            'transitioning': self.view_controller.transition_in_progress,
            'blend_views': blend_info,
            'auto_switching': self.auto_switch_enabled,
            'display_mode': self.display_mode,
            'cameras_enabled': sum(1 for c in self.cameras.values() if c['enabled']),
            'cameras_recording': len(self.recordings),
            'total_cameras': len(self.cameras)
        }
