"""
ADAS SIL System - Unit Tests

Basic unit tests for core components.

Copyright Magna Electronics. All rights reserved.
"""

import pytest
import numpy as np
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from ADAS_SIL_System.simulator import ADASSILSimulator
from core.vehicle_dynamics import VehicleDynamics
from core.sensors import RadarSensor, CameraSensor
from core.adas_features import (
    LaneDepartureWarning,
    AdaptiveCruiseControl,
    AutomaticEmergencyBraking,
    BlindSpotDetection,
    AutonomousParking,
    TrailerAssistance,
    TrailerReverseGuidance,
    SurroundViewCamera,
    CameraViewMode
)


class TestVehicleDynamics:
    """Test vehicle dynamics simulation."""

    def test_initialization(self):
        """Test vehicle initialization."""
        vehicle = VehicleDynamics()
        assert vehicle.mass > 0
        assert vehicle.wheelbase > 0

    def test_reset_state(self):
        """Test state reset."""
        vehicle = VehicleDynamics()
        vehicle.x = 100.0
        vehicle.vx = 20.0
        vehicle.reset_state()
        assert vehicle.x == 0.0
        assert vehicle.vx == 0.0

    def test_set_state(self):
        """Test setting vehicle state."""
        vehicle = VehicleDynamics()
        vehicle.set_state(x=10.0, y=5.0, yaw=np.pi/4, vx=15.0)
        assert vehicle.x == 10.0
        assert vehicle.y == 5.0
        assert vehicle.yaw == np.pi/4
        assert vehicle.vx == 15.0

    def test_update(self):
        """Test vehicle dynamics update."""
        vehicle = VehicleDynamics()
        vehicle.set_controls(throttle=0.5, brake=0.0, steering_angle=0.0)

        initial_x = vehicle.x
        vehicle.update(dt=0.1)

        # Vehicle should have moved forward
        assert vehicle.vx > 0
        assert vehicle.x > initial_x

    def test_configured_steering_angle_accepts_degrees(self):
        """Test steering angle config is interpreted correctly."""
        vehicle = VehicleDynamics({'max_steering_angle': 35.0})
        vehicle.set_controls(throttle=0.0, brake=0.0, steering_angle=10.0)
        assert vehicle.steering_angle == pytest.approx(np.deg2rad(35.0))


class TestRadarSensor:
    """Test radar sensor."""

    def test_initialization(self):
        """Test radar sensor initialization."""
        config = {
            'position': [3.0, 0.0, 0.5],
            'max_range': 200.0,
            'fov_horizontal': 20.0
        }
        sensor = RadarSensor('test_radar', config)
        assert sensor.sensor_id == 'test_radar'
        assert sensor.max_range == 200.0

    def test_fov_check(self):
        """Test field of view checking."""
        config = {
            'position': [0.0, 0.0, 0.0],
            'max_range': 100.0,
            'min_range': 1.0,
            'fov_horizontal': 20.0,
            'fov_vertical': 10.0
        }
        sensor = RadarSensor('test_radar', config)

        # Object directly in front - should be in FOV
        assert sensor.is_in_fov(
            np.array([50.0, 0.0, 0.0]),
            np.array([0.0, 0.0, 0.0]),
            0.0
        )

        # Object too far to the side - should not be in FOV
        assert not sensor.is_in_fov(
            np.array([50.0, 50.0, 0.0]),
            np.array([0.0, 0.0, 0.0]),
            0.0
        )

    def test_rcs_threshold_filters_detections(self):
        """Test weak radar targets are filtered by minimum RCS."""
        vehicle = VehicleDynamics()
        sensor = RadarSensor('test_radar', {
            'position': [0.0, 0.0, 0.0],
            'max_range': 100.0,
            'fov_horizontal': 20.0,
            'fov_vertical': 10.0,
            'detection_probability': 1.0,
            'false_alarm_rate': 0.0,
            'update_rate': 1.0,
            'min_rcs': 20.0
        })
        sensor.last_update_time = -1.0

        detections = sensor.sense(vehicle, {
            'vehicles': [{
                'id': 1,
                'position': {'x': 30.0, 'y': 0.0, 'z': 0.0},
                'velocity': {'vx': 0.0, 'vy': 0.0, 'vz': 0.0},
                'rcs': 10.0
            }],
            'obstacles': []
        }, 0.0)

        assert detections == []


