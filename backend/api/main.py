"""
ADAS + Infotainment Simulation Backend API

FastAPI application that exposes the ADAS SIL simulation engine
for the web and mobile frontends.
"""

import json
import math
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from ADAS_SIL_System.simulator import ADASSILSimulator

_PROJECT_ROOT = Path(__file__).parent.parent.parent

app = FastAPI(
    title="ADAS Vehicle Simulation API",
    description="Backend API for Radio Display + ADAS Camera ECU simulation",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class SimulationConfig(BaseModel):
    dt: float = Field(default=0.01, gt=0, le=1.0, description="Time step in seconds")
    duration: float = Field(default=10.0, gt=0, le=300.0, description="Simulation duration seconds")
    scenario: str = Field(default="highway_cruise", description="Scenario name")


class TestCaseRequest(BaseModel):
    test_id: str = Field(description="Unique test case identifier")
    scenario: str = Field(description="Scenario name to run")
    duration: float = Field(default=10.0, gt=0, le=300.0, description="Duration seconds")
    adas_features: list[str] = Field(
        default=["ldw", "acc", "aeb"],
        description="ADAS features to enable",
    )


class TestCaseResult(BaseModel):
    test_id: str
    scenario: str
    status: str
    duration: float
    steps: int
    adas_events: list[dict]
    vehicle_trace: list[dict]
    radio_display_state: dict
    camera_frames: list[dict]
    validation: dict[str, Any]


# ---------------------------------------------------------------------------
# Simulation State
# ---------------------------------------------------------------------------

_SCENARIOS_DIR = (_PROJECT_ROOT / "ADAS_SIL_System" / "scenarios").resolve()

_TEST_CASE_CATALOG: list[dict[str, Any]] = [
    {
        "id": "TC_AEB_Emergency",
        "name": "Automatic Emergency Braking",
        "scenario": "emergency_braking",
        "description": "Lead-vehicle hard brake should trigger rapid ego slowdown.",
        "adas_features": ["aeb", "acc"],
        "ecu": "ADAS Camera",
        "default_duration": 8.0,
        "criteria": {
            "min_trace_points": 8,
            "min_speed_drop_kmh": 5.0,
            "min_events": 1,
        },
    },
    {
        "id": "TC_ACC_Highway",
        "name": "Adaptive Cruise Control - Highway",
        "scenario": "highway_cruise",
        "description": "Sustained highway drive with smooth speed maintenance.",
        "adas_features": ["acc", "ldw"],
        "ecu": "ADAS Camera",
        "default_duration": 12.0,
        "criteria": {
            "min_trace_points": 10,
            "min_avg_speed_kmh": 30.0,
            "max_avg_speed_kmh": 140.0,
            "min_distance_m": 20.0,
        },
    },
    {
        "id": "TC_LDW_Departure",
        "name": "Lane Departure Warning",
        "scenario": "highway_cruise",
        "description": "Detect drift tendency during highway lane keeping.",
        "adas_features": ["ldw"],
        "ecu": "ADAS Camera",
        "default_duration": 10.0,
        "criteria": {
            "min_trace_points": 8,
            "min_distance_m": 15.0,
            "max_abs_yaw": 1.5,
        },
    },
    {
        "id": "TC_BSD_LaneChange",
        "name": "Blind Spot Detection",
        "scenario": "blind_spot_detection",
        "description": "Adjacent-lane traffic should be tracked during lane-change intent.",
        "adas_features": ["bsd"],
        "ecu": "ADAS Camera",
        "default_duration": 8.0,
        "criteria": {
            "min_trace_points": 6,
            "min_distance_m": 10.0,
        },
    },
    {
        "id": "TC_TSR_City",
        "name": "Traffic Sign Recognition - City",
        "scenario": "city_driving_tsr",
        "description": "Urban speed signage is identified at lower average speeds.",
        "adas_features": ["tsr"],
        "ecu": "Radio Display",
        "default_duration": 10.0,
        "criteria": {
            "min_trace_points": 8,
            "max_avg_speed_kmh": 70.0,
        },
    },
    {
        "id": "TC_TSR_Highway",
        "name": "Traffic Sign Recognition - Highway",
        "scenario": "highway_driving_tsr",
        "description": "High-speed speed-limit transitions should remain trackable.",
        "adas_features": ["tsr"],
        "ecu": "Radio Display",
        "default_duration": 10.0,
        "criteria": {
            "min_trace_points": 8,
            "min_avg_speed_kmh": 45.0,
        },
    },
    {
        "id": "TC_SVC_Parking",
        "name": "Surround View Camera - Parking",
        "scenario": "surround_view_camera",
        "description": "Low-speed maneuvering should stay stable with camera context.",
        "adas_features": ["surround_view", "parking"],
        "ecu": "Radio Display",
        "default_duration": 7.0,
        "criteria": {
            "min_trace_points": 5,
            "max_final_speed_kmh": 25.0,
        },
    },
    {
        "id": "TC_Parking_Parallel",
        "name": "Autonomous Parking - Parallel",
        "scenario": "autonomous_parking_parallel",
        "description": "Parallel slot entry should complete at controlled low speed.",
        "adas_features": ["parking", "surround_view"],
        "ecu": "Radio Display",
        "default_duration": 10.0,
        "criteria": {
            "min_trace_points": 6,
            "max_final_speed_kmh": 15.0,
            "max_distance_m": 80.0,
        },
    },
    {
        "id": "TC_Parking_Perpendicular",
        "name": "Autonomous Parking - Perpendicular",
        "scenario": "autonomous_parking_perpendicular",
        "description": "Perpendicular bay alignment should remain smooth and bounded.",
        "adas_features": ["parking", "surround_view"],
        "ecu": "Radio Display",
        "default_duration": 10.0,
        "criteria": {
            "min_trace_points": 6,
            "max_final_speed_kmh": 15.0,
            "max_distance_m": 90.0,
        },
    },
    {
        "id": "TC_Trailer_Assist",
        "name": "Trailer Assistance",
        "scenario": "trailer_assistance",
        "description": "Trailer reverse guidance should be controlled and low-speed.",
        "adas_features": ["trailer", "surround_view"],
        "ecu": "Radio Display",
        "default_duration": 10.0,
        "criteria": {
            "min_trace_points": 6,
            "max_final_speed_kmh": 20.0,
        },
    },
    {
        "id": "TC_StopAndGo_Commute",
        "name": "Stop-and-Go Commute",
        "scenario": "highway_cruise",
        "description": "Commuter traffic profile should show speed variation without instability.",
        "adas_features": ["acc", "aeb", "ldw"],
        "ecu": "ADAS Camera",
        "default_duration": 14.0,
        "criteria": {
            "min_trace_points": 12,
            "min_speed_drop_kmh": 3.0,
            "min_distance_m": 25.0,
        },
    },
    {
        "id": "TC_MergeAssist_DenseTraffic",
        "name": "Merge Assist - Dense Traffic",
        "scenario": "blind_spot_detection",
        "description": "Highway merge with adjacent vehicles should keep motion bounded.",
        "adas_features": ["bsd", "acc", "ldw"],
        "ecu": "ADAS Camera",
        "default_duration": 9.0,
        "criteria": {
            "min_trace_points": 7,
            "min_distance_m": 10.0,
            "max_abs_yaw": 1.8,
        },
    },
    {
        "id": "TC_SchoolZone_TSR",
        "name": "School Zone Compliance",
        "scenario": "city_driving_tsr",
        "description": "Urban speed moderation profile for signage-heavy areas.",
        "adas_features": ["tsr", "aeb"],
        "ecu": "Radio Display",
        "default_duration": 9.0,
        "criteria": {
            "min_trace_points": 7,
            "max_avg_speed_kmh": 60.0,
        },
    },
    {
        "id": "TC_RainyLot_ParkingVision",
        "name": "Rainy Parking Lot Vision",
        "scenario": "surround_view_camera",
        "description": "Tight low-speed maneuver representative of poor-visibility parking.",
        "adas_features": ["surround_view", "parking", "aeb"],
        "ecu": "Radio Display",
        "default_duration": 8.0,
        "criteria": {
            "min_trace_points": 6,
            "max_final_speed_kmh": 20.0,
        },
    },
]


def _get_available_scenarios() -> dict[str, Path]:
    """Build allow-list of scenario names to their resolved paths."""
    scenarios: dict[str, Path] = {}
    if _SCENARIOS_DIR.is_dir():
        for f in _SCENARIOS_DIR.iterdir():
            if f.suffix == ".json" and f.is_file():
                scenarios[f.stem] = f.resolve()
    return scenarios


def _get_scenario_path(scenario_name: str) -> Path:
    """Look up scenario by name using allow-list (prevents path injection)."""
    available = _get_available_scenarios()
    scenario_path = available.get(scenario_name)
    if scenario_path is None:
        raise HTTPException(404, f"Scenario '{scenario_name}' not found")
    return scenario_path


def _load_scenario_data(scenario_name: str) -> dict[str, Any]:
    scenario_path = _get_scenario_path(scenario_name)
    with scenario_path.open("r", encoding="utf-8") as file_handle:
        return json.load(file_handle)


def _find_test_case(test_id: str) -> Optional[dict[str, Any]]:
    for case in _TEST_CASE_CATALOG:
        if case["id"] == test_id:
            return case
    return None


def _sanitize_test_case(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": case["id"],
        "name": case["name"],
        "scenario": case["scenario"],
        "description": case["description"],
        "adas_features": case["adas_features"],
        "ecu": case["ecu"],
        "default_duration": case["default_duration"],
    }


def _criteria_payload(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": case["id"],
        "name": case["name"],
        "scenario": case["scenario"],
        "default_duration": case["default_duration"],
        "criteria": case.get("criteria", {}),
    }


def _travel_distance(trace: list[dict[str, Any]]) -> float:
    if len(trace) < 2:
        return 0.0

    total = 0.0
    prev = trace[0]
    for point in trace[1:]:
        total += math.dist((prev["x"], prev["y"]), (point["x"], point["y"]))
        prev = point
    return total


def _evaluate_test_case(
    case: Optional[dict[str, Any]],
    req_duration: float,
    results: dict[str, Any],
    vehicle_trace: list[dict[str, Any]],
) -> dict[str, Any]:
    speeds = [float(point.get("speed_kmh", 0.0)) for point in vehicle_trace]
    avg_speed = (sum(speeds) / len(speeds)) if speeds else 0.0
    max_speed = max(speeds) if speeds else 0.0
    final_speed = speeds[-1] if speeds else 0.0
    speed_drop = (max(speeds) - min(speeds)) if speeds else 0.0
    distance = _travel_distance(vehicle_trace)
    max_abs_yaw = max((abs(float(point.get("yaw", 0.0))) for point in vehicle_trace), default=0.0)
    event_count = len(results.get("adas_events", []))

    criteria = {
        "min_trace_points": 5,
        "min_duration": req_duration * 0.95,
        "min_steps": 10,
    }
    if case is not None:
        criteria.update(case.get("criteria", {}))

    checks = [
        {
            "name": "duration",
            "passed": float(results.get("duration", 0.0)) >= float(criteria["min_duration"]),
            "actual": round(float(results.get("duration", 0.0)), 3),
            "expected": f">= {criteria['min_duration']:.2f}",
        },
        {
            "name": "steps",
            "passed": int(results.get("steps", 0)) >= int(criteria["min_steps"]),
            "actual": int(results.get("steps", 0)),
            "expected": f">= {int(criteria['min_steps'])}",
        },
        {
            "name": "trace_points",
            "passed": len(vehicle_trace) >= int(criteria["min_trace_points"]),
            "actual": len(vehicle_trace),
            "expected": f">= {int(criteria['min_trace_points'])}",
        },
    ]

    optional_checks = [
        ("min_avg_speed_kmh", avg_speed, ">="),
        ("max_avg_speed_kmh", avg_speed, "<="),
        ("min_speed_drop_kmh", speed_drop, ">="),
        ("max_final_speed_kmh", final_speed, "<="),
        ("min_distance_m", distance, ">="),
        ("max_distance_m", distance, "<="),
        ("max_abs_yaw", max_abs_yaw, "<="),
        ("min_events", float(event_count), ">="),
    ]

    for key, actual, operator in optional_checks:
        if key not in criteria:
            continue
        expected_value = float(criteria[key])
        passed = actual >= expected_value if operator == ">=" else actual <= expected_value
        checks.append(
            {
                "name": key,
                "passed": passed,
                "actual": round(actual, 3),
                "expected": f"{operator} {round(expected_value, 3)}",
            }
        )

    all_passed = all(check["passed"] for check in checks)
    return {
        "status": "PASS" if all_passed else "FAIL",
        "checks": checks,
        "summary": {
            "avg_speed_kmh": round(avg_speed, 3),
            "max_speed_kmh": round(max_speed, 3),
            "final_speed_kmh": round(final_speed, 3),
            "speed_drop_kmh": round(speed_drop, 3),
            "distance_m": round(distance, 3),
            "event_count": event_count,
        },
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/")
async def root():
    return {
        "service": "ADAS Vehicle Simulation API",
        "version": "1.0.0",
        "endpoints": ["/scenarios", "/simulate", "/test-cases", "/test-cases/criteria", "/test-cases/run", "/radio-display"],
    }


@app.get("/scenarios")
async def list_scenarios():
    """List available simulation scenarios."""
    available = _get_available_scenarios()
    scenarios = []
    for name in sorted(available.keys()):
        scenarios.append({
            "name": name,
            "filename": f"{name}.json",
        })
    return {"scenarios": scenarios}


@app.post("/simulate")
async def run_simulation(config: SimulationConfig):
    """Run a full simulation and return results with visual data."""
    scenario_data = _load_scenario_data(config.scenario)

    adas_config = {
        "dt": config.dt,
        "adas": {
            "ldw": {"enabled": True},
            "acc": {"enabled": True},
            "aeb": {"enabled": True},
            "bsd": {"enabled": True},
            "tsr": {"enabled": True},
            "surround_view": {"enabled": True},
        },
    }

    sim = ADASSILSimulator(adas_config)
    sim.load_scenario(scenario_data)

    steps = int(config.duration / config.dt)
    vehicle_trace = []
    camera_frames = []

    for i in range(steps):
        sim.step()
        if i % 10 == 0:
            state = sim.get_state()
            vehicle_trace.append({
                "time": state["time"],
                "x": state["vehicle"]["position"]["x"],
                "y": state["vehicle"]["position"]["y"],
                "speed_kmh": state["vehicle"]["velocity"]["speed"] * 3.6,
                "yaw": state["vehicle"]["orientation"]["yaw"],
                "throttle": state["vehicle"]["controls"]["throttle"],
                "brake": state["vehicle"]["controls"]["brake"],
                "steering": state["vehicle"]["controls"]["steering_angle"],
            })
            camera_frames.append({
                "time": state["time"],
                "sensors": list(state["sensors"].keys()),
                "detections_count": len(sim.sensors.get("front_camera", type("", (), {"detections": []})()).detections) if "front_camera" in sim.sensors else 0,
            })

    results = sim.get_results()

    return {
        "scenario": config.scenario,
        "duration": results["duration"],
        "steps": results["steps"],
        "adas_events": results["adas_events"][:50],
        "vehicle_trace": vehicle_trace,
        "camera_frames": camera_frames,
        "radio_display": _generate_radio_display_state(results),
    }


@app.post("/test-cases/run")
async def run_test_case(req: TestCaseRequest) -> TestCaseResult:
    """Execute a specific test case and return visual results."""
    case = _find_test_case(req.test_id)
    scenario_name = req.scenario
    duration = req.duration
    adas_features = list(req.adas_features)

    if case is not None:
        expected_scenario = case["scenario"]
        if req.scenario != expected_scenario:
            raise HTTPException(
                status_code=400,
                detail=f"Test case '{req.test_id}' requires scenario '{expected_scenario}'",
            )
        if not adas_features:
            adas_features = list(case.get("adas_features", []))
        duration = max(duration, float(case.get("default_duration", duration)))

    scenario_data = _load_scenario_data(scenario_name)

    adas_config = {
        "dt": 0.01,
        "adas": {feat: {"enabled": True} for feat in adas_features},
    }

    sim = ADASSILSimulator(adas_config)
    sim.load_scenario(scenario_data)

    steps = int(duration / 0.01)
    vehicle_trace = []
    camera_frames = []

    for i in range(steps):
        sim.step()
        if i % 50 == 0:
            state = sim.get_state()
            vehicle_trace.append({
                "time": state["time"],
                "x": state["vehicle"]["position"]["x"],
                "y": state["vehicle"]["position"]["y"],
                "speed_kmh": state["vehicle"]["velocity"]["speed"] * 3.6,
                "yaw": state["vehicle"]["orientation"]["yaw"],
                "throttle": state["vehicle"]["controls"]["throttle"],
                "brake": state["vehicle"]["controls"]["brake"],
            })
            camera_frames.append({
                "time": state["time"],
                "active_cameras": list(state["sensors"].keys()),
            })

    results = sim.get_results()
    validation = _evaluate_test_case(case, duration, results, vehicle_trace)

    return TestCaseResult(
        test_id=req.test_id,
        scenario=scenario_name,
        status=validation["status"],
        duration=results["duration"],
        steps=results["steps"],
        adas_events=results["adas_events"][:20],
        vehicle_trace=vehicle_trace,
        radio_display_state=_generate_radio_display_state(results),
        camera_frames=camera_frames,
        validation=validation,
    )


@app.get("/test-cases")
async def list_test_cases():
    """List all available test cases with their configurations."""
    return {"test_cases": [_sanitize_test_case(case) for case in _TEST_CASE_CATALOG]}


@app.get("/test-cases/criteria")
async def list_test_case_criteria(test_id: Optional[str] = None):
    """List deterministic criteria used to evaluate each test case."""
    if test_id:
        case = _find_test_case(test_id)
        if case is None:
            raise HTTPException(404, f"Test case '{test_id}' not found")
        return {"test_case": _criteria_payload(case)}

    return {"test_cases": [_criteria_payload(case) for case in _TEST_CASE_CATALOG]}


@app.get("/radio-display")
async def get_radio_display_info():
    """Get Radio Display ECU information."""
    return {
        "ecu": "Radio Display",
        "features": [
            "Speed Display",
            "ADAS Status Icons",
            "Traffic Sign Overlay",
            "Camera View Switching",
            "Parking Guidance Overlay",
            "Warning Indicators",
        ],
        "resolution": "1920x720",
        "refresh_rate": "60Hz",
    }


@app.get("/adas-cameras")
async def get_camera_info():
    """Get ADAS Camera ECU system information."""
    return {
        "ecu": "ADAS Camera System",
        "cameras": [
            {"name": "Front Camera", "resolution": "1920x1080", "fov": "50deg", "fps": 30},
            {"name": "Rear Camera", "resolution": "1280x720", "fov": "120deg", "fps": 30},
            {"name": "Left Mirror Camera", "resolution": "1280x720", "fov": "80deg", "fps": 30},
            {"name": "Right Mirror Camera", "resolution": "1280x720", "fov": "80deg", "fps": 30},
            {"name": "Cargo/Surround Camera", "resolution": "1280x720", "fov": "100deg", "fps": 30},
        ],
        "processing": {
            "object_detection": True,
            "lane_detection": True,
            "sign_recognition": True,
            "depth_estimation": True,
        },
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _generate_radio_display_state(results: dict) -> dict:
    """Generate simulated Radio Display ECU state from results."""
    events = results.get("adas_events", [])
    warnings = [e for e in events if "warning" in e.get("event", "")]
    braking = [e for e in events if "braking" in e.get("event", "")]

    return {
        "speed_display": {
            "current_speed_kmh": 0,
            "unit": "km/h",
        },
        "adas_icons": {
            "ldw_active": any(e["feature"] == "LDW" for e in events),
            "acc_active": True,
            "aeb_warning": len(braking) > 0,
            "bsd_left": False,
            "bsd_right": False,
            "tsr_detected": False,
        },
        "warnings_triggered": len(warnings),
        "emergency_events": len(braking),
        "camera_view": "front",
    }
