# Automotive ADAS + Infotainment Simulation

A feature-complete vehicle simulation platform with deployable **Android (.apk)** and **Web** applications that visualize test case execution for Radio Display and ADAS Camera ECU systems.

## Live Demo

**Web App (GitHub Pages):** <https://delongkevin.github.io/Automotive_ADAS_Infortainment/>

## Local Setup (No Codespaces Required)

This project is designed to run fully on a local machine after clone.

### One-Click Setup (Windows)

From repository root, run:

```bat
setup_local_env.bat
```

This script will:

- Create/reuse `.venv`
- Install Python dependencies from `backend/requirements.txt` and `ADAS_SIL_System/requirements.txt`
- Install web dependencies in `web-app`
- Install mobile dependencies in `mobile-app`
- Optionally start backend and web app in new terminals

If you are on macOS/Linux (or prefer manual setup), use the steps below.

### Prerequisites

- Python 3.10+
- Node.js 20 LTS (includes npm)
- Git
- Optional for Android builds: Java 17 and Android Studio SDK/Platform tools

### 1. Clone Repository

```bash
git clone https://github.com/delongkevin/Automotive_ADAS_Infortainment.git
cd Automotive_ADAS_Infortainment
```

### 2. Install Python Dependencies (Backend + Simulation)

```bash
# From repository root
python -m venv .venv

# Windows PowerShell
.\.venv\Scripts\Activate.ps1

# macOS/Linux
# source .venv/bin/activate

python -m pip install --upgrade pip
pip install -r backend/requirements.txt -r ADAS_SIL_System/requirements.txt
```

### 3. Install Web Dependencies

```bash
cd web-app
npm install
cd ..
```

### 4. Install Mobile Dependencies

```bash
cd mobile-app
npm install
cd ..
```

### 5. Verify Install

```bash
# Run from repository root (with Python venv active)
pytest backend/tests/ ADAS_SIL_System/tests/ -v

# Optional web build check
cd web-app && npm run build && cd ..
```

### 6. Start Components Locally

```bash
# Terminal 1 (repo root, venv active): backend API
uvicorn backend.api.main:app --reload --port 8000

# Terminal 2: web app
cd web-app && npm run dev

# Terminal 3: mobile app (Expo)
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
├── docs/                      # Design review & feedback documents
│   └── REVIEW_AND_FEEDBACK.md # Bug audit, AAOS gaps, roadmap
└── .github/workflows/         # CI/CD pipelines
```

## Design review

See [`docs/REVIEW_AND_FEEDBACK.md`](docs/REVIEW_AND_FEEDBACK.md) for the latest engineering review: fixed bugs, Android Automotive compatibility gaps, and recommended next steps.

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
