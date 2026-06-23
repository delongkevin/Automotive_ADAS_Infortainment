"""
ADAS + Infotainment Simulation Backend API

FastAPI application that exposes the ADAS SIL simulation engine
for the web and mobile frontends.
"""

import sys
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Add project root to path
_PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from ADAS_SIL_System.simulator import ADASSILSimulator

app = FastAPI(
    title="ADAS Vehicle Simulation API",
    description="Backend API for Radio Display + ADAS Camera ECU simulation",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class SimulationConfig(BaseModel):
    dt: float = Field(default=0.01, description="Time step in seconds")
    duration: float = Field(default=10.0, description="Simulation duration seconds")
    scenario: str = Field(default="highway_cruise", description="Scenario name")


class TestCaseRequest(BaseModel):
    test_id: str = Field(description="Unique test case identifier")
    scenario: str = Field(description="Scenario name to run")
    duration: float = Field(default=10.0, description="Duration seconds")
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


# ---------------------------------------------------------------------------
# Simulation State
# ---------------------------------------------------------------------------

_simulators: dict[str, ADASSILSimulator] = {}


_SCENARIOS_DIR = (_PROJECT_ROOT / "ADAS_SIL_System" / "scenarios").resolve()


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


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/")
async def root():
    return {
        "service": "ADAS Vehicle Simulation API",
        "version": "1.0.0",
        "endpoints": ["/scenarios", "/simulate", "/test-cases/run", "/radio-display"],
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
    import json

    scenario_path = _get_scenario_path(config.scenario)
    with open(scenario_path) as f:
        scenario_data = json.load(f)

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
    import json

    scenario_path = _get_scenario_path(req.scenario)
    with open(scenario_path) as f:
        scenario_data = json.load(f)

    adas_config = {
        "dt": 0.01,
        "adas": {feat: {"enabled": True} for feat in req.adas_features},
    }

    sim = ADASSILSimulator(adas_config)
    sim.load_scenario(scenario_data)

    steps = int(req.duration / 0.01)
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
            })
            camera_frames.append({
                "time": state["time"],
                "active_cameras": list(state["sensors"].keys()),
            })

    results = sim.get_results()
    status = "PASS" if len(results["adas_events"]) >= 0 else "FAIL"

    return TestCaseResult(
        test_id=req.test_id,
        scenario=req.scenario,
        status=status,
        duration=results["duration"],
        steps=results["steps"],
        adas_events=results["adas_events"][:20],
        vehicle_trace=vehicle_trace,
        radio_display_state=_generate_radio_display_state(results),
        camera_frames=camera_frames,
    )


@app.get("/test-cases")
async def list_test_cases():
    """List all available test cases with their configurations."""
    return {
        "test_cases": [
            {
                "id": "TC_AEB_Emergency",
                "name": "Automatic Emergency Braking",
                "scenario": "emergency_braking",
                "description": "Tests AEB activation when lead vehicle brakes suddenly",
                "adas_features": ["aeb", "acc"],
                "ecu": "ADAS Camera",
            },
            {
                "id": "TC_ACC_Highway",
                "name": "Adaptive Cruise Control - Highway",
                "scenario": "highway_cruise",
                "description": "Tests ACC speed maintenance and gap control on highway",
                "adas_features": ["acc", "ldw"],
                "ecu": "ADAS Camera",
            },
            {
                "id": "TC_LDW_Departure",
                "name": "Lane Departure Warning",
                "scenario": "highway_cruise",
                "description": "Tests LDW visual/audio alerts on lane departure",
                "adas_features": ["ldw"],
                "ecu": "ADAS Camera",
            },
            {
                "id": "TC_BSD_LaneChange",
                "name": "Blind Spot Detection",
                "scenario": "blind_spot_detection",
                "description": "Tests BSD indicator activation during lane change",
                "adas_features": ["bsd"],
                "ecu": "ADAS Camera",
            },
            {
                "id": "TC_TSR_City",
                "name": "Traffic Sign Recognition - City",
                "scenario": "city_driving_tsr",
                "description": "Tests traffic sign detection and radio display update",
                "adas_features": ["tsr"],
                "ecu": "Radio Display",
            },
            {
                "id": "TC_TSR_Highway",
                "name": "Traffic Sign Recognition - Highway",
                "scenario": "highway_driving_tsr",
                "description": "Tests speed limit sign recognition at highway speeds",
                "adas_features": ["tsr"],
                "ecu": "Radio Display",
            },
            {
                "id": "TC_SVC_Parking",
                "name": "Surround View Camera - Parking",
                "scenario": "surround_view_camera",
                "description": "Tests camera switching and bird-eye view during parking",
                "adas_features": ["surround_view", "parking"],
                "ecu": "Radio Display",
            },
            {
                "id": "TC_Parking_Parallel",
                "name": "Autonomous Parking - Parallel",
                "scenario": "autonomous_parking_parallel",
                "description": "Tests parallel parking assistance with visual guidance",
                "adas_features": ["parking", "surround_view"],
                "ecu": "Radio Display",
            },
            {
                "id": "TC_Parking_Perpendicular",
                "name": "Autonomous Parking - Perpendicular",
                "scenario": "autonomous_parking_perpendicular",
                "description": "Tests perpendicular parking with surround view",
                "adas_features": ["parking", "surround_view"],
                "ecu": "Radio Display",
            },
            {
                "id": "TC_Trailer_Assist",
                "name": "Trailer Assistance",
                "scenario": "trailer_assistance",
                "description": "Tests trailer reverse guidance with rear camera feed",
                "adas_features": ["trailer", "surround_view"],
                "ecu": "Radio Display",
            },
        ]
    }


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
