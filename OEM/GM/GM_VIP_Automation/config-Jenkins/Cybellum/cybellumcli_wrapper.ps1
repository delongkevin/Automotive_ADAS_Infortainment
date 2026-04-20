$ErrorActionPreference = "Stop"  # Exit if any command fails

"""
Notes:
    Installation Package: https://docs.cybellum.com/product-documentation/latest/cli-installation

"""


# NOTE: This script is an early draft.  More direct API should be found to check values.
# TODO: Invoke expression isn't providing console output, obfuscating the command output needed for debugging

$env:CYBELLUM_CLI_VERSION = "1.3.5"

$repo_root = & git rev-parse --show-superproject-working-tree
if (-not $repo_root) {
    $repo_root = & git rev-parse --show-toplevel
};  $project_root = Resolve-Path $repo_root

# if .venv doesn't exist at project_root, tell user to setup the project python, else activate it
$venv_path = Join-Path $project_root ".venv"
if (-not (Test-Path $venv_path)) {
    Write-Error "Virtual environment not found at $venv_path. Please set up the project Python environment."
} else {
    & "$venv_path\Scripts\Activate.ps1"
}


#$ARTIFACT_PATH = Join-Path $project_root "bin"
$ARTIFACT_PATH = Join-Path $project_root "artifacts/GM_Deliverable"  # Not limiting to HWIODeliverable since the rework will move internal source to private from that level.
$API_KEY = "ak_9440faa48ccfdba2c9566d45778bd8b9c51638403ee41363385670d16ed6cad4" #  Key doesn't expose or permit access to any concerning items.  To be scoped later.
$COMPONENT_NAME = (Split-Path (git remote get-url origin) -Leaf) -replace '\.git$',''
$VERSION = (git describe --tags --abbrev=0)
$since_last_tag = (git rev-list "$VERSION..HEAD" --count).Trim()
$atTag = $since_last_tag -eq '0'
#$VERSION_PREVIOUS = git describe --tags --abbrev=0 "$VERSION^"
#$VERSION_PREVIOUS = git describe --tags --abbrev=0 HEAD^
$VERSION_SINCE = if($atTag) { $VERSION } else { "${VERSION}_$since_last_tag" }


$root_version = if($atTag) { "--root-version" } else { "" }
$make_default_version = if($atTag) { "--make-default-version" } else { "" }

function submit_binary {
    # CLI Information: https://docs.cybellum.com/product-documentation/latest/cli-attributes
    $cmd = @(
        "cybellumcli component create-version",
        ## ---- Target Environment: ----
        '--base-url "https://magna.cybellum.com"',
        ## ---- Authentication: ----
        "--api-key $API_KEY",
        ## ---- Connectivity: ----
        ## ---- Component: ----
        "--name $COMPONENT_NAME",
        "--create-component when-not-exists",
        "--auto-fix-import-issues",
        ## ---- Version Hierarchy: ----
        "--version $VERSION_SINCE",
        #"--from-version $VERSION_PREVIOUS",  # Incompatible with --create-component
        $root_version,
        ## ---- Default Version: ----
        $make_default_version,
        ## ---- File Source & Black list options: ----
        "--from-path $ARTIFACT_PATH",
        "--black-list *.lst *.obj *.o *.exe *.dll",
        ## ---- Worflow: ----
        "--no-workflow",  # Required for `--wait-for-completion`
        ## ---- Process Options: ----
        #"--wait-for-completion",
        "--status-interval 5",
        ## ---- Assessments: ----
        "--vulnerabilities",
        "--va-autostart",
        ## ---- Zero days assessment: ----
        "--zero-days",
        ## ---- Policy assessment: ----
        ""
    ) -join ' '
    Write-Host "Running the command: `n $cmd"
    Invoke-Expression $cmd
}

submit_binary
