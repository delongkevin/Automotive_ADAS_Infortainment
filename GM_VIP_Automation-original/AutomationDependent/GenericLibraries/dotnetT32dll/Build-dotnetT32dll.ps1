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

# Verify the CANoe assemblies exist
$requiredAssemblies = @("Vector.CANoe.Runtime.dll", "Vector.CANoe.Threading.dll")
foreach ($asm in $requiredAssemblies) {
    if (-not (Test-Path "$CANoeExecPath\$asm")) {
        Write-Host "ERROR: Required assembly not found: $CANoeExecPath\$asm" -ForegroundColor Red
        exit 1
    }
}
Write-Host "CANoe assemblies verified." -ForegroundColor Green

# Build the project
$projectPath = Join-Path $scriptDir "dotnetT32dll.csproj"

Write-Host "Building .NET Framework 4.7 library (x64)..." -ForegroundColor Cyan
Write-Host "Using CANoe path: $CANoeExecPath" -ForegroundColor Cyan

# Clean and rebuild
Remove-Item -Recurse -Force "$scriptDir\bin" -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force "$scriptDir\obj" -ErrorAction SilentlyContinue

dotnet build $projectPath --configuration $Configuration /p:CANoeExecPath="$CANoeExecPath"

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n=== Build Successful ===" -ForegroundColor Green
    $outputDll = Join-Path $scriptDir "bin\$Configuration\net47\dotnetT32dll.dll"
    $targetDll = Join-Path $scriptDir "..\controlLib\T32\dotnetT32dll.dll"
    $outputCin = Join-Path $scriptDir "cdotnetT32dll.cin"
    $targetCin = Join-Path $scriptDir "..\controlLib\T32\cdotnetT32dll.cin"

    if (Test-Path $outputDll) {
        Write-Host "Output DLL: $outputDll" -ForegroundColor Green
    }
    if (Test-Path $targetDll) {
        Write-Host "Copied to: $targetDll" -ForegroundColor Green
    }
    Copy-Item -Force $outputCin $targetCin
    Write-Host "Output CIN: $outputCin" -ForegroundColor Green

} else {
    Write-Host "`n=== Build Failed ===" -ForegroundColor Red
    exit 1
}