class TestCameraSensor:
    """Test camera sensor behavior."""

    def test_lane_detection_uses_coefficients_without_points(self):
        """Test lane detection works when scenarios only provide polynomial coefficients."""
        sensor = CameraSensor('test_camera', {
            'position': [0.0, 0.0, 0.0],
            'max_range': 100.0,
            'fov_horizontal': 50.0,
            'fov_vertical': 30.0
        })

        detections = sensor._detect_lanes(
            [{
                'id': 1,
                'type': 'dashed',
                'side': 'left',
                'coefficients': [1.75, 0.0, 0.0, 0.0],
                'points': []
            }],
            np.array([0.0, 0.0, 0.0]),
            0.0
        )

        assert len(detections) == 1
        assert detections[0]['coefficients'][0] == pytest.approx(1.75)


class TestADASFeatures:
    """Test ADAS feature implementations."""

    def test_ldw_initialization(self):
        """Test LDW initialization."""
        ldw = LaneDepartureWarning()
        assert ldw.enabled == True
        assert ldw.warning_active == False

    def test_acc_initialization(self):
        """Test ACC initialization."""
        acc = AdaptiveCruiseControl()
        assert acc.enabled == False
        assert acc.active == False

    def test_aeb_initialization(self):
        """Test AEB initialization."""
        aeb = AutomaticEmergencyBraking()
        assert aeb.enabled == True
        assert aeb.braking_active == False

    def test_acc_enable_disable(self):
        """Test ACC enable/disable."""
        acc = AdaptiveCruiseControl()

        # Enable ACC at valid speed
        acc.enable(current_speed=20.0)
        assert acc.enabled == True

        # Disable ACC
        acc.disable()
        assert acc.enabled == False
        assert acc.active == False


class TestSimulator:
    """Test simulator integration behavior."""

    def test_step_accepts_mixed_feature_signatures_and_processes_events(self):
        """Test simulator steps without TypeError and applies scenario events."""
        simulator = ADASSILSimulator({
            'dt': 0.1,
            'vehicle': {'max_steering_angle': 35.0},
            'sensors': {
                'front_radar': {
                    'enabled': True,
                    'position': [0.0, 0.0, 0.0],
                    'max_range': 100.0,
                    'min_range': 0.5,
                    'fov_horizontal': 20.0,
                    'fov_vertical': 10.0,
                    'update_rate': 50.0,
                    'detection_probability': 1.0,
                    'false_alarm_rate': 0.0
                },
                'front_camera': {
                    'enabled': True,
                    'position': [0.0, 0.0, 0.0],
                    'max_range': 100.0,
                    'min_range': 0.5,
                    'fov_horizontal': 50.0,
                    'fov_vertical': 30.0,
                    'update_rate': 50.0,
                    'detection_probability': 1.0
                }
            }
        })
        simulator.load_scenario({
            'name': 'event_test',
            'initial_conditions': {
                'ego_vehicle': {'position': [0.0, 0.0, 0.0], 'velocity': 20.0, 'yaw': 0.0}
            },
            'environment': {
                'vehicles': [{
                    'id': 1,
                    'position': {'x': 10.0, 'y': 0.0, 'z': 0.0},
                    'velocity': {'vx': 5.0, 'vy': 0.0, 'vz': 0.0},
                    'rcs': 25.0
                }],
                'lanes': [
                    {'id': 1, 'type': 'dashed', 'side': 'left', 'coefficients': [1.75, 0.0, 0.0, 0.0], 'points': []},
                    {'id': 2, 'type': 'solid', 'side': 'right', 'coefficients': [-1.75, 0.0, 0.0, 0.0], 'points': []}
                ]
            },
            'events': [{
                'time': 0.0,
                'type': 'vehicle_acceleration',
                'vehicle_id': 1,
                'acceleration': 1.0,
                'duration': 0.2
            }]
        })

        simulator.step()
        lead_vehicle = simulator.environment['vehicles'][0]
        assert lead_vehicle['velocity']['vx'] > 5.0


