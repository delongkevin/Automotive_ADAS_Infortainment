#Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
#$PSNativeCommandUseErrorActionPreference = $true  # PS 7+


function finisher {
    Write-Host "Detatching branches to avoid interaction conflicts"
    git checkout --detach
    git submodule foreach "git checkout --detach; true"

    Write-Host "Fetching all branches from the remote"
    git fetch --prune
    git submodule foreach git fetch --prune

    Write-Host "Deleting existing local branches for $branch then checking out"
    git branch -D $branch 2> $null
    git submodule foreach "git branch -D $branch; true"

    # Checkout the specified branch from origin
    git checkout -b $branch origin/$branch
    git submodule update --init --recursive

    Write-Host "Updating submodules to the latest commit"
    git submodule foreach "git checkout origin/$targetBranch; true"
    $submodules = git submodule foreach --quiet 'echo $path'
    foreach ($sub in $submodules) {
        git add $sub
        Write-Host "Added submodule $sub"
    }
    git commit -m "Submodule Pointer Update"
    git push
}


$repoRoot = git -C $PSScriptRoot rev-parse --show-superproject-working-tree 2>$null; if (-not $repoRoot) { $repoRoot = git -C $PSScriptRoot rev-parse --show-toplevel }
Push-Location $repoRoot

# Get current branch as default
$currentBranch = git branch --show-current
$defaultTarget = "develop"

# Capture arguments
if ($args.Count -ge 2) {
    $branch = $args[0]
    $targetBranch = $args[1]
} elseif ($args.Count -eq 1) {
    $branch = $args[0]
    $targetInput = Read-Host "Please enter the target branch to pull from (default: $defaultTarget)"
    $targetBranch = if ($targetInput) { $targetInput } else { $defaultTarget }
} else {
    $branchInput = Read-Host "Please enter the branch you want to checkout (default: $currentBranch)"
    $branch = if ($branchInput) { $branchInput } else { $currentBranch }
    $targetInput = Read-Host "Please enter the target branch to pull from (default: $defaultTarget)"
    $targetBranch = if ($targetInput) { $targetInput } else { $defaultTarget }
}


finisher
finisher

Pop-Location
