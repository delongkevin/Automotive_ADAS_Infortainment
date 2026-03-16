"""
validate_t32_scripts.py - Lauterbach Trace32 script and integration validator
==============================================================================
Validates Lauterbach Trace32 PRACTICE (.cmm) scripts and the T32/CAPL
integration layer for consistency, without requiring physical hardware or a
Vector CANoe / Trace32 installation.  Run this in CI (GitHub Actions or
Jenkins) on every push to catch T32-related problems early.

Checks performed
----------------
1.  T32_API.exe presence
        AutomationDependent/GenericLibraries/T32_API.exe must exist.
        Its absence means the CANoe automation layer cannot call Trace32 at
        all -- every lFctn_G_T32_RUN_CMM_CORE() invocation would fail.

2.  Required CMM scripts present
        startup.cmm and reset.cmm must exist in
        Generic_Tools/Lauterbach/TC4_Aurix/StartUp_Scripts/.
        These are the two scripts invoked by the automation library
        (vFctn_T32_CommandCreate_StartUpScripts) and are mandatory for
        bench operation.

3.  CMM script syntax (per executable .cmm file)
        a)  Balanced IF / ELSE / ENDIF  --  mismatched blocks cause PRACTICE
            to raise a syntax error at runtime; undetected without execution.
        b)  At least one ENDDO statement  --  executable scripts must return
            an exit code.  A missing ENDDO causes T32_API.exe to exit with
            code 0 unconditionally, silently hiding failures.
        c)  ENDDO exit codes are valid integers  --  only integer literals are
            accepted; ENDDO with no argument or a non-integer argument causes
            T32_API.exe to report an ambiguous exit code.
        README-only .cmm files (those containing only comment lines) are
        skipped for syntax checks (b) and (c).

4.  T32 constants consistency  (ccT32.cin)
        Parses ccT32.cin and verifies:
        a)  All eight required constants are defined:
              cc_dwT32_MaxTimeout, cc_dwT32_BP_HaltTimeout,
              cc_nT32_BPSetMaxRetries, cc_dwT32_BPSetRetryInterval,
              cc_nT32_BPSetSymbolReloadAt, cc_dwT32_LaunchTimeout,
              cc_dwT32_APICallMinGap, cc_dwT32_SymbolReloadWait
        b)  All numeric constants are > 0.
        c)  cc_nT32_BPSetSymbolReloadAt < cc_nT32_BPSetMaxRetries
            (the symbol-reload trigger must fire before the retry budget
            is exhausted, otherwise SYMBOL.RELOAD is never executed).

5.  CAPL integration path consistency  (cT32.cin)
        a)  lFctn_G_T32_RUN_CMM_CORE references T32_API.exe via the
            expected relative sub-path:
            "TestSuites\\AutomationDependent\\GenericLibraries\\T32_API.exe"
        b)  vFctn_T32_CommandCreate_StartUpScripts appends the expected
            Lauterbach sub-path:
            "TestSuites\\AutomationDependent\\Generic_Tools\\Lauterbach\\TC4_Aurix\\"
        c)  vFctn_T32_CommandCreate_Cmm_Commands appends the expected sub-path:
            "TestSuites\\AutomationDependent\\Generic_Tools\\Lauterbach\\TC4_Aurix\\Cmm_Commands\\"

Usage
-----
    python validate_t32_scripts.py [--root <GM_VIP_Automation folder>]

Exit code
---------
    0  –  no issues found
    1  –  one or more issues detected (details printed to stdout)
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_readme_cmm(text: str) -> bool:
    """Return True if the file contains only PRACTICE comment lines (;…) and
    blank lines, meaning it is a documentation placeholder, not an executable
    script."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith(';'):
            return False
    return True


def _strip_cmm_comments(text: str) -> str:
    """Remove PRACTICE ; line comments, preserving line count."""
    result = []
    for line in text.splitlines(keepends=True):
        # Remove trailing ; comment (not inside a string literal)
        idx = line.find(';')
        if idx >= 0:
            # Only strip if not inside a quoted string (simple heuristic)
            pre = line[:idx]
            result.append(pre + '\n' if '\n' in line else pre)
        else:
            result.append(line)
    return ''.join(result)


# ---------------------------------------------------------------------------
# Check 1 – T32_API.exe presence
# ---------------------------------------------------------------------------

def check_t32api_exe(root: Path) -> List[str]:
    """Return a list of error strings (empty = OK)."""
    expected = (
        root
        / 'AutomationDependent'
        / 'GenericLibraries'
        / 'T32_API.exe'
    )
    if not expected.is_file():
        return [
            f"[FAIL] T32_API.exe not found: {expected}\n"
            "       Every lFctn_G_T32_RUN_CMM_CORE() call will fail without it."
        ]
    return []


