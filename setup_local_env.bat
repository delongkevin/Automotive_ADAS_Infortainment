@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "ROOT=%~dp0"
cd /d "%ROOT%"

echo ================================================
echo   Automotive ADAS + Infotainment Local Setup
echo ================================================
echo.

call :detect_python
if errorlevel 1 goto :fail

call :check_npm
if errorlevel 1 goto :fail

call :create_or_use_venv
if errorlevel 1 goto :fail

call :install_python_deps
if errorlevel 1 goto :fail

call :install_node_deps "web-app"
if errorlevel 1 goto :fail

call :install_node_deps "mobile-app"
if errorlevel 1 goto :fail

echo.
echo Setup completed successfully.
echo.
echo Next commands:
echo   1) Backend API   : .venv\Scripts\activate ^& uvicorn backend.api.main:app --reload --port 8000
echo   2) Web App       : cd web-app ^& npm run dev
echo   3) Mobile App    : cd mobile-app ^& npx expo start
echo.

choice /M "Start backend and web app now in new terminals"
if errorlevel 2 goto :done
if errorlevel 1 call :start_services

goto :done

:detect_python
echo [1/6] Detecting Python...
set "PYTHON_CMD="
where py >nul 2>nul
if not errorlevel 1 (
    py -3 -c "import sys; print(sys.version)" >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=py -3"
)
if not defined PYTHON_CMD (
    where python >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=python"
)
if not defined PYTHON_CMD (
    echo ERROR: Python 3 not found. Install Python 3.10+ and re-run.
    exit /b 1
)
echo Using: %PYTHON_CMD%
exit /b 0

:check_npm
echo [2/6] Checking Node.js and npm...
where npm >nul 2>nul
if errorlevel 1 (
    echo ERROR: npm not found. Install Node.js 20 LTS and re-run.
    exit /b 1
)
call npm --version >nul 2>nul
if errorlevel 1 (
    echo ERROR: npm command failed. Verify Node.js installation.
    exit /b 1
)
echo npm detected.
exit /b 0

:create_or_use_venv
echo [3/6] Preparing virtual environment...
if exist ".venv\Scripts\python.exe" (
    echo Existing .venv found.
) else (
    %PYTHON_CMD% -m venv .venv
    if errorlevel 1 (
        echo ERROR: Failed to create .venv.
        exit /b 1
    )
    echo Created .venv
)
call ".venv\Scripts\activate.bat"
if errorlevel 1 (
    echo ERROR: Failed to activate .venv.
    exit /b 1
)
exit /b 0

:install_python_deps
echo [4/6] Installing Python dependencies...
python -m pip install --upgrade pip
if errorlevel 1 (
    echo ERROR: pip upgrade failed.
    exit /b 1
)
pip install -r backend\requirements.txt -r ADAS_SIL_System\requirements.txt
if errorlevel 1 (
    echo ERROR: Python dependency installation failed.
    exit /b 1
)
exit /b 0

:install_node_deps
set "APP_DIR=%~1"
echo [5/6] Installing Node dependencies in %APP_DIR%...
pushd "%APP_DIR%" >nul 2>nul
if errorlevel 1 (
    echo ERROR: Directory not found: %APP_DIR%
    exit /b 1
)
call npm install
if errorlevel 1 (
    popd >nul
    echo ERROR: npm install failed in %APP_DIR%.
    exit /b 1
)
popd >nul
exit /b 0

:start_services
echo [6/6] Starting backend and web app...
start "ADAS Backend API" cmd /k "cd /d \"%ROOT%\" && call .venv\Scripts\activate.bat && uvicorn backend.api.main:app --reload --port 8000"
start "ADAS Web App" cmd /k "cd /d \"%ROOT%web-app\" && npm run dev"
echo Started backend and web app in separate terminals.
exit /b 0

:fail
echo.
echo Setup failed. Fix the error above and run setup_local_env.bat again.
exit /b 1

:done
exit /b 0
