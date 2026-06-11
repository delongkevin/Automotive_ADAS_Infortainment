# This script checks if the submodules in the current branch of the supermodule are aligned with the latest commit on the same branch in their respective remotes.

$ErrorActionPreference = "Stop"
#!/usr/bin/env pwsh

# ── 0. Navigate to repository root ──────────────────────────────────────────
# Handles being run from any subdirectory or from within a submodule
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

try {
    $repoRoot = git -C $ScriptDir rev-parse --show-superproject-working-tree 2>$null
} catch {
    $repoRoot = $null
}

if ([string]::IsNullOrWhiteSpace($repoRoot)) {
    try {
        $repoRoot = git -C $ScriptDir rev-parse --show-toplevel 2>$null
    } catch {
        $repoRoot = $null
    }
}

if ([string]::IsNullOrWhiteSpace($repoRoot)) {
    Write-Host "ERROR: Could not determine repository root." -ForegroundColor Red
    exit 1
}

Set-Location $repoRoot

# ── 1. Get the current branch of the supermodule ───────────────────────────
$currentBranch = git rev-parse --abbrev-ref HEAD

if ($env:CHANGE_BRANCH) {
    $currentBranch = $env:CHANGE_BRANCH
    Write-Host "Using CHANGE_BRANCH override: $currentBranch"
} elseif ($env:BRANCH_NAME) {
    $currentBranch = $env:BRANCH_NAME
    Write-Host "Using BRANCH_NAME override: $currentBranch"
} elseif ($currentBranch -eq "HEAD") {
    Write-Host "ERROR: Supermodule is in detached-HEAD state; cannot determine branch." -ForegroundColor Red
    exit 1
}

Write-Host "Supermodule branch: $currentBranch"
Write-Host "Repository root: $repoRoot"
Write-Host "──────────────────────────────────────────────"

# ── 1a. Check for .gitmodules ───────────────────────────────────────────────
if (-not (Test-Path ".gitmodules")) {
    Write-Host "No .gitmodules file found — this repository has no submodules."
    exit 0
}

# Counters for a tidy summary (script-scoped for recursion)
$script:total = 0
$script:checked = 0
$script:upToDate = 0
$script:behind = 0
$script:noBranch = 0

# ── 2. Recursive function to walk submodules ────────────────────────────────
function Check-Submodules {
    param (
        [string]$RepoPath,
        [string]$BranchName,
        [string]$PathPrefix = ""
    )

    $gitmodulesPath = Join-Path $RepoPath ".gitmodules"
    if (-not (Test-Path $gitmodulesPath)) {
        return
    }

    try {
        $configLines = git config --file $gitmodulesPath --get-regexp '^submodule\..*\.path$' 2>$null
    } catch {
        $configLines = $null
    }

    if ([string]::IsNullOrWhiteSpace($configLines)) {
        return
    }

    foreach ($configLine in $configLines -split "`n") {
        if ([string]::IsNullOrWhiteSpace($configLine)) { continue }

        # config_line is like: submodule.MySubmoduleName.path src/path/to/submodule
        # Extract the submodule name and path
        $parts = $configLine -split '\s+', 2
        $configKey = $parts[0]
        $smPath = $parts[1]

        # Extract submodule name from key: submodule.<name>.path -> <name>
        if ($configKey -match '^submodule\.(.*)\.path$') {
            $smName = $Matches[1]
        } else {
            continue
        }

        # Build the full display path for output
        $displayPath = "$PathPrefix$smPath"
        # Build the full filesystem path
        $fullSmPath = Join-Path $RepoPath $smPath

        $script:total++

        # Get the SHA the supermodule currently pins using git ls-tree
        try {
            $treeEntry = git -C $RepoPath ls-tree HEAD -- $smPath 2>$null
        } catch {
            $treeEntry = $null
        }

        if ([string]::IsNullOrWhiteSpace($treeEntry)) {
            Write-Host "[" -NoNewline
            Write-Host "SKIP" -ForegroundColor Yellow -NoNewline
            Write-Host "]  $displayPath  — not found in current tree (not committed?)"
            continue
        }

        $sha = ($treeEntry -split '\s+')[2]

        # Resolve the remote URL for this submodule using the submodule name
        try {
            $remoteUrl = git config --file $gitmodulesPath "submodule.$smName.url" 2>$null
        } catch {
            $remoteUrl = $null
        }

        if ([string]::IsNullOrWhiteSpace($remoteUrl)) {
            Write-Host "[" -NoNewline
            Write-Host "SKIP" -ForegroundColor Yellow -NoNewline
            Write-Host "]  $displayPath  — could not resolve remote URL"
            continue
        }

        # ── 3a. Check if the branch exists on the submodule's remote ────────────
        try {
            $lsRemoteOutput = git ls-remote --heads $remoteUrl "refs/heads/$BranchName" 2>$null
            if (-not [string]::IsNullOrWhiteSpace($lsRemoteOutput)) {
                $remoteSha = ($lsRemoteOutput -split '\s+')[0]
            } else {
                $remoteSha = $null
            }
        } catch {
            $remoteSha = $null
        }

        if ([string]::IsNullOrWhiteSpace($remoteSha)) {
            Write-Host "[" -NoNewline
            Write-Host "----" -ForegroundColor Cyan -NoNewline
            Write-Host "]  $displayPath  — branch '$BranchName' does not exist on remote"
            $script:noBranch++
            # Still recurse into nested submodules if directory exists
            if (Test-Path $fullSmPath -PathType Container) {
                Check-Submodules -RepoPath $fullSmPath -BranchName $BranchName -PathPrefix "$displayPath/"
            }
            continue
        }

        $script:checked++

        # ── 3b. The SHA the supermodule currently pins ──────────────────────────
        $pinnedSha = $sha

        # ── 3c. Compare ─────────────────────────────────────────────────────────
        if ($pinnedSha -eq $remoteSha) {
            $shortSha = $pinnedSha.Substring(0, [Math]::Min(12, $pinnedSha.Length))
            Write-Host "[" -NoNewline
            Write-Host "  OK" -ForegroundColor Green -NoNewline
            Write-Host "]  $displayPath  — up-to-date ($shortSha)"
            $script:upToDate++
        } else {
            Write-Host "[" -NoNewline
            Write-Host "DIFF" -ForegroundColor Red -NoNewline
            Write-Host "]  $displayPath"
            Write-Host "          pinned : $pinnedSha"
            Write-Host "          remote : $remoteSha"
            $script:behind++
        }

        # ── 3d. Recurse into nested submodules ──────────────────────────────────
        if (Test-Path $fullSmPath -PathType Container) {
            Check-Submodules -RepoPath $fullSmPath -BranchName $BranchName -PathPrefix "$displayPath/"
        }
    }
}

# ── Start recursive check from repository root ─────────────────────────────
Check-Submodules -RepoPath $repoRoot -BranchName $currentBranch -PathPrefix ""

# Handle case where .gitmodules exists but has no submodules defined
if ($script:total -eq 0) {
    Write-Host "No submodules defined in .gitmodules."
    exit 0
}

# ── 4. Summary ──────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "══════════════════════════════════════════════"
Write-Host "Summary  (branch: $currentBranch)"
Write-Host "  Submodules total    : $script:total"
Write-Host "  Submodules checked  : $script:checked"
Write-Host "  Up-to-date          : $script:upToDate"
Write-Host "  Differ from remote  : $script:behind"
Write-Host "  Branch not on remote: $script:noBranch"
Write-Host "══════════════════════════════════════════════"

# Exit with non-zero if any submodule is out of date
if ($script:behind -ne 0) {
    exit 1
}
exit 0