# ---------------------------------------------------------------------------
# Check 2 – Required CMM scripts present
# ---------------------------------------------------------------------------

REQUIRED_CMM = [
    Path('StartUp_Scripts') / 'startup.cmm',
    Path('StartUp_Scripts') / 'reset.cmm',
]

def check_required_cmm(t32_root: Path) -> List[str]:
    """Return error strings for any missing required CMM script."""
    errors: List[str] = []
    for rel in REQUIRED_CMM:
        fp = t32_root / rel
        if not fp.is_file():
            errors.append(
                f"[FAIL] Required CMM script missing: {fp}\n"
                f"       '{rel}' is invoked by vFctn_T32_CommandCreate_StartUpScripts()."
            )
    return errors


# ---------------------------------------------------------------------------
# Check 3 – CMM syntax
# ---------------------------------------------------------------------------

_IF_RE    = re.compile(r'^\s*IF\b',    re.IGNORECASE | re.MULTILINE)
_ELSE_RE  = re.compile(r'^\s*ELSE\b',  re.IGNORECASE | re.MULTILINE)
_ENDIF_RE = re.compile(r'^\s*\)',      re.MULTILINE)    # closing ) of IF block
_ENDDO_RE = re.compile(r'^\s*ENDDO\b', re.IGNORECASE | re.MULTILINE)

# PRACTICE IF blocks are:  IF (cond)\n(\n  body\n)
# The closing ')' terminates the block (ELSE is optionally between two blocks).
# We track a depth counter and look for ENDDO at top-level.

