# Compatibility assignments
if ([string]::IsNullOrEmpty($IsWindows)) { $IsWindows = [System.Environment]::OSVersion.Platform -eq "Win32NT" }

# Repo alignment
$repoRoot = git -C $PSScriptRoot rev-parse --show-superproject-working-tree 2>$null; if (-not $repoRoot) { $repoRoot = git -C $PSScriptRoot rev-parse --show-toplevel }
$moduleRoot = git -C $PSScriptRoot rev-parse --show-toplevel

# OS + env alignment
$activateScript = if ($IsWindows) { Join-Path $repoRoot ".venv\Scripts\Activate.ps1" } else { Join-Path $repoRoot ".venv/bin/Activate.ps1" }
if (Test-Path $activateScript) {
    . $activateScript
} else {
    Write-Warning "Virtual environment activation script not found at $activateScript. Ensure the virtual environment is set up correctly."
}

# ensure pyserial is installed, do so if not
if (-not (& python -m pip show pyserial 2>$null)) {
    Write-Host "pyserial not found. Installing pyserial..."
    & python -m pip install pyserial
}

& python $moduleRoot\GM_VIP_Automation\Serial.py

