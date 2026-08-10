#!/usr/bin/env bash
# Idempotent dependency refresh for the Automotive ADAS + Infotainment monorepo.
# Runs after the repository is checked out. Safe to re-run.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "[install] Python dependencies (backend API + ADAS simulation engine)"
python3 -m pip install --upgrade pip
python3 -m pip install -r backend/requirements.txt -r ADAS_SIL_System/requirements.txt

echo "[install] web-app dependencies"
(cd web-app && npm ci)

echo "[install] mobile-app dependencies"
(cd mobile-app && npm ci)

echo "[install] Complete"
