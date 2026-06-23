# Automotive ADAS + Infotainment Simulation

A feature-complete vehicle simulation platform with deployable **Android (.apk)** and **Web** applications that visualize test case execution for Radio Display and ADAS Camera ECU systems.

## Architecture

```
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
|----|-----------|-----|----------|
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

## Quick Start

### Backend API
```bash
pip install -r backend/requirements.txt -r ADAS_SIL_System/requirements.txt
uvicorn backend.api.main:app --reload
```

### Web App (Development)
```bash
cd web-app && npm install && npm run dev
```

### Mobile App (Development)
```bash
cd mobile-app && npm install && npx expo start
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
- **web-ci.yml** — Builds web app and deploys to GitHub Pages
- **mobile-build.yml** — Builds Android APK artifact
