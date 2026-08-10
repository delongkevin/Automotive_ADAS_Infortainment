# Review & Feedback — Automotive ADAS + Infotainment System

**Date:** 2026-08-10  
**Scope:** Software-only ADAS SIL + Radio Display / Camera ECU simulation targeting Android Automotive–compatible infotainment  
**Audience:** Maintainers reviewing progress outside of chat history  

---

## Executive verdict

The repository is a coherent **Software-in-the-Loop (SIL)** stack (Python sim → FastAPI → React web / Expo mobile) with a solid scenario/test-case catalog. Before this pass, several core control loops were effectively dead (ACC/TSR never enabled from config, reverse impossible, parking/trailer steering unused, BSD/TSR sensor contracts broken, Radio Display stubbed). Those blockers are addressed in code on this branch. Remaining gaps are mainly **Android Automotive OS (AAOS) packaging**, richer HMI (media/nav), MIL runner completeness, and production API hosting for GitHub Pages.

---

## Architecture (as designed)

```text
web-app (React/Vite)  ──┐
mobile-app (Expo RN)  ──┼── REST ──► backend/api (FastAPI)
                        │                │
                        │                ▼
                        │         ADAS_SIL_System
                        │         ├── VehicleDynamics (+ gear / reverse)
                        │         ├── Sensors (front/left/right/rear radar + front camera)
                        │         └── ADAS: LDW, ACC, AEB, BSD, Parking, Trailer, SVC, TSR
```

**ECU surfaces promised by README**

| Surface | Intent | Status after this pass |
|---------|--------|------------------------|
| Radio Display | Speed, ADAS icons, TSR overlay, warnings | **Live from sim results** (was stubbed) |
| ADAS Camera | Multi-camera + detection | UI mosaic + API metadata; still SVG/decorative feeds |
| Dynamics / ADAS | Scenario-driven SIL | Core enable/control/schema bugs fixed |

---

## Bugs fixed in this branch

### Simulation engine

1. **ACC ignored `config.enabled`** — always started disabled; never called `enable()`. Now honors config and activates after scenario load.
2. **TSR ignored `config.enabled`** — same pattern; now enables with config / load.
3. **Camera ↔ TSR schema mismatch** — camera emits `sign_type` / `sign_value` / `range`; TSR expected `sign_class` / `distance`. Also crashed on `position` dict via eager `get` default. Fixed with `_resolve_sign_type` and safe position defaults.
4. **No reverse motion** — `vx = max(0, vx)` blocked trailer/SVC reverse. Added gear (`P/R/N/D`) and signed longitudinal dynamics.
5. **Parking / trailer steering never applied** — `_compute_vehicle_controls` only used AEB/ACC. Added priority stack: AEB → parking → trailer → ACC (+ mild LDW nudge).
6. **BSD could not consume radar** — required `classification` + global `x/y`. Radar now emits vehicle-frame `x/y`, `azimuth`, `classification`; BSD accepts range/azimuth.
7. **Only front radar** — blind-spot traffic invisible. Added left/right/rear radars; FOV honors sensor mount yaw.
8. **`vehicle_approaching` unimplemented** — BSD scenarios no-oped. Engine now spawns adjacent/rear actors.
9. **MIL-style `vehicle_config` ignored by API path** — `load_scenario` now accepts MIL initial speed/position.
10. **`get_results` only logged LDW/AEB** — now also ACC/BSD/TSR/parking/trailer (downsampled).

### Backend API

11. **Radio Display always showed 0 km/h / hard-coded icons** — derived from last trace + final ADAS status.
12. **`/simulate` omitted parking/trailer features** — enabled in default sim config.
13. **Unhandled sim/JSON failures → opaque 500s** — try/except with 400/500 detail.
14. **Response key inconsistency** — `/simulate` now also returns `radio_display_state` alias.

### Web / mobile

15. **Web Simulation hid API errors** — error card added.
16. **RadioDisplay / CameraView static** — RadioDisplay accepts live `state`; CameraView lists 5 cameras consistently.
17. **“Last test” used `Object.values().slice(-1)`** — wrong after re-runs; tracked via `lastTestId`.
18. **Mobile missing scenarios** — added highway TSR + perpendicular parking.
19. **Mobile deps** — declared `expo-constants`, `react-native-gesture-handler`; cleartext + orientation notes for AAOS path.