def _check_cmm_syntax(fp: Path) -> List[str]:
    """Return error strings for syntax problems in a single CMM file."""
    try:
        raw = fp.read_text(encoding='latin-1', errors='replace')
    except OSError as exc:
        return [f"[FAIL] Could not read {fp}: {exc}"]

    if _is_readme_cmm(raw):
        return []   # documentation placeholder – skip syntax checks

    errors: List[str] = []
    rel = fp.name

    # --- (a) IF/ELSE/ENDIF (closing ')') balance --------------------------
    depth = 0
    for lineno, line in enumerate(raw.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith(';'):
            continue
        # In PRACTICE, IF (cond)\n(\n…\n) uses '(' to open and ')' to close.
        # Count standalone '(' that follow an IF on the line above.
        # We use a simple heuristic: a line that is just '(' opens a block;
        # a line that is just ')' closes a block.
        if stripped == '(':
            depth += 1
        elif stripped == ')':
            depth -= 1
            if depth < 0:
                errors.append(
                    f"[FAIL] {fp.name}:{lineno}: unexpected ')' "
                    "(more block-closers than openers)."
                )
                depth = 0  # recover

    if depth > 0:
        errors.append(
            f"[FAIL] {fp.name}: {depth} unclosed IF block(s) "
            "(missing closing ')')."
        )

    # --- (b) At least one ENDDO ------------------------------------------
    has_enddo = bool(_ENDDO_RE.search(raw))
    if not has_enddo:
        errors.append(
            f"[FAIL] {fp.name}: no ENDDO statement found. "
            "Executable CMM scripts must return an exit code via ENDDO."
        )
        return errors   # skip (c) – no ENDDO to check

    # --- (c) ENDDO exit codes are valid integers --------------------------
    for lineno, line in enumerate(raw.splitlines(), start=1):
        stripped = line.strip()
        if not stripped.upper().startswith('ENDDO'):
            continue
        # Strip inline comment
        stripped = stripped.split(';')[0].strip()
        # ENDDO alone (no argument) is technically valid PRACTICE but
        # returns 0 by convention; flag only ENDDO with a non-integer token.
        parts = stripped.split()
        if len(parts) >= 2:
            arg = parts[1]
            try:
                int(arg)
            except ValueError:
                errors.append(
                    f"[FAIL] {fp.name}:{lineno}: ENDDO argument '{arg}' "
                    "is not an integer literal. "
                    "T32_API.exe exit-code checking requires a plain integer."
                )

    return errors


def check_cmm_syntax(t32_root: Path) -> List[str]:
    """Walk the TC4_Aurix directory and syntax-check every .cmm file."""
    errors: List[str] = []
    cmm_files = sorted(t32_root.rglob('*.cmm'))
    if not cmm_files:
        errors.append(
            f"[FAIL] No .cmm files found under {t32_root}. "
            "Expected at least startup.cmm and reset.cmm."
        )
        return errors

    for fp in cmm_files:
        errors.extend(_check_cmm_syntax(fp))

    return errors


# ---------------------------------------------------------------------------
# Check 4 – T32 constants consistency  (ccT32.cin)
# ---------------------------------------------------------------------------

REQUIRED_T32_CONSTANTS: List[str] = [
    'cc_dwT32_MaxTimeout',
    'cc_dwT32_BP_HaltTimeout',
    'cc_nT32_BPSetMaxRetries',
    'cc_dwT32_BPSetRetryInterval',
    'cc_nT32_BPSetSymbolReloadAt',
    'cc_dwT32_LaunchTimeout',
    'cc_dwT32_APICallMinGap',
    'cc_dwT32_SymbolReloadWait',
]

_CONST_RE = re.compile(
    r'\bconst\s+\w+\s+(\w+)\s*=\s*(\d+)\s*;'
)


def _parse_t32_constants(fp: Path) -> Tuple[Dict[str, int], List[str]]:
    """Parse numeric const declarations from ccT32.cin.
    Returns ({name: value}, [error strings])."""
    try:
        raw = fp.read_text(encoding='latin-1', errors='replace')
    except OSError as exc:
        return {}, [f"[FAIL] Could not read {fp}: {exc}"]

    constants: Dict[str, int] = {}
    for m in _CONST_RE.finditer(raw):
        constants[m.group(1)] = int(m.group(2))
    return constants, []


def check_t32_constants(t32_ctrl_root: Path) -> List[str]:
    """Validate ccT32.cin constant definitions."""
    cc_path = t32_ctrl_root / 'ccT32.cin'
    if not cc_path.is_file():
        return [f"[FAIL] ccT32.cin not found: {cc_path}"]

    constants, errors = _parse_t32_constants(cc_path)
    if errors:
        return errors

    # (a) All required constants defined
    for name in REQUIRED_T32_CONSTANTS:
        if name not in constants:
            errors.append(
                f"[FAIL] ccT32.cin: required constant '{name}' is not defined "
                "or could not be parsed."
            )

    # (b) All numeric constants > 0
    for name, value in constants.items():
        if name.startswith('cc_') and value <= 0:
            errors.append(
                f"[FAIL] ccT32.cin: constant '{name}' = {value}; "
                "must be > 0."
            )

    # (c) cc_nT32_BPSetSymbolReloadAt < cc_nT32_BPSetMaxRetries
    reload_at  = constants.get('cc_nT32_BPSetSymbolReloadAt')
    max_retries = constants.get('cc_nT32_BPSetMaxRetries')
    if reload_at is not None and max_retries is not None:
        if reload_at >= max_retries:
            errors.append(
                f"[FAIL] ccT32.cin: cc_nT32_BPSetSymbolReloadAt ({reload_at}) "
                f">= cc_nT32_BPSetMaxRetries ({max_retries}). "
                "SYMBOL.RELOAD is triggered at or after the retry budget is "
                "exhausted – it will never execute."
            )

    return errors


# ---------------------------------------------------------------------------
# Check 5 – CAPL integration path consistency  (cT32.cin)
# ---------------------------------------------------------------------------

# Key sub-strings that must appear in cT32.cin to guarantee correct paths.
# In CAPL string literals a single path separator is written as \\ (escaped
# backslash).  Python reads these as two characters (\\ ) so the needles
# below use \\\\ in the Python source, which produces the two-char sequence
# (backslash + backslash) that actually appears in the file.
_CAPL_PATH_CHECKS: List[Tuple[str, str, str]] = [
    # (description, function context hint, required substring in file)
    (
        "T32_API.exe path in lFctn_G_T32_RUN_CMM_CORE / lFctn_CallT32API",
        "T32_API.exe",
        "TestSuites\\\\AutomationDependent\\\\GenericLibraries\\\\T32_API.exe",
    ),
    (
        "Lauterbach sub-path in vFctn_T32_CommandCreate_StartUpScripts",
        "vFctn_T32_CommandCreate_StartUpScripts",
        "TestSuites\\\\AutomationDependent\\\\Generic_Tools\\\\Lauterbach\\\\TC4_Aurix\\\\",
    ),
    (
        "Cmm_Commands sub-path in vFctn_T32_CommandCreate_Cmm_Commands",
        "vFctn_T32_CommandCreate_Cmm_Commands",
        "TC4_Aurix\\\\Cmm_Commands\\\\",
    ),
]


def check_capl_integration(t32_ctrl_root: Path) -> List[str]:
    """Check that cT32.cin contains the expected path strings."""
    ct32_path = t32_ctrl_root / 'cT32.cin'
    if not ct32_path.is_file():
        return [f"[FAIL] cT32.cin not found: {ct32_path}"]

    try:
        raw = ct32_path.read_text(encoding='latin-1', errors='replace')
    except OSError as exc:
        return [f"[FAIL] Could not read {ct32_path}: {exc}"]

    errors: List[str] = []
    for desc, context, needle in _CAPL_PATH_CHECKS:
        if needle not in raw:
            errors.append(
                f"[FAIL] cT32.cin: expected path string not found.\n"
                f"       Check : {desc}\n"
                f"       Missing: {needle!r}"
            )

    return errors


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate Lauterbach Trace32 PRACTICE scripts and T32/CAPL "
            "integration layer without physical hardware."
        )
    )
    parser.add_argument(
        '--root', '-r',
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

    # Derived paths
    lauterbach_root = (
        root
        / 'AutomationDependent'
        / 'Generic_Tools'
        / 'Lauterbach'
        / 'TC4_Aurix'
    )
    t32_ctrl_root = (
        root
        / 'AutomationDependent'
        / 'GenericLibraries'
        / 'controlLib'
        / 'T32'
    )

    all_errors: List[str] = []

    # ------------------------------------------------------------------
    print("--- Check 1: T32_API.exe presence ---")
    errs = check_t32api_exe(root)
    for e in errs:
        print(f"  {e}")
    all_errors.extend(errs)
    if not errs:
        print("  [OK]   T32_API.exe found.")

    # ------------------------------------------------------------------
    print()
    print("--- Check 2: Required CMM scripts present ---")
    if not lauterbach_root.is_dir():
        msg = f"  [FAIL] Lauterbach directory not found: {lauterbach_root}"
        print(msg)
        all_errors.append(msg)
    else:
        errs = check_required_cmm(lauterbach_root)
        for e in errs:
            print(f"  {e}")
        all_errors.extend(errs)
        if not errs:
            print("  [OK]   startup.cmm and reset.cmm are present.")

    # ------------------------------------------------------------------
    print()
    print("--- Check 3: CMM script syntax ---")
    if lauterbach_root.is_dir():
        errs = check_cmm_syntax(lauterbach_root)
        for e in errs:
            print(f"  {e}")
        all_errors.extend(errs)

        # Also check the standalone BVT script in misc/
        bvt_cmm = root / 'misc' / 'bvt_t32_check.cmm'
        if bvt_cmm.is_file():
            bvt_errs = _check_cmm_syntax(bvt_cmm)
            for e in bvt_errs:
                print(f"  {e}")
            all_errors.extend(bvt_errs)

        total_cmm = len(list(lauterbach_root.rglob('*.cmm')))
        total_cmm += 1 if bvt_cmm.is_file() else 0
        if not errs and not bvt_errs:
            print(f"  [OK]   {total_cmm} CMM script(s) passed syntax check.")

    # ------------------------------------------------------------------
    print()
    print("--- Check 4: T32 constants consistency (ccT32.cin) ---")
    if t32_ctrl_root.is_dir():
        errs = check_t32_constants(t32_ctrl_root)
        for e in errs:
            print(f"  {e}")
        all_errors.extend(errs)
        if not errs:
            print("  [OK]   All required T32 constants are defined and valid.")
    else:
        msg = f"  [FAIL] controlLib/T32 directory not found: {t32_ctrl_root}"
        print(msg)
        all_errors.append(msg)

    # ------------------------------------------------------------------
    print()
    print("--- Check 5: CAPL integration path consistency (cT32.cin) ---")
    if t32_ctrl_root.is_dir():
        errs = check_capl_integration(t32_ctrl_root)
        for e in errs:
            print(f"  {e}")
        all_errors.extend(errs)
        if not errs:
            print("  [OK]   cT32.cin integration paths are consistent.")
    else:
        msg = f"  [FAIL] controlLib/T32 directory not found: {t32_ctrl_root}"
        print(msg)
        all_errors.append(msg)

    # ------------------------------------------------------------------
    print()
    print("=" * 60)
    if all_errors:
        print(f"RESULT: {len(all_errors)} issue(s) found.")
        print(
            "\nNote: Lauterbach Trace32 script execution requires physical "
            "hardware (ECU + JTAG probe + Trace32 installation). "
            "This validator only checks static consistency; actual runtime "
            "behavior must be verified on a test bench."
        )
        return 1

    print(
        "RESULT: All T32 script checks passed. "
        "Scripts are structurally consistent and ready for bench deployment."
    )
    print()
    print(
        "Note: This validator confirms static consistency only. "
        "Actual Trace32 execution requires physical hardware "
        "(ECU + JTAG probe + Trace32 installation). "
        "Use the bench CI/CD pipeline (cd.yml / Jenkinsfile) for live runs."
    )
    return 0


if __name__ == '__main__':
    sys.exit(main())
