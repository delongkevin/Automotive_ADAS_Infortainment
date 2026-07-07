"""
Backend API tests for the ADAS simulation service.
"""

import pytest
from fastapi.testclient import TestClient

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.api.main import app

client = TestClient(app)


class TestRootEndpoint:
    def test_root_returns_service_info(self):
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "ADAS Vehicle Simulation API"
        assert data["version"] == "1.0.0"
        assert "/test-cases/criteria" in data["endpoints"]


class TestScenariosEndpoint:
    def test_list_scenarios(self):
        response = client.get("/scenarios")
        assert response.status_code == 200
        data = response.json()
        assert "scenarios" in data
        assert len(data["scenarios"]) > 0
        for s in data["scenarios"]:
            assert "name" in s
            assert "filename" in s


class TestSimulationEndpoint:
    def test_simulate_highway_cruise(self):
        response = client.post("/simulate", json={
            "dt": 0.1,
            "duration": 1.0,
            "scenario": "highway_cruise",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["scenario"] == "highway_cruise"
        assert data["duration"] > 0
        assert "vehicle_trace" in data
        assert "radio_display" in data

    def test_simulate_invalid_scenario(self):
        response = client.post("/simulate", json={
            "scenario": "nonexistent_scenario",
        })
        assert response.status_code == 404


class TestTestCasesEndpoint:
    def test_list_test_cases(self):
        response = client.get("/test-cases")
        assert response.status_code == 200
        data = response.json()
        assert "test_cases" in data
        assert len(data["test_cases"]) >= 14
        for tc in data["test_cases"]:
            assert "id" in tc
            assert "name" in tc
            assert "scenario" in tc
            assert "ecu" in tc
            assert "default_duration" in tc

    def test_run_test_case(self):
        response = client.post("/test-cases/run", json={
            "test_id": "TC_AEB_Emergency",
            "scenario": "emergency_braking",
            "duration": 1.0,
            "adas_features": ["aeb", "acc"],
        })
        assert response.status_code == 200
        data = response.json()
        assert data["test_id"] == "TC_AEB_Emergency"
        assert data["status"] in ["PASS", "FAIL"]
        assert "vehicle_trace" in data
        assert "camera_frames" in data
        assert "radio_display_state" in data
        assert "validation" in data
        assert "checks" in data["validation"]

    def test_run_test_case_with_mismatched_scenario_returns_400(self):
        response = client.post("/test-cases/run", json={
            "test_id": "TC_AEB_Emergency",
            "scenario": "highway_cruise",
            "duration": 1.0,
            "adas_features": ["aeb", "acc"],
        })
        assert response.status_code == 400

    def test_list_test_case_criteria(self):
        response = client.get("/test-cases/criteria")
        assert response.status_code == 200
        data = response.json()
        assert "test_cases" in data
        assert len(data["test_cases"]) >= 14
        assert "criteria" in data["test_cases"][0]

    def test_get_single_test_case_criteria(self):
        response = client.get("/test-cases/criteria", params={"test_id": "TC_AEB_Emergency"})
        assert response.status_code == 200
        data = response.json()
        assert data["test_case"]["id"] == "TC_AEB_Emergency"
        assert "criteria" in data["test_case"]


class TestEcuEndpoints:
    def test_radio_display_info(self):
        response = client.get("/radio-display")
        assert response.status_code == 200
        data = response.json()
        assert data["ecu"] == "Radio Display"
        assert "features" in data

    def test_adas_cameras_info(self):
        response = client.get("/adas-cameras")
        assert response.status_code == 200
        data = response.json()
        assert data["ecu"] == "ADAS Camera System"
        assert "cameras" in data
        assert len(data["cameras"]) == 5