---

## Remaining feedback (prioritized)

### P0 — Android Automotive compatibility (goal gap)

The Expo app is still a **phone** package (`com.adasinfotainment.app`), not an AAOS system/HMI app.

| Gap | Why it matters | Recommended next step |
|-----|----------------|------------------------|
| No `android.hardware.type.automotive` | Not installable/recognized as automotive | Expo config plugin or bare `android/` manifest |
| No Car App Library / templates | Distraction-optimized UX required for many AAOS surfaces | Add `androidx.car.app` park-mode screens for tests/sim |
| Landscape / IVI layout | Head units are wide; bottom tabs are phone UX | Landscape-first IVI shell (large targets, driver-safe) |
| Touchscreen optional | Many AAOS images mark touchscreen not required | `uses-feature touchscreen required=false` |
| Emulator CI | Never validated on Automotive system image | AAOS emulator smoke in `mobile-build.yml` |
| Backend reachability | `10.0.2.2` + cleartext is emulator-dev only | Build flavors: emulator / device LAN / HTTPS |

**Honest assessment:** software ADAS/Radio Display logic can run on AAOS as an APK, but **shipping as an Android Automotive–compatible infotainment system** needs native packaging + HMI rules above — not only React Native UI.

### P1 — Product / ECU completeness

- **Dashboard still mostly static** until a simulation is run on the Simulation page; wire shared state or poll `/radio-display` health + last run store.
- **Camera feeds are decorative** — no image pipeline from surround_view; acceptable for SIL demo, not for vision validation.
- **No media / tuner / nav** — “Radio Display” is ADAS chrome, not a media session (important if targeting AAOS media apps).
- **GitHub Pages demo has no API** — `VITE_API_BASE_URL` unset in CI; Run buttons fail in production. Host API or disable/gated UI when `/` health fails.
- **Collision model missing** — after AEB, ACC can re-accelerate through a stopped lead once FOV is lost. Add occupancy / post-AEB hold.

### P2 — Scenario / MIL pipeline

- Two scenario formats (engine vs MIL) still coexist. API now best-effort parses MIL events; full MIL validation still lives in `core/mil_testing.py` and does **not** feed injected detections into `step()`.
- Parking space detection heuristics and surround auto-switch on gear need deeper MIL command coverage (`start_parking`, `set_auto_switching`).
- Environment actors still primarily advance along world +X (limited yaw-aware motion).

### P3 — Engineering hygiene

- Visualization extras (`matplotlib`, `websockets`) not in requirements — gate or add optional extras.
- Unit tests historically assert “enabled after update” more than behavior; add regressions for ACC control, TSR camera schema, reverse gear, BSD radar polar detections, radio display speed.
- Sync `package-lock.json` after mobile dependency adds before CI install.

---

## Suggested roadmap (technical, not calendar)

1. **AAOS packaging spike** — config plugin + Automotive emulator install of the APK; landscape IVI shell.
2. **Shared app state** — last simulation → Dashboard Radio/Camera; API health indicator.
3. **Hosted backend** for Pages demo or document UI-only mode.
4. **Unify scenario schema** + finish MIL injection into `simulator.step`.
5. **Safety arbitration** — post-AEB ACC inhibit / simple collision.
6. **Behavioral tests** asserting AEB event, BSD occupied, TSR limit, reverse trailer active.

---

## How to verify this branch

```bash
# From repo root
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt -r ADAS_SIL_System/requirements.txt
pytest backend/tests/ ADAS_SIL_System/tests/ -v

# Manual API smoke
uvicorn backend.api.main:app --port 8000
# POST /simulate {"scenario":"emergency_braking","duration":5,"dt":0.1}
# Expect radio_display.speed_display.current_speed_kmh != stub-only zeros when ego moves
# Expect adas_events may include AEB/ACC
```

---

## Summary for stakeholders

You asked for a **fully functional software infotainment system compatible with Android Automotive**. This branch makes the **SIL + ECU visualization path functionally honest** (features enable, reverse exists, controls apply, sensors feed BSD/TSR, Radio Display reflects sim). AAOS **compatibility** is started (orientation/cleartext/deps notes) but **not complete** until automotive manifest, landscape IVI UX, and preferably Car App Library / emulator validation land. Treat the checklist in **P0** as the remaining gate for “Android Automotive compatible.”
