"""
validate_dotnetT32dll.py - Post-build DLL integrity checker
===========================================================
Validates that dotnetT32dll.dll is correctly built for .NET 8.0 and is
compatible with CANoe's ``#pragma netlibrary`` directive before the
compiled DLL is deployed to a test bench.

Run this after every ``Build-dotnetT32dll.ps1`` invocation (or ``dotnet
build``) to catch problems that would otherwise only surface as cryptic
"Unknown symbol 'dotnetT32dllLib'" CAPL compilation errors.

Checks performed
----------------
1.  Required files exist
        dotnetT32dll.dll, dotnetT32dll.runtimeconfig.json,
        dotnetT32dll.deps.json and cdotnetT32dll.cin must all be present
        in ``controlLib/T32/``.  A missing .runtimeconfig.json is the
        root cause of the .NET 8.0 "Unknown symbol" error because CANoe
        cannot initialise the .NET 8.0 runtime host without it.

2.  runtimeconfig.json targets .NET 8.0
        Parses the JSON and verifies that the ``runtimeOptions`` refer to
        ``Microsoft.NETCore.App`` version 8.x (not .NET Framework).

3.  deps.json targets .NET 8.0
        Verifies the runtime target name in the JSON contains
        ``NETCoreApp,Version=v8.0``.

4.  DLL is not a .NET Framework assembly
        Scans the DLL binary for the string ``.NETFramework`` which is
        embedded in every .NET Framework assembly's metadata.  Its
        presence means the user compiled against the wrong target
        framework; the DLL will be loaded by CANoe as .NET 8.0 but will
        be incompatible at runtime.

5.  DLL exposes the expected namespace, class and method symbols
        Scans the DLL's metadata strings heap (UTF-8) for
        ``dotnetT32dllLib``, ``dotnetT32dllHelper`` and the six public
        methods that CAPL calls.  Any missing symbol means the C#
        source changed incompatibly without updating cdotnetT32dll.cin.

6.  cdotnetT32dll.cin API calls match DLL symbols
        Parses every ``dotnetT32dllLib::dotnetT32dllHelper::Method(``
        call in the .cin wrapper and confirms each referenced method
        name was found in the DLL binary.  This catches renames or
        deletions in dotnetT32dll.cs that were not reflected in the
        CAPL wrapper.

Usage
-----
    python validate_dotnetT32dll.py [--root <GM_VIP_Automation folder>]

    The script deduces ``controlLib/T32/`` relative to ``--root``.  Run
    it from the repo root or pass ``--root`` explicitly:

        python GM_VIP_Automation/validate_dotnetT32dll.py \\
            --root GM_VIP_Automation

Exit code
---------
    0  – all checks passed; DLL is safe to deploy
    1  – one or more checks failed (details printed to stdout)
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DLL_NAME             = "dotnetT32dll.dll"
RUNTIMECONFIG_NAME   = "dotnetT32dll.runtimeconfig.json"
DEPS_JSON_NAME       = "dotnetT32dll.deps.json"
CIN_NAME             = "cdotnetT32dll.cin"

# Relative path inside GM_VIP_Automation where CANoe loads the DLL from.
T32_SUBDIR = Path("AutomationDependent") / "GenericLibraries" / "controlLib" / "T32"

# Exact strings that must be present in the DLL's metadata strings heap.
EXPECTED_NAMESPACE = "dotnetT32dllLib"
EXPECTED_CLASS     = "dotnetT32dllHelper"
EXPECTED_METHODS   = [
    "TestWriteMessage",
    "TestWriteCustomMessage",
    "TestAdd",
    "WaitMs",
    "RunT32cmdBlocking",
    "RunT32cmdNonBlocking",
]

# Marker embedded in every .NET Framework assembly – must NOT be present.
NETFRAMEWORK_MARKER = b".NETFramework"

# Substring expected in deps.json to confirm the .NET 8.0 target.
NETCOREAPP8_MARKER = "NETCoreApp,Version=v8.0"


# ---------------------------------------------------------------------------
# Check 1 – required files exist
# ---------------------------------------------------------------------------

def check_required_files(t32_dir: Path) -> list[str]:
    """Return issues for any file that is absent from ``t32_dir``."""
    issues = []
    required = [DLL_NAME, RUNTIMECONFIG_NAME, DEPS_JSON_NAME, CIN_NAME]
    for name in required:
        path = t32_dir / name
        if not path.is_file():
            hint = ""
            if name == RUNTIMECONFIG_NAME:
                hint = (
                    "  Hint: add <EnableDynamicLoading>true</EnableDynamicLoading> to "
                    "dotnetT32dll.csproj and rebuild."
                )
            elif name == DEPS_JSON_NAME:
                hint = (
                    "  Hint: add <EnableDynamicLoading>true</EnableDynamicLoading> to "
                    "dotnetT32dll.csproj and rebuild."
                )
            elif name == DLL_NAME:
                hint = (
                    "  Hint: run Build-dotnetT32dll.ps1 (or dotnet build) before "
                    "deploying."
                )
            msg = f"  Missing required file: {path}"
            issues.append(msg)
            if hint:
                issues.append(hint)
    return issues


# ---------------------------------------------------------------------------
# Check 2 – runtimeconfig.json targets .NET 8.0
# ---------------------------------------------------------------------------

def check_runtime_config(t32_dir: Path) -> list[str]:
    """Parse runtimeconfig.json and verify it references .NET 8.0."""
    issues = []
    rc_path = t32_dir / RUNTIMECONFIG_NAME
    if not rc_path.is_file():
        return []   # already reported by check_required_files

    try:
        data = json.loads(rc_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"  {rc_path}: failed to parse JSON: {exc}"]

    opts = data.get("runtimeOptions", {})

    # Option A – tfm field (generated by EnableDynamicLoading in .NET 8+)
    tfm = opts.get("tfm", "")
    if tfm.startswith("net8."):
        return []   # pass

    # Option B – framework block
    framework = opts.get("framework", {})
    fw_name    = framework.get("name", "")
    fw_version = framework.get("version", "")
    if fw_name == "Microsoft.NETCore.App" and fw_version.startswith("8."):
        return []   # pass

    # Option C – frameworks list (multi-target builds)
    for fw in opts.get("frameworks", []):
        if (fw.get("name") == "Microsoft.NETCore.App"
                and fw.get("version", "").startswith("8.")):
            return []   # pass

    # Nothing matched
    if tfm:
        issues.append(
            f"  {rc_path}: expected target framework 'net8.x', got '{tfm}'."
        )
    elif fw_name:
        issues.append(
            f"  {rc_path}: expected Microsoft.NETCore.App 8.x, "
            f"got '{fw_name}' '{fw_version}'."
        )
    else:
        issues.append(
            f"  {rc_path}: could not determine target framework. "
            "Expected runtimeOptions.tfm='net8.x' or "
            "runtimeOptions.framework.name='Microsoft.NETCore.App'."
        )
    issues.append(
        "  Hint: ensure <TargetFramework>net8.0</TargetFramework> and "
        "<EnableDynamicLoading>true</EnableDynamicLoading> are in the .csproj."
    )
    return issues


# ---------------------------------------------------------------------------
# Check 3 – deps.json targets .NET 8.0
# ---------------------------------------------------------------------------

def check_deps_json(t32_dir: Path) -> list[str]:
    """Parse deps.json and verify the runtime target mentions .NET 8.0."""
    issues = []
    deps_path = t32_dir / DEPS_JSON_NAME
    if not deps_path.is_file():
        return []   # already reported by check_required_files

    try:
        raw = deps_path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"  {deps_path}: could not read: {exc}"]

    if NETCOREAPP8_MARKER not in raw:
        issues.append(
            f"  {deps_path}: expected to contain '{NETCOREAPP8_MARKER}'. "
            "The DLL may have been compiled against the wrong target framework."
        )
        issues.append(
            "  Hint: ensure <TargetFramework>net8.0</TargetFramework> in the .csproj "
            "and rebuild."
        )
    return issues


# ---------------------------------------------------------------------------
# Check 4 – DLL is NOT a .NET Framework assembly
# ---------------------------------------------------------------------------

def check_not_netframework(t32_dir: Path) -> list[str]:
    """Fail if the DLL binary contains the .NETFramework metadata marker."""
    issues = []
    dll_path = t32_dir / DLL_NAME
    if not dll_path.is_file():
        return []   # already reported by check_required_files

    try:
        data = dll_path.read_bytes()
    except OSError as exc:
        return [f"  {dll_path}: could not read binary: {exc}"]

    if NETFRAMEWORK_MARKER in data:
        issues.append(
            f"  {dll_path}: DLL was compiled for .NET Framework "
            f"(found '{NETFRAMEWORK_MARKER.decode()}' in binary metadata). "
            "CANoe v19+ requires a .NET 8.0 assembly; "
            "the old .NET Framework DLL will fail to load."
        )
        issues.append(
            "  Hint: change <TargetFramework> to net8.0 in the .csproj, add "
            "<EnableDynamicLoading>true</EnableDynamicLoading>, then rebuild."
        )
    return issues


# ---------------------------------------------------------------------------
# Check 5 – DLL exposes expected namespace / class / method symbols
# ---------------------------------------------------------------------------

def _scan_dll_symbols(dll_path: Path) -> set[str]:
    """
    Return the set of plain ASCII/UTF-8 identifier strings found in the DLL.

    .NET assemblies store all type and method names in the metadata
    ``#Strings`` heap as null-terminated UTF-8 sequences.  Scanning the
    raw binary for ASCII-printable tokens is sufficient to locate them
    without needing a .NET runtime on the host.
    """
    try:
        data = dll_path.read_bytes()
    except OSError:
        return set()

    # Extract runs of printable ASCII characters (identifier candidates).
    # The pattern matches valid C#/CLR identifier characters.
    dll_identifiers: set[str] = set(re.findall(rb"[A-Za-z_][A-Za-z0-9_]{2,}", data))
    return {t.decode("ascii") for t in dll_identifiers}


def check_dll_symbols(t32_dir: Path) -> tuple[list[str], set[str]]:
    """
    Scan the DLL binary for required namespace/class/method identifiers.

    Returns ``(issues, found_symbols)`` so callers can reuse the symbol
    set for subsequent checks without re-reading the file.
    """
    issues = []
    dll_path = t32_dir / DLL_NAME
    if not dll_path.is_file():
        return [], set()   # already reported by check_required_files

    found = _scan_dll_symbols(dll_path)

    for symbol in [EXPECTED_NAMESPACE, EXPECTED_CLASS] + EXPECTED_METHODS:
        if symbol not in found:
            issues.append(
                f"  {dll_path}: expected symbol '{symbol}' not found in DLL binary. "
                "The class/method may have been renamed or removed from dotnetT32dll.cs."
            )

    if issues:
        issues.append(
            "  Hint: verify dotnetT32dll.cs still declares "
            f"namespace {EXPECTED_NAMESPACE} {{ public class {EXPECTED_CLASS} {{ ... }} }} "
            "with all required public static methods, then rebuild."
        )

    return issues, found


# ---------------------------------------------------------------------------
# Check 6 – cdotnetT32dll.cin API calls match DLL symbols
# ---------------------------------------------------------------------------

# Matches calls like: dotnetT32dllLib::dotnetT32dllHelper::MethodName(
_CIN_CALL_RE = re.compile(
    rf"{re.escape(EXPECTED_NAMESPACE)}::{re.escape(EXPECTED_CLASS)}::([A-Za-z_][A-Za-z0-9_]*)\s*\("
)


def check_cin_api_consistency(t32_dir: Path, dll_symbols: set[str]) -> list[str]:
    """
    Parse cdotnetT32dll.cin and verify every .NET method it calls exists
    in the DLL binary.
    """
    issues = []
    cin_path = t32_dir / CIN_NAME
    if not cin_path.is_file():
        return []   # already reported by check_required_files
    if not dll_symbols:
        return []   # DLL unreadable; already reported

    try:
        text = cin_path.read_text(encoding="latin-1", errors="replace")
    except OSError as exc:
        return [f"  {cin_path}: could not read: {exc}"]

    # Strip // and /* */ comments to avoid matching inside comment blocks.
    text_clean = _strip_comments(text)

    called_methods: dict[str, list[int]] = {}
    for lineno, line in enumerate(text_clean.splitlines(), start=1):
        for m in _CIN_CALL_RE.finditer(line):
            method = m.group(1)
            called_methods.setdefault(method, []).append(lineno)

    if not called_methods:
        issues.append(
            f"  {cin_path}: no "
            f"{EXPECTED_NAMESPACE}::{EXPECTED_CLASS}::Method() calls found. "
            "The .cin file may be outdated or use an unexpected format."
        )
        return issues

    for method, lines in called_methods.items():
        if method not in dll_symbols:
            line_refs = ", ".join(str(l) for l in lines[:5])
            issues.append(
                f"  {cin_path}: line(s) {line_refs}: method '{method}' is called "
                f"in CAPL but was not found in {DLL_NAME}. "
                "The C# source and CAPL wrapper are out of sync."
            )

    if issues:
        issues.append(
            "  Hint: ensure every method called in cdotnetT32dll.cin exists as a "
            f"public static method on {EXPECTED_NAMESPACE}.{EXPECTED_CLASS} "
            "in dotnetT32dll.cs, then rebuild."
        )

    return issues


# ---------------------------------------------------------------------------
# Comment stripping (same logic as validate_capl.py for consistency)
# ---------------------------------------------------------------------------

def _strip_line_comments(text: str) -> str:
    result = []
    i = 0
    in_string = False
    while i < len(text):
        ch = text[i]
        if ch == '"' and (i == 0 or text[i - 1] != '\\'):
            in_string = not in_string
        if not in_string and ch == '/' and i + 1 < len(text) and text[i + 1] == '/':
            while i < len(text) and text[i] != '\n':
                i += 1
            continue
        result.append(ch)
        i += 1
    return ''.join(result)


def _strip_block_comments(text: str) -> str:
    result = []
    i = 0
    in_string = False
    while i < len(text):
        ch = text[i]
        if ch == '"' and (i == 0 or text[i - 1] != '\\'):
            in_string = not in_string
        if not in_string and text[i:i + 2] == '/*':
            i += 2
            while i < len(text) and text[i:i + 2] != '*/':
                if text[i] == '\n':
                    result.append('\n')
                i += 1
            if i < len(text):
                i += 2
        else:
            result.append(ch)
            i += 1
    return ''.join(result)


def _strip_comments(text: str) -> str:
    text = _strip_block_comments(text)
    text = _strip_line_comments(text)
    return text


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Post-build dotnetT32dll integrity checker – "
            "validates the compiled .NET 8.0 DLL is compatible with "
            "CANoe's #pragma netlibrary before deployment to test benches."
        )
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent,
        help=(
            "Root directory of GM_VIP_Automation "
            "(default: same folder as this script)"
        ),
    )
    args = parser.parse_args()
    root: Path = args.root.resolve()

    if not root.is_dir():
        print(f"ERROR: root directory not found: {root}", file=sys.stderr)
        return 1

    t32_dir = root / T32_SUBDIR
    if not t32_dir.is_dir():
        print(f"ERROR: T32 library directory not found: {t32_dir}", file=sys.stderr)
        return 1

    print(f"Validating dotnetT32dll build artifacts in: {t32_dir}\n")

    all_issues: list[str] = []

    # ---- Check 1: required files ----
    issues = check_required_files(t32_dir)
    _report("Required files present", issues, all_issues)

    # ---- Check 2: runtimeconfig.json targets .NET 8.0 ----
    issues = check_runtime_config(t32_dir)
    _report("runtimeconfig.json targets .NET 8.0", issues, all_issues)

    # ---- Check 3: deps.json targets .NET 8.0 ----
    issues = check_deps_json(t32_dir)
    _report("deps.json targets .NET 8.0", issues, all_issues)

    # ---- Check 4: DLL is NOT .NET Framework ----
    issues = check_not_netframework(t32_dir)
    _report("DLL is not a .NET Framework assembly", issues, all_issues)

    # ---- Check 5: DLL exposes expected symbols ----
    issues, dll_symbols = check_dll_symbols(t32_dir)
    _report("DLL exposes expected namespace/class/methods", issues, all_issues)

    # ---- Check 6: cdotnetT32dll.cin calls match DLL ----
    issues = check_cin_api_consistency(t32_dir, dll_symbols)
    _report("cdotnetT32dll.cin API calls consistent with DLL", issues, all_issues)

    # ---- Summary ----
    print(f"\n{'=' * 60}")
    if all_issues:
        print(
            f"RESULT: {len(all_issues)} issue(s) found. "
            "Fix before deploying dotnetT32dll to test benches."
        )
        return 1
    print(
        "RESULT: All checks passed. "
        "dotnetT32dll.dll is ready for CANoe deployment."
    )
    return 0


def _report(check_name: str, issues: list[str], accumulator: list[str]) -> None:
    """Print a single check result and append issues to the accumulator."""
    if issues:
        print(f"[FAIL] {check_name}")
        for issue in issues:
            print(issue)
        print()
        accumulator += issues
    else:
        print(f"[OK]   {check_name}")


if __name__ == "__main__":
    sys.exit(main())