class TestBlindSpotDetection:
    """Test Blind Spot Detection feature."""

    def test_bsd_initialization(self):
        """Test BSD system initialization."""
        bsd = BlindSpotDetection()
        assert bsd.enabled == True
        assert bsd.left_blind_spot_occupied == False
        assert bsd.right_blind_spot_occupied == False
        assert bsd.rear_blind_spot_occupied == False

    def test_bsd_enable_disable(self):
        """Test BSD enable/disable functionality."""
        bsd = BlindSpotDetection()
        bsd.disable()
        assert bsd.enabled == False

        bsd.enable()
        assert bsd.enabled == True

    def test_bsd_vehicle_detection(self):
        """Test BSD detects vehicles in blind spots."""
        bsd = BlindSpotDetection()
        vehicle_state = {
            'position': {'x': 0.0, 'y': 0.0},
            'orientation': {'yaw': 0.0},
            'velocity': {'speed': 20.0}
        }

        # Simulated detection in left blind spot
        sensor_data = [{
            'sensor_type': 'radar',
            'classification': 'vehicle',
            'x': -3.0,  # 3m to the left
            'y': 2.0,   # 2m forward
            'velocity': 10.0,
            'false_alarm': False,
            'object_id': 'vehicle_1'
        }]

        status = bsd.update(vehicle_state, sensor_data, 0.0)
        assert status['system'] == 'blind_spot_detection'
        assert status['enabled'] == True


class TestAutonomousParking:
    """Test Autonomous Parking feature."""

    def test_parking_initialization(self):
        """Test parking system initialization."""
        parking = AutonomousParking()
        assert parking.enabled == True
        assert parking.active == False
        assert parking.stage == 'idle'

    def test_parking_space_detection(self):
        """Test parking space detection capability."""
        parking = AutonomousParking()
        vehicle_state = {
            'position': {'x': 0.0, 'y': 0.0},
            'orientation': {'yaw': 0.0},
            'velocity': {'speed': 5.0}
        }

        sensor_data = [
            {
                'sensor_type': 'ultrasonic',
                'azimuth': np.pi/4,  # Right side
                'range': 8.0
            },
            {
                'sensor_type': 'ultrasonic',
                'azimuth': np.pi/4,
                'range': 8.0
            }
        ]

        status = parking.update(vehicle_state, sensor_data, 0.0, 0.01)
        assert status['system'] == 'autonomous_parking'
        assert status['enabled'] == True

    def test_parking_enable_disable(self):
        """Test parking system enable/disable."""
        parking = AutonomousParking()
        parking.disable()
        assert parking.enabled == False

        parking.enable()
        assert parking.enabled == True


class TestTrailerAssistance:
    """Test Trailer Assistance feature."""

    def test_trailer_assistance_initialization(self):
        """Test trailer assistance initialization."""
        trailer = TrailerAssistance()
        assert trailer.enabled == False  # Waits for trailer detection
        assert trailer.active == False

    def test_trailer_angle_estimation(self):
        """Test trailer angle estimation."""
        trailer = TrailerAssistance()
        vehicle_state = {
            'position': {'x': 0.0, 'y': 0.0},
            'orientation': {'yaw': 0.0},
            'velocity': {'vx': -2.0, 'vy': 0.0, 'speed': 2.0},
            'controls': {'steering_angle': 0.0}
        }

        sensor_data = [
            {
                'sensor_type': 'radar',
                'azimuth': np.pi,  # Rear
                'range': 3.0
            }
        ]

        status = trailer.update(vehicle_state, sensor_data, 0.0, 0.01)
        assert status['system'] == 'trailer_assistance'

    def test_trailer_guidance_mode_setting(self):
        """Test setting trailer guidance mode."""
        trailer = TrailerAssistance()
        trailer.set_guidance_mode('auto', strength=0.8)
        assert trailer.guidance_mode == 'auto'
        assert trailer.guidance_strength == 0.8


class TestTrailerReverseGuidance:
    """Test Trailer Reverse Guidance feature."""

    def test_reverse_guidance_initialization(self):
        """Test reverse guidance initialization."""
        guidance = TrailerReverseGuidance()
        assert guidance.enabled == False
        assert guidance.active == False

    def test_reverse_guidance_path_following(self):
        """Test path following logic."""
        guidance = TrailerReverseGuidance()

        path = [(0.0, 0.0), (2.0, 1.0), (4.0, 2.0)]
        guidance.set_target_path(path)
        assert guidance.target_path == path
        assert guidance.path_index == 0

    def test_reverse_guidance_enable_disable(self):
        """Test guidance enable/disable."""
        guidance = TrailerReverseGuidance()
        guidance.enable()
        assert guidance.enabled == True

        guidance.disable()
        assert guidance.enabled == False


