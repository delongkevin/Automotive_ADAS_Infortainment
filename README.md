# Automotive ADAS + Infotainment Simulation

A feature-complete vehicle simulation platform with deployable **Android (.apk)** and **Web** applications that visualize test case execution for Radio Display and ADAS Camera ECU systems.

## Live Demo

**Web App (GitHub Pages):** <https://delongkevin.github.io/Automotive_ADAS_Infortainment/>

## Getting Started with Codespaces

The fastest way to run all components is via GitHub Codespaces — everything is pre-configured.

1. Click **Code > Codespaces > Create codespace on main** on the repository page
2. Wait for the container to build (installs Python, Node.js 20, and Java 17 automatically)
3. All dependencies are installed via `postCreateCommand` — no manual setup needed

Once the Codespace is ready:

```bash
# Start the backend API
# Run this from repository root: /workspaces/Automotive_ADAS_Infortainment
uvicorn backend.api.main:app --reload --port 8000 &

# Start the web app (opens in browser automatically on port 5173)
cd web-app && npm run dev

# Or start the mobile app (Expo)
cd mobile-app && npx expo start
```

## Architecture

```text
├── ADAS_SIL_System/          # Core simulation engine (Python)
│   ├── core/                  # Vehicle dynamics, sensors, ADAS features
│   ├── scenarios/             # JSON test scenarios
│   ├── tests/                 # Unit tests
│   └── visualization/         # Visualization utilities
├── backend/                   # FastAPI REST API
│   ├── api/main.py            # Simulation API endpoints
│   └── tests/                 # API integration tests
├── web-app/                   # React web dashboard (Vite)
│   └── src/                   # Components, pages, visuals
├── mobile-app/                # React Native / Expo Android app
│   └── src/                   # Screens, components
└── .github/workflows/         # CI/CD pipelines
```

## Deployments

### Web App (GitHub Pages)

The React web app deploys automatically to GitHub Pages on push to `main`.
URL: <https://delongkevin.github.io/Automotive_ADAS_Infortainment/>

### Android App (.apk)

The mobile app builds an APK via Expo EAS on push to `main`.

### Backend API

Run locally or deploy to any cloud platform:

```bash
cd backend && pip install -r requirements.txt
uvicorn api.main:app --reload --port 8000
```

## ECU Simulation

### Radio Display ECU

- Speed display with ADAS status icons
- Traffic sign overlay from camera recognition
- Parking guidance visualization
- Warning indicators (LDW, AEB, BSD)

### ADAS Camera ECU

- Front, rear, left, right, and cargo cameras
- Object detection and classification
- Lane marking detection
- Surround view composition

## Test Cases

| ID | Test Case | ECU | Scenario |
| -- | --------- | --- | -------- |
| TC_AEB_Emergency | Automatic Emergency Braking | ADAS Camera | emergency_braking |
| TC_ACC_Highway | Adaptive Cruise Control | ADAS Camera | highway_cruise |
| TC_LDW_Departure | Lane Departure Warning | ADAS Camera | highway_cruise |
| TC_BSD_LaneChange | Blind Spot Detection | ADAS Camera | blind_spot_detection |
| TC_TSR_City | Traffic Sign Recognition | Radio Display | city_driving_tsr |
| TC_TSR_Highway | Traffic Sign Recognition | Radio Display | highway_driving_tsr |
| TC_SVC_Parking | Surround View Camera | Radio Display | surround_view_camera |
| TC_Parking_Parallel | Autonomous Parking | Radio Display | autonomous_parking_parallel |
| TC_Parking_Perpendicular | Autonomous Parking | Radio Display | autonomous_parking_perpendicular |
| TC_Trailer_Assist | Trailer Assistance | Radio Display | trailer_assistance |
| TC_StopAndGo_Commute | Stop-and-Go Commute | ADAS Camera | highway_cruise |
| TC_MergeAssist_DenseTraffic | Merge Assist - Dense Traffic | ADAS Camera | blind_spot_detection |
| TC_SchoolZone_TSR | School Zone Compliance | Radio Display | city_driving_tsr |
| TC_RainyLot_ParkingVision | Rainy Parking Lot Vision | Radio Display | surround_view_camera |

Each test case now includes deterministic validation criteria in the backend (minimum trajectory quality, duration, speed profile bounds, and distance/yaw constraints) so pass/fail is reproducible.

## Quick Start

### Backend API (Quick Start)

```bash
pip install -r backend/requirements.txt -r ADAS_SIL_System/requirements.txt
# Run from repository root
uvicorn backend.api.main:app --reload

# If you are inside web-app, use:
# uvicorn --app-dir .. backend.api.main:app --reload --port 8000
```

### Web App (Development)

```bash
cd web-app && npm install && npm run dev
```

### Mobile App (Development)

```bash
cd mobile-app && npm install && npx expo start

# Optional: point app to a different backend at runtime
# Update mobile-app/app.json -> expo.extra.apiBaseUrl
```

### Mobile Build Modes

```bash
# Cloud build (preferred): EAS-managed APK
cd mobile-app && npm run build:apk

# Local build (debugging): Gradle release APK via Expo prebuild
cd mobile-app && npm run build:apk-local
```

### Run Tests

```bash
# Backend + simulation tests
pytest backend/tests/ ADAS_SIL_System/tests/ -v

# Web app build
cd web-app && npm run build
```

## CI/CD Workflows

- **backend-ci.yml** — Runs Python tests for simulation engine and API
- **web-ci.yml** — Lints, tests, builds web app, and deploys to GitHub Pages
- **mobile-build.yml** — Builds Android APK via EAS cloud (default), with optional local Gradle mode for debugging
