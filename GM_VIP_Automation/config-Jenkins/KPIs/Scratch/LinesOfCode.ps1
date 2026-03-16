# Ensure we are at the REAL root of the main repository
$repoRoot = git -C $PSScriptRoot rev-parse --show-superproject-working-tree 2>$null; if (-not $repoRoot) { $repoRoot = git -C $PSScriptRoot rev-parse --show-toplevel }
Set-Location -Path $repoRoot
Write-Host "Corrected Repo Root: $repoRoot" -ForegroundColor Green

# Function to get line counts per author
function Get-LocPerAuthor {
    param ($directory, $name)
    Push-Location $directory
    Write-Host "`nProcessing: $name ($directory)" -ForegroundColor Cyan

    $files = git ls-files
    Write-Host "Found $($files.Count) files in $name" -ForegroundColor Magenta

    $authors = $files | ForEach-Object -Parallel {
        git blame --line-porcelain $_ | Select-String "^author " | ForEach-Object { $_.Line -replace "^author " }
    } -ThrottleLimit 12

    Pop-Location

    $results = $authors | Group-Object | Sort-Object Count -Descending
    return @{ Name = $name; Data = $results }
}

# Store results
$results = @()

# Process the top-level repository
$results += Get-LocPerAuthor $repoRoot "Top-Level Repository"

# Get submodules (now correctly from the main repo)
$submodules = git submodule foreach --quiet 'pwd'
Write-Host "`nSubmodules found:" -ForegroundColor Yellow
Write-Host $submodules -ForegroundColor Gray

# Process each submodule
foreach ($subPath in $submodules) {
    if (Test-Path $subPath) {
        $results += Get-LocPerAuthor $subPath "Submodule: $subPath"
    } else {
        Write-Host "Skipping invalid path: $subPath" -ForegroundColor Red
    }
}

# Display results
foreach ($result in $results) {
    Write-Host "`n==== $($result.Name) ====" -ForegroundColor Yellow
    $result.Data | Format-Table Count, Name
}
