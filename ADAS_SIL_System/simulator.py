"""
Main ADAS SIL Simulator

Integrates all components into a complete simulation system.

Copyright Magna Electronics. All rights reserved.
"""

import numpy as np
from typing import Dict, List, Optional
import logging
import time

from .core.vehicle_dynamics import VehicleDynamics
from .core.sensors import RadarSensor, CameraSensor
from .core.adas_features import (
    LaneDepartureWarning,
    AdaptiveCruiseControl,
    AutomaticEmergencyBraking
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
        self.environment = {
            'vehicles': [],
            'pedestrians': [],
            'obstacles': [],
            'traffic_signs': [],
            'lanes': [],
            'lighting': 'day',
            'weather': 'clear'
        }

        # Data logging
        self.log_data = []
        self.max_log_entries = 10000

        logger.info("ADAS SIL Simulator initialized")

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

        # Set initial vehicle state
        initial_conditions = scenario.get('initial_conditions', {})
        ego_init = initial_conditions.get('ego_vehicle', {})

        if 'position' in ego_init:
            pos = ego_init['position']
            vel = ego_init.get('velocity', 0.0)
            yaw = ego_init.get('yaw', 0.0)
            self.vehicle.set_state(pos[0], pos[1], yaw, vel)

        # Set environment
        self.environment.update(scenario.get('environment', {}))

        # Load scenario events
        self.scenario_events = scenario.get('events', [])

        logger.info("Scenario loaded successfully")

    def reset(self):
        """Reset simulation to initial state."""
        self.current_time = 0.0
        self.vehicle.reset_state()
        self.log_data = []

        # Reset ADAS features
        for feature in self.adas_features.values():
            if hasattr(feature, 'disable'):
                feature.disable()

        logger.info("Simulation reset")

    def step(self):
        """
        Execute one simulation step.
        """
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

    def _compute_vehicle_controls(self, adas_status: Dict, vehicle_state: Dict) -> tuple:
        """
        Compute vehicle control inputs based on ADAS commands.

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
        if 'aeb' in adas_status and adas_status['aeb']['braking_active']:
            brake = adas_status['aeb']['braking_level']
            return throttle, brake, steering

        # ACC controls throttle/brake
        if 'acc' in adas_status and adas_status['acc']['active']:
            target_accel = adas_status['acc']['target_acceleration']
            if target_accel > 0:
                throttle = min(target_accel / 2.0, 1.0)
            else:
                brake = min(abs(target_accel) / 8.0, 1.0)

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

        results = {
            'duration': self.current_time,
            'steps': len(self.log_data),
            'adas_events': adas_events,
            'log_data': self.log_data
        }

        return results

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
