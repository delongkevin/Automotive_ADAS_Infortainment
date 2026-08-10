"""Regression tests for critical ADAS / infotainment bugfixes."""

import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from ADAS_SIL_System.simulator import ADASSILSimulator
from core.vehicle_dynamics import VehicleDynamics
from core.adas_features.acc import AdaptiveCruiseControl
from core.adas_features.traffic_sign_recognition import TrafficSignRecognition
from core.adas_features.blind_spot_detection import BlindSpotDetection


class TestFeatureEnableFromConfig:
    def test_acc_honors_enabled_config(self):
        acc = AdaptiveCruiseControl({"enabled": True, "set_speed": 25.0})
        assert acc.enabled is True

    def test_tsr_honors_enabled_config(self):
        tsr = TrafficSignRecognition({"enabled": True})
        assert tsr.enabled is True

    def test_simulator_activates_acc_after_load(self):
        sim = ADASSILSimulator({"adas": {"acc": {"enabled": True}, "aeb": {"enabled": True}}})
        sim.load_scenario({
            "name": "acc_bootstrap",
            "initial_conditions": {
                "ego_vehicle": {"position": [0, 0], "velocity": 30.0, "yaw": 0.0}
            },
            "environment": {"vehicles": []},
            "events": [],
        })
        assert sim.adas_features["acc"].enabled is True


class TestTSRCameraSchema:
    def test_accepts_camera_sign_type_and_value(self):
        tsr = TrafficSignRecognition({"enabled": True, "min_confidence": 0.5})
        tsr.enable()
        vehicle_state = {
            "position": {"x": 0.0, "y": 0.0, "z": 0.0},
            "velocity": {"speed": 10.0, "vx": 10.0, "vy": 0.0},
        }
        detections = [{
            "sensor_type": "camera",
            "detection_type": "traffic_sign",
            "sign_type": "speed_limit",
            "sign_value": 50,
            "range": 40.0,
            "confidence": 0.95,
        }]
        status = tsr.update(vehicle_state, detections, 1.0, 0.01)
        assert status["current_speed_limit"] == 50.0
        assert status["signs_detected"] >= 1

    def test_does_not_crash_on_dict_position(self):
        tsr = TrafficSignRecognition({"enabled": True})
        tsr.enable()
        vehicle_state = {"position": {"x": 1.0, "y": 2.0}, "velocity": {"speed": 5.0}}
        detections = [{
            "sensor_type": "camera",
            "sign_class": "speed_60",
            "confidence": 0.99,
            "distance": 30.0,
        }]
        status = tsr.update(vehicle_state, detections, 0.5, 0.01)
        assert status["enabled"] is True


class TestReverseGear:
    def test_vehicle_can_reverse_in_gear_r(self):
        vehicle = VehicleDynamics()
        vehicle.set_gear("R")
        vehicle.set_controls(throttle=0.5, brake=0.0, steering_angle=0.0)
        for _ in range(20):
            vehicle.update(0.05)
        assert vehicle.vx < 0.0
        state = vehicle.get_state()
        assert state["gear"] == "R"
        assert state["velocity"]["longitudinal"] < 0.0


class TestBSDRadarPolar:
    def test_bsd_uses_range_azimuth_without_classification(self):
        bsd = BlindSpotDetection()
        bsd.enable()
        vehicle_state = {
            "position": {"x": 0.0, "y": 0.0},
            "orientation": {"yaw": 0.0},
            "velocity": {"speed": 20.0},
        }
        # Left blind-spot polar detection (vehicle frame; left = negative azimuth in this model)
        detections = [{
            "sensor_type": "radar",
            "object_id": 1,
            "range": 5.0,
            "azimuth": math.radians(-90),
            "false_alarm": False,
        }]
        status = bsd.update(vehicle_state, detections, 1.0, 0.01)
        assert status["left_occupied"] is True
        assert status["warning_active"] is True


class TestControlArbitration:
    def test_acc_applies_throttle_when_enabled(self):
        sim = ADASSILSimulator({
            "dt": 0.05,
            "adas": {
                "acc": {"enabled": True, "set_speed": 25.0},
                "aeb": {"enabled": False},
                "ldw": {"enabled": False},
            },
        })
        # Disable side radars noise path isn't needed; keep defaults
        sim.load_scenario({
            "name": "acc_cruise",
            "initial_conditions": {
                "ego_vehicle": {"position": [0, 0], "velocity": 10.0, "yaw": 0.0}
            },
            "environment": {"vehicles": []},
            "events": [],
        })
        for _ in range(80):
            sim.step()
        assert sim.vehicle.vx > 12.0