class TestSurroundViewCamera:
    """Test Surround View Camera system."""

    def test_surround_view_initialization(self):
        """Test surround view initialization."""
        svc = SurroundViewCamera()
        assert svc.enabled == True
        assert svc.active == True
        assert len(svc.cameras) == 5  # Front, rear, left, right, cargo

    def test_camera_view_switching(self):
        """Test camera view mode switching."""
        svc = SurroundViewCamera()
        svc.set_view_mode(CameraViewMode.REAR)
        assert svc.view_controller.requested_view == CameraViewMode.REAR

    def test_auto_switching_modes(self):
        """Test automatic view switching modes."""
        svc = SurroundViewCamera()
        svc.enable_auto_switching(True)
        assert svc.auto_switch_enabled == True

        svc.enable_auto_switching(False)
        assert svc.auto_switch_enabled == False

    def test_display_mode_selection(self):
        """Test display mode selection."""
        svc = SurroundViewCamera()
        svc.set_display_mode('pip')
        assert svc.display_mode == 'pip'

    def test_camera_recording(self):
        """Test camera recording functionality."""
        svc = SurroundViewCamera()
        svc.start_recording('front')
        assert 'front' in svc.recordings

        svc.stop_recording('front')
        assert 'front' not in svc.recordings

    def test_surround_view_with_vehicle_state(self):
        """Test surround view update with vehicle state."""
        svc = SurroundViewCamera()
        vehicle_state = {
            'position': {'x': 0.0, 'y': 0.0},
            'orientation': {'yaw': 0.0},
            'velocity': {'speed': 0.0},
            'transmission': {'gear': 'R'},
            'controls': {'steering_angle': 0.0},
            'signals': {'turn_signal': None}
        }

        status = svc.update(vehicle_state, [], 0.0, 0.033)
        assert status['system'] == 'surround_view_camera'
        assert status['enabled'] == True


