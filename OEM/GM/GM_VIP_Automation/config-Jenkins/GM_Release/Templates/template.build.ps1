<#
.SYNOPSIS
    Build script for different targets (APPL, BOOT, RPGM, ALL).

.PARAMETER Flag
    Specify the target to build.
    Valid values: APPL, BOOT, RPGM, ALL.
#>

param (
    [ValidateSet("APPL", "APPL_GM" ,"BOOT", "RPGM", "ALL")]
    [string]$Flag = "ALL"
)

# Set -e equivalent.
$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $true

# Navigate to the script directory
Push-Location -Path $PSScriptRoot

# Import common environment variables
. "$PSScriptRoot\common_env.ps1"
if ($IsWindows) {
    $env:PATH = "$PSScriptRoot/gnu_utils/v1.1.0/bin;$env:PATH"
}

# Helper function to make all builds the same
function Build-Target {
    param([string]$Target)

    $upper  = $Target.ToUpper()
    $lower = ($Target.ToLower() -split '^hwio',2)[1]
    $logDir = Join-Path $PSScriptRoot "temp/$upper"
    $null   = New-Item -Path $logDir -ItemType Directory -Force

    Write-Host "Building target: $Target. Logs in $logDir"

    # Test
    & make "clean_test$Target"
    Set-Unset-Comment -Mode 'unset' -Path "$PSScriptRoot/HWIODeliverable/${upper}/${upper}.lsl" -Pattern '#include.*?Supplier'  # Supplier Cal
    Set-Unset-Comment -Mode 'unset' -Path "$PSScriptRoot/HWIODeliverable/${upper}/LinkerIncludes/sections_$lower.lcf" -Pattern '#include.*?Supplier'  # Supplier Test Sections
    & make "Magna_test$Target" "-j" "-B" 'LDFLAG_ARGS=-Xpreprocess-lecl'
    Set-Unset-Comment -Mode 'set' -Path "$PSScriptRoot/HWIODeliverable/${upper}/${upper}.lsl" -Pattern '#include.*?Supplier' # Supplier Cal
    Set-Unset-Comment -Mode 'set' -Path "$PSScriptRoot/HWIODeliverable/${upper}/LinkerIncludes/sections_$lower.lcf" -Pattern '#include.*?Supplier' # Supplier Test Sections

    # Lib
    & make "clean_$Target"
    & make $Target "-j" "-B" 'LDFLAG_ARGS=-Xpreprocess-lecl'
}

function Set-Unset-Comment {
    param(
        [ValidateSet('set','unset')]$Mode,
        [string]$Path,
        [string]$Pattern
    )

    $lines = Get-Content -LiteralPath $Path
    $rx    = [regex]$Pattern

    $blockRx = '^(?<indent>\s*)/\*\s?(?<body>.*?)\s?\*/\s*$'

    $lines = foreach($l in $lines){
        $u = $l
        if($l -match $blockRx){
            $u = "$($matches.indent)$($matches.body)"  # uncommented view (for matching)
        }

        if(-not $rx.IsMatch($u)){ $l; continue }

        if($Mode -eq 'unset'){
            $u
        } else {
            if($l -match $blockRx){
                $l
            } else {
                $indent = [regex]::Match($l,'^\s*').Value
                $rest   = $l.Substring($indent.Length)
                "$indent/* $rest */"
            }
        }
    }

    Set-Content -LiteralPath $Path -Value $lines
}


Push-Location -Path "HWIODeliverable"
if ($Flag -ieq "APPL") {
    Build-Target 'hwioappl'
} elseif ($Flag -ieq "BOOT") {
    Build-Target 'hwioboot'
} elseif ($Flag -ieq "RPGM") {
    Build-Target 'hwiorpgm'
} elseif ($Flag -ieq "ALL") {
    Build-Target 'hwioappl'
    Build-Target 'hwioboot'
    Build-Target 'hwiorpgm'
} elseif ($Flag -ieq "APPL_GM") {
    $appl_gm_path = Join-Path $PSScriptRoot "Private/HWIOAPPL_GM"
    if (Test-Path $appl_gm_path) {
        Remove-Item -Recurse -Force $appl_gm_path
    }  # Delete the HWIOAPPL_GM folder
    New-Item -ItemType Directory -Path $appl_gm_path
    Copy-Item -Recurse -Force "HWIOAPPL/Makefile" $appl_gm_path/Makefile
    Copy-Item -Recurse -Force "HWIOAPPL/Source" $appl_gm_path/Source
    git -C $env:REPO_ROOT apply --verbose "$PSScriptRoot/Private/APPL_GM_BUILD.patch"

    Set-Unset-Comment -Mode 'set' -Path "$env:REPO_ROOT/sw/common/linker/symbols_appl.lcf" -Pattern '-l:HWIOAPPL_fpu_hwio.a'
    make -C $appl_gm_path Magna_testhwioappl -j -B GM_OBJDIR="$env:REPO_ROOT/sw/customer/APPL"
    Set-Unset-Comment -Mode 'unset' -Path "$env:REPO_ROOT/sw/common/linker/symbols_appl.lcf" -Pattern '-l:HWIOAPPL_fpu_hwio.a'
}
Pop-Location

# Return to the original directory
Pop-Location
