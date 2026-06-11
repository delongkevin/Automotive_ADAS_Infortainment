# Build-dotnetT32dll.ps1
# Build script for dotnetT32dll.dll

param(
    [string]$Configuration = "Release",
    [string]$CANoeExecPath = ""
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "=== Building dotnetT32dll.dll ===" -ForegroundColor Cyan

# Try to find CANoe installation if not specified
if ([string]::IsNullOrEmpty($CANoeExecPath)) {
    $possiblePaths = @(
        "C:\Program Files\Vector CANoe 19\Exec64\NETDev",
        "C:\Program Files\Vector CANoe 19.0\Exec64\NETDev",
        "C:\Program Files\Vector CANoe 19.4\Exec64\NETDev",
        "C:\Program Files\Vector CANoe 18\Exec64\NETDev",
        "C:\Program Files\Vector CANoe 17\Exec64\NETDev"
    )

    foreach ($path in $possiblePaths) {
        # .NET 8.0 assemblies are placed in a net8.0 subfolder in CANoe v19+
        if (Test-Path "$path\net8.0\Vector.CANoe.Runtime.dll") {
            $CANoeExecPath = $path
            Write-Host "Found CANoe at: $CANoeExecPath" -ForegroundColor Green
            break
        }
        # Fallback: check top-level for older CANoe installations
        if (Test-Path "$path\Vector.CANoe.Runtime.dll") {
            $CANoeExecPath = $path
            Write-Host "Found CANoe at: $CANoeExecPath" -ForegroundColor Green
            break
        }
    }

    if ([string]::IsNullOrEmpty($CANoeExecPath)) {
        Write-Host "ERROR: Could not find Vector CANoe installation!" -ForegroundColor Red
        Write-Host "Please specify CANoeExecPath parameter." -ForegroundColor Yellow
        Write-Host "Example: .\Build-dotnetT32dll.ps1 -CANoeExecPath 'C:\Program Files\Vector CANoe 19.0\Exec64'" -ForegroundColor Yellow
        exit 1
    }
}

# Verify the CANoe assemblies exist.
# In CANoe v19+ with .NET 8.0 support, assemblies live in the net8.0 subfolder.
$requiredAssemblies = @("Vector.CANoe.Runtime.dll", "Vector.CANoe.Threading.dll")
foreach ($asm in $requiredAssemblies) {
    $net8Path  = "$CANoeExecPath\net8.0\$asm"
    $topPath   = "$CANoeExecPath\$asm"
    if (-not (Test-Path $net8Path) -and -not (Test-Path $topPath)) {
        Write-Host "ERROR: Required assembly not found in '$CANoeExecPath' or '$CANoeExecPath\net8.0': $asm" -ForegroundColor Red
        exit 1
    }
}
Write-Host "CANoe assemblies verified." -ForegroundColor Green

# Build the project
$projectPath = Join-Path $scriptDir "dotnetT32dll.csproj"

Write-Host "Building .NET 8.0 library (x64)..." -ForegroundColor Cyan
Write-Host "Using CANoe path: $CANoeExecPath" -ForegroundColor Cyan

# Clean and rebuild
Remove-Item -Recurse -Force "$scriptDir\bin" -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force "$scriptDir\obj" -ErrorAction SilentlyContinue

dotnet build $projectPath --configuration $Configuration /p:CANoeExecPath="$CANoeExecPath"

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n=== Build Successful ===" -ForegroundColor Green
    $outputDll           = Join-Path $scriptDir "bin\$Configuration\net8.0\dotnetT32dll.dll"
    $outputRuntimeConfig = Join-Path $scriptDir "bin\$Configuration\net8.0\dotnetT32dll.runtimeconfig.json"
    $outputDepsJson      = Join-Path $scriptDir "bin\$Configuration\net8.0\dotnetT32dll.deps.json"
    $targetDll           = Join-Path $scriptDir "..\controlLib\T32\dotnetT32dll.dll"
    $outputCin           = Join-Path $scriptDir "cdotnetT32dll.cin"
    $targetCin           = Join-Path $scriptDir "..\controlLib\T32\cdotnetT32dll.cin"

    if (Test-Path $outputDll) {
        Write-Host "Output DLL: $outputDll" -ForegroundColor Green
    }
    if (Test-Path $targetDll) {
        Write-Host "Copied to: $targetDll" -ForegroundColor Green
    }

    # Copy runtimeconfig.json - required by CANoe to initialize the .NET 8.0 runtime
    # when loading the DLL via #pragma netlibrary.
    if (Test-Path $outputRuntimeConfig) {
        Copy-Item -Force $outputRuntimeConfig (Join-Path $scriptDir "..\controlLib\T32\dotnetT32dll.runtimeconfig.json")
        Write-Host "Copied runtimeconfig.json to controlLib\T32\" -ForegroundColor Green
    } else {
        Write-Host "WARNING: dotnetT32dll.runtimeconfig.json not found - ensure <EnableDynamicLoading>true</EnableDynamicLoading> is set in the .csproj" -ForegroundColor Yellow
    }

    # Copy deps.json - required for assembly dependency resolution at runtime.
    if (Test-Path $outputDepsJson) {
        Copy-Item -Force $outputDepsJson (Join-Path $scriptDir "..\controlLib\T32\dotnetT32dll.deps.json")
        Write-Host "Copied deps.json to controlLib\T32\" -ForegroundColor Green
    }

    Copy-Item -Force $outputCin $targetCin
    Write-Host "Output CIN: $outputCin" -ForegroundColor Green

} else {
    Write-Host "`n=== Build Failed ===" -ForegroundColor Red
    exit 1
}