class TestSurroundViewCameraAllViews:
    """Test all camera view modes with complete coverage."""

    def test_all_view_modes_exist(self):
        """Test all camera view modes are defined."""
        svc = SurroundViewCamera()
        
        # Test all view modes are accessible
        assert CameraViewMode.FRONT
        assert CameraViewMode.REAR
        assert CameraViewMode.LEFT
        assert CameraViewMode.RIGHT
        assert CameraViewMode.CARGO  # Truck bed / cargo area
        assert CameraViewMode.BIRD_EYE
        assert CameraViewMode.PANORAMIC_FRONT
        assert CameraViewMode.PANORAMIC_REAR
        assert CameraViewMode.FULL_SURROUND

    def test_all_cameras_initialized(self):
        """Test all cameras are properly initialized."""
        svc = SurroundViewCamera()
        
        # Verify we have 5 cameras now (including cargo)
        assert len(svc.cameras) == 5
        
        # Verify each camera has required properties
        required_props = ['name', 'position', 'fov_h', 'fov_v', 'resolution', 'frame_rate', 'enabled']
        for cam_name, cam_config in svc.cameras.items():
            assert cam_name in ['front', 'rear', 'left', 'right', 'cargo']
            for prop in required_props:
                assert prop in cam_config

    def test_cargo_camera_config(self):
        """Test cargo camera is properly configured."""
        svc = SurroundViewCamera()
        
        assert 'cargo' in svc.cameras
        cargo_cam = svc.cameras['cargo']
        assert cargo_cam['enabled'] == True
        assert cargo_cam['name'] == 'Cargo Area / Truck Bed Camera'
        assert cargo_cam['fov_h'] == 100.0
        assert cargo_cam['fov_v'] == 75.0

    def test_front_view_mode(self):
        """Test front camera view mode."""
        svc = SurroundViewCamera()
        svc.set_view_mode(CameraViewMode.FRONT)
        svc.view_controller.update(0.5)
        assert svc.view_controller.current_view == CameraViewMode.FRONT

    def test_rear_view_mode(self):
        """Test rear camera view mode."""
        svc = SurroundViewCamera()
        svc.set_view_mode(CameraViewMode.REAR)
        svc.view_controller.update(0.5)
        assert svc.view_controller.current_view == CameraViewMode.REAR

    def test_left_view_mode(self):
        """Test left side camera view mode."""
        svc = SurroundViewCamera()
        svc.set_view_mode(CameraViewMode.LEFT)
        svc.view_controller.update(0.5)
        assert svc.view_controller.current_view == CameraViewMode.LEFT

    def test_right_view_mode(self):
        """Test right side camera view mode."""
        svc = SurroundViewCamera()
        svc.set_view_mode(CameraViewMode.RIGHT)
        svc.view_controller.update(0.5)
        assert svc.view_controller.current_view == CameraViewMode.RIGHT

    def test_cargo_view_mode(self):
        """Test cargo area camera view mode."""
        svc = SurroundViewCamera()
        svc.set_view_mode(CameraViewMode.CARGO)
        svc.view_controller.update(0.5)
        assert svc.view_controller.current_view == CameraViewMode.CARGO

    def test_bird_eye_view_mode(self):
        """Test bird's eye (top-down) view mode."""
        svc = SurroundViewCamera()
        svc.set_view_mode(CameraViewMode.BIRD_EYE)
        svc.view_controller.update(0.5)
        assert svc.view_controller.current_view == CameraViewMode.BIRD_EYE

    def test_panoramic_front_view_mode(self):
        """Test panoramic front view mode."""
        svc = SurroundViewCamera()
        svc.set_view_mode(CameraViewMode.PANORAMIC_FRONT)
        svc.view_controller.update(0.5)
        assert svc.view_controller.current_view == CameraViewMode.PANORAMIC_FRONT

    def test_panoramic_rear_view_mode(self):
        """Test panoramic rear view mode."""
        svc = SurroundViewCamera()
        svc.set_view_mode(CameraViewMode.PANORAMIC_REAR)
        svc.view_controller.update(0.5)
        assert svc.view_controller.current_view == CameraViewMode.PANORAMIC_REAR

    def test_full_surround_view_mode(self):
        """Test full surround view mode (all cameras)."""
        svc = SurroundViewCamera()
        svc.set_view_mode(CameraViewMode.FULL_SURROUND)
        svc.view_controller.update(0.5)
        assert svc.view_controller.current_view == CameraViewMode.FULL_SURROUND

    def test_auto_switch_to_rear_when_reversing(self):
        """Test automatic switch to rear view when reversing."""
        svc = SurroundViewCamera()
        vehicle_state = {
            'position': {'x': 0.0, 'y': 0.0},
            'orientation': {'yaw': 0.0},
            'velocity': {'speed': 3.0},  # Moving backwards fast
            'transmission': {'gear': 'R'},
            'controls': {'steering_angle': 0.0},
            'signals': {'turn_signal': None}
        }

        svc.enable_auto_switching(True)
        svc.update(vehicle_state, [], 0.0, 0.033)
        # After update, should have requested rear view
        assert svc.view_controller.requested_view == CameraViewMode.REAR

    def test_auto_switch_to_bird_eye_when_parking(self):
        """Test automatic switch to bird's eye when parking (low speed reverse)."""
        svc = SurroundViewCamera()
        vehicle_state = {
            'position': {'x': 0.0, 'y': 0.0},
            'orientation': {'yaw': 0.0},
            'velocity': {'speed': 0.5},  # Slow reverse for parking
            'transmission': {'gear': 'R'},
            'controls': {'steering_angle': 0.0},
            'signals': {'turn_signal': None}
        }

        svc.enable_auto_switching(True)
        svc.update(vehicle_state, [], 0.0, 0.033)
        assert svc.view_controller.requested_view == CameraViewMode.BIRD_EYE

    def test_auto_switch_to_cargo_when_parked(self):
        """Test automatic switch to cargo view when vehicle is parked."""
        svc = SurroundViewCamera()
        vehicle_state = {
            'position': {'x': 0.0, 'y': 0.0},
            'orientation': {'yaw': 0.0},
            'velocity': {'speed': 0.0},
            'transmission': {'gear': 'P'},  # Parked
            'controls': {'steering_angle': 0.0},
            'signals': {'turn_signal': None}
        }

        svc.enable_auto_switching(True)
        svc.update(vehicle_state, [], 0.0, 0.033)
        assert svc.view_controller.requested_view == CameraViewMode.CARGO

    def test_auto_switch_left_view_on_left_turn(self):
        """Test automatic switch to left view when turning left."""
        svc = SurroundViewCamera()
        vehicle_state = {
            'position': {'x': 0.0, 'y': 0.0},
            'orientation': {'yaw': 0.0},
            'velocity': {'speed': 10.0},
            'transmission': {'gear': 'D'},
            'controls': {'steering_angle': np.deg2rad(25)},  # Left turn
            'signals': {'turn_signal': 'left'}
        }

        svc.enable_auto_switching(True)
        svc.update(vehicle_state, [], 0.0, 0.033)
        assert svc.view_controller.requested_view == CameraViewMode.LEFT

    def test_auto_switch_right_view_on_right_turn(self):
        """Test automatic switch to right view when turning right."""
        svc = SurroundViewCamera()
        vehicle_state = {
            'position': {'x': 0.0, 'y': 0.0},
            'orientation': {'yaw': 0.0},
            'velocity': {'speed': 10.0},
            'transmission': {'gear': 'D'},
            'controls': {'steering_angle': np.deg2rad(-25)},  # Right turn
            'signals': {'turn_signal': 'right'}
        }

        svc.enable_auto_switching(True)
        svc.update(vehicle_state, [], 0.0, 0.033)
        assert svc.view_controller.requested_view == CameraViewMode.RIGHT

    def test_auto_switch_to_front_normal_driving(self):
        """Test automatic switch to front view during normal driving."""
        svc = SurroundViewCamera()
        # Start with a different view
        svc.set_view_mode(CameraViewMode.REAR)
        svc.view_controller.update(0.5)
        
        vehicle_state = {
            'position': {'x': 0.0, 'y': 0.0},
            'orientation': {'yaw': 0.0},
            'velocity': {'speed': 25.0},
            'transmission': {'gear': 'D'},
            'controls': {'steering_angle': 0.0},
            'signals': {'turn_signal': None}
        }

        svc.enable_auto_switching(True)
        svc.update(vehicle_state, [], 0.0, 0.033)
        # Should request front view
        assert svc.view_controller.requested_view == CameraViewMode.FRONT or \
               svc.view_controller.current_view == CameraViewMode.FRONT

    def test_all_views_with_blind_spot_detection(self):
        """Test all camera views work with blind spot detection enabled."""
        svc = SurroundViewCamera()
        bsd = BlindSpotDetection()
        bsd.enable()

        for view_mode in [CameraViewMode.FRONT, CameraViewMode.REAR, CameraViewMode.LEFT, 
                         CameraViewMode.RIGHT, CameraViewMode.CARGO, CameraViewMode.BIRD_EYE]:
            svc.set_view_mode(view_mode)
            vehicle_state = {
                'position': {'x': 0.0, 'y': 0.0},
                'orientation': {'yaw': 0.0},
                'velocity': {'speed': 20.0}
            }
            sensor_data = []
            
            svc_status = svc.update(vehicle_state, sensor_data, 0.0, 0.033)
            bsd_status = bsd.update(vehicle_state, sensor_data, 0.0)
            
            assert svc_status['enabled'] == True
            assert bsd_status['enabled'] == True

    def test_all_views_with_autonomous_parking(self):
        """Test all camera views work with autonomous parking enabled."""
        svc = SurroundViewCamera()
        parking = AutonomousParking()
        parking.enable()

        for view_mode in [CameraViewMode.FRONT, CameraViewMode.REAR, CameraViewMode.LEFT, 
                         CameraViewMode.RIGHT, CameraViewMode.CARGO, CameraViewMode.BIRD_EYE]:
            svc.set_view_mode(view_mode)
            vehicle_state = {
                'position': {'x': 0.0, 'y': 0.0},
                'orientation': {'yaw': 0.0},
                'velocity': {'speed': 5.0}
            }
            sensor_data = []
            
            svc_status = svc.update(vehicle_state, sensor_data, 0.0, 0.033)
            parking_status = parking.update(vehicle_state, sensor_data, 0.0, 0.01)
            
            assert svc_status['enabled'] == True
            assert parking_status['enabled'] == True

    def test_all_views_with_trailer_assistance(self):
        """Test all camera views work with trailer assistance enabled."""
        svc = SurroundViewCamera()
        trailer = TrailerAssistance()
        trailer.enable()

        for view_mode in [CameraViewMode.FRONT, CameraViewMode.REAR, CameraViewMode.LEFT, 
                         CameraViewMode.RIGHT, CameraViewMode.CARGO, CameraViewMode.BIRD_EYE]:
            svc.set_view_mode(view_mode)
            vehicle_state = {
                'position': {'x': 0.0, 'y': 0.0},
                'orientation': {'yaw': 0.0},
                'velocity': {'vx': -2.0, 'vy': 0.0, 'speed': 2.0},
                'controls': {'steering_angle': 0.0}
            }
            sensor_data = []
            
            svc_status = svc.update(vehicle_state, sensor_data, 0.0, 0.033)
            trailer_status = trailer.update(vehicle_state, sensor_data, 0.0, 0.01)
            
            assert svc_status['enabled'] == True
            assert trailer_status['enabled'] == True

    def test_view_transition_smooth(self):
        """Test smooth transition between views."""
        svc = SurroundViewCamera()
        svc.set_view_mode(CameraViewMode.FRONT)
        svc.view_controller.update(1.0)
        
        # Verify we're on front view
        assert svc.view_controller.current_view == CameraViewMode.FRONT
        
        # Switch to rear
        svc.set_view_mode(CameraViewMode.REAR)
        assert svc.view_controller.transition_in_progress == True
        
        # Partially complete transition
        svc.view_controller.update(0.15)
        assert svc.view_controller.transition_progress > 0.0
        assert svc.view_controller.transition_progress < 1.0
        
        # Fully complete transition
        svc.view_controller.update(1.0)
        assert svc.view_controller.current_view == CameraViewMode.REAR
        assert svc.view_controller.transition_in_progress == False


