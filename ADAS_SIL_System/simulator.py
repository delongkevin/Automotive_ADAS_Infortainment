"""
Main ADAS SIL Simulator

Integrates all components into a complete simulation system.

Copyright Magna Electronics. All rights reserved.
"""

import numpy as np
import copy
from typing import Dict, List, Optional
import logging
import time

from .core.vehicle_dynamics import VehicleDynamics
from .core.sensors import RadarSensor, CameraSensor
from .core.adas_features import (
    LaneDepartureWarning,
    AdaptiveCruiseControl,
    AutomaticEmergencyBraking,
    BlindSpotDetection,
    AutonomousParking,
    TrailerAssistance,
    TrailerReverseGuidance,
    SurroundViewCamera,
    TrafficSignRecognition
)

logger = logging.getLogger(__name__)


class ADASSILSimulator:
    """
    Complete ADAS Software-in-the-Loop Simulator.

    Integrates vehicle dynamics, sensors, and ADAS features
    into a unified simulation environment.
    """

    def __init__(self, config: Dict = None):
        """
        Initialize ADAS SIL simulator.

        Args:
            config: Configuration dictionary
        """
        self.config = config or {}

        # Simulation parameters
        self.dt = self.config.get('dt', 0.01)  # 100 Hz default
        self.current_time = 0.0
        self.is_running = False

        # Initialize vehicle
        vehicle_config = self.config.get('vehicle', {})
        self.vehicle = VehicleDynamics(vehicle_config)

        # Initialize sensors
        self.sensors = {}
        self._initialize_sensors()

        # Initialize ADAS features
        self.adas_features = {}
        self._initialize_adas_features()

        # Environment
        self.environment = self._create_default_environment()
        self.scenario_events = []
        self.next_event_index = 0

        # Data logging
        self.log_data = []
        self.max_log_entries = 10000

        logger.info("ADAS SIL Simulator initialized")

    def _create_default_environment(self) -> Dict:
        """Create a fresh default environment state."""
        return {
            'vehicles': [],
            'pedestrians': [],
            'obstacles': [],
            'traffic_signs': [],
            'lanes': [],
            'lighting': 'day',
            'weather': 'clear'
        }

    def _initialize_sensors(self):
        """Initialize sensor suite."""
        sensors_config = self.config.get('sensors', {})

        # Front radar
        if sensors_config.get('front_radar', {}).get('enabled', True):
            radar_config = sensors_config.get('front_radar', {})
            radar_config.setdefault('position', [3.0, 0.0, 0.5])
            radar_config.setdefault('max_range', 200.0)
            radar_config.setdefault('fov_horizontal', 20.0)
            self.sensors['front_radar'] = RadarSensor('front_radar', radar_config)

        # Side / rear radars for BSD coverage
        if sensors_config.get('left_radar', {}).get('enabled', True):
            left_cfg = dict(sensors_config.get('left_radar', {}))
            left_cfg.setdefault('position', [0.0, 0.9, 0.5])
            left_cfg.setdefault('orientation', [0.0, 0.0, np.deg2rad(90)])
            left_cfg.setdefault('max_range', 40.0)
            left_cfg.setdefault('fov_horizontal', 120.0)
            self.sensors['left_radar'] = RadarSensor('left_radar', left_cfg)

        if sensors_config.get('right_radar', {}).get('enabled', True):
            right_cfg = dict(sensors_config.get('right_radar', {}))
            right_cfg.setdefault('position', [0.0, -0.9, 0.5])
            right_cfg.setdefault('orientation', [0.0, 0.0, np.deg2rad(-90)])
            right_cfg.setdefault('max_range', 40.0)
            right_cfg.setdefault('fov_horizontal', 120.0)
            self.sensors['right_radar'] = RadarSensor('right_radar', right_cfg)

        if sensors_config.get('rear_radar', {}).get('enabled', True):
            rear_cfg = dict(sensors_config.get('rear_radar', {}))
            rear_cfg.setdefault('position', [-2.0, 0.0, 0.5])
            rear_cfg.setdefault('orientation', [0.0, 0.0, np.pi])
            rear_cfg.setdefault('max_range', 60.0)
            rear_cfg.setdefault('fov_horizontal', 80.0)
            self.sensors['rear_radar'] = RadarSensor('rear_radar', rear_cfg)

        # Front camera
        if sensors_config.get('front_camera', {}).get('enabled', True):
            camera_config = sensors_config.get('front_camera', {})
            camera_config.setdefault('position', [2.5, 0.0, 1.2])
            camera_config.setdefault('max_range', 150.0)
            camera_config.setdefault('fov_horizontal', 50.0)
            camera_config.setdefault('lane_detection_enabled', True)
            self.sensors['front_camera'] = CameraSensor('front_camera', camera_config)

        logger.info(f"Initialized {len(self.sensors)} sensors")

    def _initialize_adas_features(self):
        """Initialize ADAS features."""
        adas_config = self.config.get('adas', {})

        # Lane Departure Warning
        if adas_config.get('ldw', {}).get('enabled', True):
            self.adas_features['ldw'] = LaneDepartureWarning(adas_config.get('ldw', {}))

        # Adaptive Cruise Control
        if adas_config.get('acc', {}).get('enabled', True):
            self.adas_features['acc'] = AdaptiveCruiseControl(adas_config.get('acc', {}))

        # Automatic Emergency Braking
        if adas_config.get('aeb', {}).get('enabled', True):
            self.adas_features['aeb'] = AutomaticEmergencyBraking(adas_config.get('aeb', {}))

        # Blind Spot Detection
        if adas_config.get('bsd', {}).get('enabled', False):
            self.adas_features['bsd'] = BlindSpotDetection(adas_config.get('bsd', {}))

        # Autonomous Parking
        if adas_config.get('parking', {}).get('enabled', False):
            self.adas_features['parking'] = AutonomousParking(adas_config.get('parking', {}))

        # Trailer Assistance
        trailer_cfg = adas_config.get('trailer', {})
        trailer_assist_cfg = adas_config.get('trailer_assistance', trailer_cfg)
        trailer_reverse_cfg = adas_config.get('trailer_reverse', trailer_cfg)
        trailer_enabled = (
            trailer_cfg.get('enabled', False)
            or trailer_assist_cfg.get('enabled', False)
            or trailer_reverse_cfg.get('enabled', False)
        )
        if trailer_enabled:
            self.adas_features['trailer_assistance'] = TrailerAssistance(trailer_assist_cfg)
            self.adas_features['trailer_reverse'] = TrailerReverseGuidance(trailer_reverse_cfg)

        # Surround View Camera
        if adas_config.get('surround_view', {}).get('enabled', False):
            self.adas_features['surround_view'] = SurroundViewCamera(adas_config.get('surround_view', {}))

        # Traffic Sign Recognition
        if adas_config.get('tsr', {}).get('enabled', False):
            self.adas_features['tsr'] = TrafficSignRecognition(adas_config.get('tsr', {}))

        logger.info(f"Initialized {len(self.adas_features)} ADAS features")

    def load_scenario(self, scenario: Dict):
        """
        Load a test scenario.

        Args:
            scenario: Scenario dictionary with initial conditions and events
        """
        logger.info(f"Loading scenario: {scenario.get('name', 'Unnamed')}")

        # Reset simulation
        self.reset()

        # Set initial vehicle state (engine format)
        initial_conditions = scenario.get('initial_conditions', {})
        ego_init = initial_conditions.get('ego_vehicle', {})

        # Also accept MIL-style vehicle_config
        vehicle_config = scenario.get('vehicle_config', {})
        if not ego_init and vehicle_config:
            pos = vehicle_config.get('initial_position', [0.0, 0.0])
            if isinstance(pos, dict):
                pos = [pos.get('x', 0.0), pos.get('y', 0.0)]
            ego_init = {
                'position': list(pos) + ([0.0] if len(pos) < 3 else []),
                'velocity': float(vehicle_config.get('initial_speed', 0.0)),
                'yaw': float(vehicle_config.get('initial_yaw', 0.0)),
                'gear': vehicle_config.get('gear', 'R' if vehicle_config.get('has_trailer') else 'D'),
            }

        if 'position' in ego_init:
            pos = ego_init['position']
            vel = ego_init.get('velocity', 0.0)
            yaw = ego_init.get('yaw', 0.0)
            self.vehicle.set_state(pos[0], pos[1], yaw, vel)

        if 'gear' in ego_init:
            self.vehicle.set_gear(ego_init['gear'])
        elif vehicle_config.get('has_trailer'):
            # Trailer assist demos typically reverse
            pass  # keep D unless scenario sets R via events

        # Set environment
        self.environment.update(copy.deepcopy(scenario.get('environment', {})))
        # Normalize environment vehicles list if missing
        self.environment.setdefault('vehicles', [])
        self.environment.setdefault('traffic_signs', [])
        self.environment.setdefault('lanes', [])

        # Load scenario events
        self.scenario_events = sorted(
            copy.deepcopy(scenario.get('events', [])),
            key=lambda event: event.get('time', 0.0)
        )
        self.next_event_index = 0

        # Activate features that were configured enabled (ACC/TSR honor runtime enable)
        self._activate_configured_features()

        logger.info("Scenario loaded successfully")

    def _activate_configured_features(self):
        """Enable ADAS features whose config requested enabled=True."""
        vehicle_state = self.vehicle.get_state()
        speed = vehicle_state['velocity']['speed']
        longitudinal = vehicle_state['velocity'].get('longitudinal', speed)

        if 'acc' in self.adas_features:
            acc = self.adas_features['acc']
            if getattr(acc, 'enabled', False) or self.config.get('adas', {}).get('acc', {}).get('enabled', True):
                # Bootstrap ACC with current (or set) speed so control loop runs
                enable_speed = speed if speed >= getattr(acc, 'min_speed', 0) else max(speed, acc.set_speed)
                acc.enable(enable_speed if enable_speed > 0 else acc.set_speed)

        if 'tsr' in self.adas_features:
            tsr = self.adas_features['tsr']
            if not tsr.enabled:
                tsr.enable()

        if 'bsd' in self.adas_features:
            self.adas_features['bsd'].enable()

        if 'trailer_assistance' in self.adas_features:
            assist = self.adas_features['trailer_assistance']
            if hasattr(assist, 'enable'):
                assist.enable()
            # Trailer scenarios typically start in reverse
            ego_init_gear = (
                (self.config.get('vehicle') or {}).get('gear')
            )
            # Scenario may request reverse via initial conditions elsewhere; default keep D

        if 'parking' in self.adas_features:
            parking = self.adas_features['parking']
            if hasattr(parking, 'enable') and not getattr(parking, 'enabled', True):
                parking.enable()

        # Apply gear from scenario initial conditions if present on environment/meta
        _ = longitudinal  # reserved for future reverse bootstrap

    def reset(self):
        """Reset simulation to initial state."""
        self.current_time = 0.0
        self.vehicle.reset_state()
        self.log_data = []
        self.environment = self._create_default_environment()
        self.scenario_events = []
        self.next_event_index = 0

        for sensor in self.sensors.values():
            sensor.last_update_time = 0.0
            sensor.detections = []

        self.adas_features = {}
        self._initialize_adas_features()

        logger.info("Simulation reset")

    def step(self):
        """
        Execute one simulation step.
        """
        self._process_scenario_events()
        self._update_environment_actors()

        # Collect sensor data
        sensor_data = []
        for sensor in self.sensors.values():
            detections = sensor.sense(self.vehicle, self.environment, self.current_time)
            sensor_data.extend(detections)

        # Get vehicle state
        vehicle_state = self.vehicle.get_state()

        # Update ADAS features
        adas_status = {}
        for name, feature in self.adas_features.items():
            status = feature.update(vehicle_state, sensor_data, self.current_time, self.dt)
            adas_status[name] = status

        # Determine vehicle control inputs
        throttle, brake, steering = self._compute_vehicle_controls(adas_status, vehicle_state)

        # Apply controls to vehicle
        self.vehicle.set_controls(throttle, brake, steering)

        # Update vehicle dynamics
        self.vehicle.update(self.dt)

        # Log data
        self._log_step(vehicle_state, sensor_data, adas_status)

        # Update time
        self.current_time += self.dt

    def _process_scenario_events(self):
        """Apply all scenario events scheduled for the current simulation time."""
        while self.next_event_index < len(self.scenario_events):
            event = self.scenario_events[self.next_event_index]
            if event.get('time', 0.0) > self.current_time + 1e-9:
                break

            self._apply_scenario_event(event)
            self.next_event_index += 1

    def _apply_scenario_event(self, event: Dict):
        """Apply a single scenario event to an environment actor or ego vehicle."""
        event_type = event.get('type')

        # Ego gear / motion helpers used by parking & trailer scenarios
        if event_type == 'ego_gear':
            gear = event.get('gear', 'D')
            self.vehicle.set_gear(gear)
            return
        if event_type == 'ego_controls':
            self.vehicle.set_controls(
                event.get('throttle', 0.0),
                event.get('brake', 0.0),
                event.get('steering_angle', 0.0),
            )
            return

        # Spawn / approach helper for BSD scenarios (MIL-style event)
        if event_type == 'vehicle_approaching':
            params = event.get('parameters') or event.get('params') or event
            side = str(params.get('side', 'left')).lower()
            speed = float(params.get('speed', params.get('approach_speed', 20.0)))
            distance = float(params.get('initial_distance', 40.0))
            # Place adjacent-lane traffic relative to ego
            ego = self.vehicle.get_state()
            ex = ego['position']['x']
            ey = ego['position']['y']
            yaw = ego['orientation']['yaw']
            # Lateral offset ~ one lane (~3.5m); longitudinal behind for blind spot
            if side == 'left':
                lat = 3.5
                long_offset = -8.0
            elif side == 'right':
                lat = -3.5
                long_offset = -8.0
            else:  # rear
                lat = 0.0
                long_offset = -min(distance, 25.0)

            cos_y, sin_y = np.cos(yaw), np.sin(yaw)
            # Body frame: +x forward, +y left
            wx = ex + long_offset * cos_y - lat * sin_y
            wy = ey + long_offset * sin_y + lat * cos_y
            # Match ego forward speed so relative motion stays in zone briefly
            ego_speed = ego['velocity'].get('longitudinal', ego['velocity']['speed'])
            vx_world = ego_speed * cos_y  # approximate; actors only use vx along world +x today
            # Prefer actor motion along ego heading by storing both vx/vy
            vehicles = self.environment.setdefault('vehicles', [])
            vehicles.append({
                'id': params.get('vehicle_id', event.get('vehicle_id', 9000 + len(vehicles))),
                'position': {'x': wx, 'y': wy, 'z': 0.0},
                'velocity': {
                    'vx': float(speed if abs(yaw) < 0.2 else speed * cos_y),
                    'vy': float(0.0 if abs(yaw) < 0.2 else speed * sin_y),
                    'vz': 0.0,
                },
                'dimensions': params.get('dimensions', {'length': 4.5, 'width': 1.8, 'height': 1.5}),
                'classification': 'vehicle',
            })
            return

        # Ignore MIL validation / feature_command here (handled by MIL runner)
        if event_type in ('validation', 'feature_command', 'environment_setup', 'vehicle_motion'):
            # Best-effort vehicle_motion for ego
            if event_type == 'vehicle_motion':
                params = event.get('parameters') or event.get('params') or {}
                if 'gear' in params:
                    self.vehicle.set_gear(params['gear'])
                if 'steering_angle' in params:
                    self.vehicle.set_controls(
                        self.vehicle.throttle,
                        self.vehicle.brake,
                        float(params['steering_angle']),
                    )
                if 'speed_target' in params:
                    target = float(params['speed_target'])
                    # Approximate by setting vx toward target
                    self.vehicle.vx = target
                if 'acceleration' in params and event.get('vehicle_id') is not None:
                    vehicle = self._find_vehicle(event.get('vehicle_id'))
                    if vehicle is not None:
                        vehicle['acceleration'] = float(params['acceleration'])
                        duration = params.get('duration')
                        vehicle['acceleration_end_time'] = (
                            self.current_time + duration if duration is not None else None
                        )
            return

        vehicle = self._find_vehicle(event.get('vehicle_id'))
        if vehicle is None:
            logger.warning(f"Scenario event target not found: {event}")
            return

        if event_type == 'vehicle_acceleration':
            vehicle['acceleration'] = event.get('acceleration', 0.0)
            duration = event.get('duration')
            vehicle['acceleration_end_time'] = (
                self.current_time + duration if duration is not None else None
            )
        elif event_type == 'vehicle_emergency_brake':
            vehicle['acceleration'] = event.get('deceleration', -8.0)
            vehicle['acceleration_end_time'] = None
        else:
            logger.warning(f"Unsupported scenario event type: {event_type}")

    def _find_vehicle(self, vehicle_id: Optional[int]) -> Optional[Dict]:
        """Find an environment vehicle by id."""
        for vehicle in self.environment.get('vehicles', []):
            if vehicle.get('id') == vehicle_id:
                return vehicle
        return None

    def _update_environment_actors(self):
        """Advance simple kinematics for environment vehicles."""
        for vehicle in self.environment.get('vehicles', []):
            velocity = vehicle.setdefault('velocity', {'vx': 0.0, 'vy': 0.0, 'vz': 0.0})
            position = vehicle.setdefault('position', {'x': 0.0, 'y': 0.0, 'z': 0.0})

            acceleration = vehicle.get('acceleration', 0.0)
            acceleration_end_time = vehicle.get('acceleration_end_time')
            if acceleration_end_time is not None and self.current_time >= acceleration_end_time:
                acceleration = 0.0
                vehicle.pop('acceleration', None)
                vehicle.pop('acceleration_end_time', None)

            velocity['vx'] = max(0.0, velocity.get('vx', 0.0) + acceleration * self.dt)
            position['x'] += velocity['vx'] * self.dt
            position['y'] += velocity.get('vy', 0.0) * self.dt
            position['z'] += velocity.get('vz', 0.0) * self.dt

    def _compute_vehicle_controls(self, adas_status: Dict, vehicle_state: Dict) -> tuple:
        """
        Compute vehicle control inputs based on ADAS commands.

        Priority: AEB > parking > trailer reverse > ACC longitudinal.
        Lateral: parking / trailer steering when active.

        Args:
            adas_status: Status from all ADAS features
            vehicle_state: Current vehicle state

        Returns:
            Tuple of (throttle, brake, steering)
        """
        throttle = 0.0
        brake = 0.0
        steering = 0.0

        # AEB has highest priority
        if 'aeb' in adas_status and adas_status['aeb'].get('braking_active'):
            brake = adas_status['aeb'].get('braking_level', 1.0)
            return throttle, brake, steering

        # Autonomous parking controls (when maneuver active)
        parking = adas_status.get('parking') or {}
        if parking.get('active'):
            target_speed = float(parking.get('target_speed', 0.0))
            current_speed = float(vehicle_state['velocity'].get('speed', 0.0))
            steering = float(parking.get('target_steering_angle', 0.0))
            if parking.get('brake_active'):
                brake = 0.6
            elif target_speed > current_speed + 0.2:
                throttle = min((target_speed - current_speed) / 2.0, 0.4)
            elif target_speed < current_speed - 0.2:
                brake = min((current_speed - target_speed) / 3.0, 0.5)
            return throttle, brake, steering

        # Trailer reverse steering correction (status reports degrees for TrailerAssistance)
        trailer = adas_status.get('trailer_assistance') or {}
        trailer_rev = adas_status.get('trailer_reverse') or {}
        if trailer.get('active') or trailer_rev.get('active'):
            if trailer.get('active'):
                steering = np.deg2rad(float(trailer.get('steering_correction', 0.0)))
            else:
                # TrailerReverseGuidance may expose steering differently
                steering = float(trailer_rev.get('steering_angle', trailer_rev.get('steering_correction', 0.0)))
                if abs(steering) > np.pi:
                    steering = np.deg2rad(steering)
            gear = vehicle_state.get('gear') or (vehicle_state.get('transmission') or {}).get('gear')
            if gear == 'R' and vehicle_state['velocity'].get('speed', 0) < 1.0:
                throttle = 0.15
            return throttle, brake, steering

        # ACC controls throttle/brake
        if 'acc' in adas_status and adas_status['acc'].get('active'):
            target_accel = adas_status['acc'].get('target_acceleration', 0.0)
            if target_accel > 0:
                throttle = min(target_accel / 2.0, 1.0)
            else:
                brake = min(abs(target_accel) / 8.0, 1.0)

        # Mild LDW corrective steer (if warning active) — optional assist
        ldw = adas_status.get('ldw') or {}
        if ldw.get('warning_active') and steering == 0.0:
            side = ldw.get('warning_side')
            if side == 'left':
                steering = -0.02
            elif side == 'right':
                steering = 0.02

        return throttle, brake, steering

    def _log_step(self, vehicle_state: Dict, sensor_data: List[Dict], adas_status: Dict):
        """
        Log simulation step data.

        Args:
            vehicle_state: Vehicle state
            sensor_data: Sensor detections
            adas_status: ADAS feature status
        """
        if len(self.log_data) >= self.max_log_entries:
            # Remove oldest entry
            self.log_data.pop(0)

        log_entry = {
            'time': self.current_time,
            'vehicle': vehicle_state,
            'sensors': sensor_data,
            'adas': adas_status
        }

        self.log_data.append(log_entry)

    def run(self, duration: float = 60.0, real_time: bool = False) -> Dict:
        """
        Run simulation for specified duration.

        Args:
            duration: Simulation duration in seconds
            real_time: If True, run at real-time speed

        Returns:
            Simulation results dictionary
        """
        logger.info(f"Starting simulation for {duration}s")

        self.is_running = True
        start_time = time.time()
        last_real_time = start_time

        steps = int(duration / self.dt)

        for i in range(steps):
            if not self.is_running:
                break

            self.step()

            # Real-time pacing
            if real_time:
                target_time = start_time + self.current_time
                current_real_time = time.time()
                if current_real_time < target_time:
                    time.sleep(target_time - current_real_time)

            # Progress reporting
            if i % 1000 == 0:
                logger.info(f"Simulation progress: {self.current_time:.1f}s / {duration}s")

        elapsed = time.time() - start_time
        logger.info(f"Simulation completed in {elapsed:.2f}s real time")

        return self.get_results()

    def stop(self):
        """Stop simulation."""
        self.is_running = False
        logger.info("Simulation stopped")

    def get_results(self) -> Dict:
        """
        Get simulation results.

        Returns:
            Results dictionary with statistics and event log
        """
        # Analyze logged data
        adas_events = []

        for entry in self.log_data:
            # Extract ADAS events
            for feature_name, status in entry['adas'].items():
                if feature_name == 'ldw' and status.get('warning_active'):
                    adas_events.append({
                        'time': entry['time'],
                        'feature': 'LDW',
                        'event': 'lane_departure_warning',
                        'side': status.get('warning_side')
                    })
                elif feature_name == 'aeb' and status.get('braking_active'):
                    adas_events.append({
                        'time': entry['time'],
                        'feature': 'AEB',
                        'event': 'emergency_braking',
                        'level': status.get('braking_level')
                    })
                elif feature_name == 'acc' and status.get('active'):
                    # Sparse ACC events — only when lead vehicle present or significant accel cmd
                    if status.get('lead_vehicle_detected') or abs(status.get('target_acceleration', 0)) > 0.5:
                        adas_events.append({
                            'time': entry['time'],
                            'feature': 'ACC',
                            'event': 'acc_active',
                            'set_speed': status.get('set_speed'),
                            'lead_distance': status.get('lead_vehicle_distance'),
                        })
                elif feature_name == 'bsd' and status.get('warning_active'):
                    adas_events.append({
                        'time': entry['time'],
                        'feature': 'BSD',
                        'event': 'blind_spot_warning',
                        'side': status.get('warning_side'),
                        'left_occupied': status.get('left_occupied'),
                        'right_occupied': status.get('right_occupied'),
                    })
                elif feature_name == 'tsr' and (
                    status.get('active') or status.get('current_speed_limit') is not None
                ):
                    adas_events.append({
                        'time': entry['time'],
                        'feature': 'TSR',
                        'event': 'traffic_sign_detected',
                        'speed_limit_kmh': status.get('speed_limit_kmh') or status.get('current_speed_limit'),
                        'signs_detected': status.get('signs_detected', 0),
                    })
                elif feature_name == 'parking' and status.get('active'):
                    adas_events.append({
                        'time': entry['time'],
                        'feature': 'PARKING',
                        'event': 'parking_maneuver',
                        'stage': status.get('stage'),
                        'progress': status.get('progress'),
                    })
                elif feature_name in ('trailer_assistance', 'trailer_reverse') and status.get('active'):
                    adas_events.append({
                        'time': entry['time'],
                        'feature': 'TRAILER',
                        'event': 'trailer_guidance',
                        'warning': status.get('warning_active', False),
                    })

        # Deduplicate high-frequency events (keep ~2 Hz max per feature type)
        adas_events = self._downsample_events(adas_events, min_interval=0.5)

        results = {
            'duration': self.current_time,
            'steps': len(self.log_data),
            'adas_events': adas_events,
            'log_data': self.log_data,
            'final_adas': self.log_data[-1]['adas'] if self.log_data else {},
            'final_vehicle': self.log_data[-1]['vehicle'] if self.log_data else {},
        }

        return results

    def _downsample_events(self, events: List[Dict], min_interval: float = 0.5) -> List[Dict]:
        """Keep event density manageable for API responses."""
        last_by_key = {}
        filtered = []
        for event in events:
            key = (event.get('feature'), event.get('event'), event.get('side'))
            t = event.get('time', 0.0)
            prev = last_by_key.get(key)
            if prev is not None and (t - prev) < min_interval:
                continue
            last_by_key[key] = t
            filtered.append(event)
        return filtered

    def get_state(self) -> Dict:
        """
        Get current simulation state.

        Returns:
            Current state dictionary
        """
        return {
            'time': self.current_time,
            'vehicle': self.vehicle.get_state(),
            'sensors': {sid: s.get_info() for sid, s in self.sensors.items()},
            'adas': {name: f._get_status() if hasattr(f, '_get_status') else {}
                    for name, f in self.adas_features.items()}
        }