class TestIntegratedADASFeatures:
    """Test integration of multiple ADAS features."""

    def test_simulator_with_new_features(self):
        """Test simulator can initialize and run with new features."""
        simulator = ADASSILSimulator({
            'dt': 0.01,
            'vehicle': {'max_steering_angle': 35.0},
            'adas': {
                'ldw': {'enabled': True},
                'acc': {'enabled': True},
                'aeb': {'enabled': True},
                'bsd': {'enabled': True},
                'parking': {'enabled': True},
                'trailer': {'enabled': True},
                'surround_view': {'enabled': True}
            },
            'sensors': {
                'front_radar': {
                    'enabled': True,
                    'position': [0.0, 0.0, 0.0],
                    'max_range': 100.0,
                    'min_range': 0.5,
                    'fov_horizontal': 20.0,
                    'fov_vertical': 10.0,
                    'update_rate': 50.0,
                    'detection_probability': 1.0,
                    'false_alarm_rate': 0.0
                },
                'front_camera': {
                    'enabled': True,
                    'position': [0.0, 0.0, 0.0],
                    'max_range': 100.0,
                    'min_range': 0.5,
                    'fov_horizontal': 50.0,
                    'fov_vertical': 30.0,
                    'update_rate': 50.0,
                    'detection_probability': 1.0
                }
            }
        })

        # Verify all features are initialized
        assert 'ldw' in simulator.adas_features
        assert 'acc' in simulator.adas_features
        assert 'aeb' in simulator.adas_features
        assert 'bsd' in simulator.adas_features
        assert 'parking' in simulator.adas_features
        assert 'trailer_assistance' in simulator.adas_features
        assert 'trailer_reverse' in simulator.adas_features
        assert 'surround_view' in simulator.adas_features

        # Load and step scenario
        simulator.load_scenario({
            'name': 'integration_test',
            'initial_conditions': {
                'ego_vehicle': {'position': [0.0, 0.0, 0.0], 'velocity': 10.0, 'yaw': 0.0}
            },
            'environment': {'vehicles': [], 'lanes': []}
        })

        simulator.step()
        assert simulator.current_time > 0.0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
