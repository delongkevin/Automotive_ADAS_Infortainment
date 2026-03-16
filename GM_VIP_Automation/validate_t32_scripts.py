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
        a)  Balanced block delimiters  --  every standalone '(' that opens a
            PRACTICE IF/ELSE body must have a matching standalone ')'.
            Mismatched blocks cause PRACTICE to raise a syntax error at
            runtime; they are undetectable without execution.
        b)  At least one ENDDO statement  --  executable scripts must return
            an exit code.  A missing ENDDO causes T32_API.exe to exit with
            code 0 unconditionally, silently hiding failures.
        c)  ENDDO exit codes are valid integers  --  bare ENDDO (no argument)
            is accepted and returns 0 by convention; only a non-integer token
            after ENDDO is flagged.
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

6.  Jenkins config.t32 validity
        Parses the config.t32 committed under
        config-Jenkins/Jenkins/Scripts/target_testing/ and verifies:
        a)  The file is present (it drives T32 auto-detect and t32.ini sync).
        b)  RCL=NETASSIST is declared – required for T32_API.exe socket
            connectivity; without it every API call will fail to connect.
        c)  PORT= is present and contains a valid integer > 0.
        d)  PACKLEN= is present and contains a valid integer > 0.
        Also reports the parsed PORT value; the Jenkinsfile BVT stage reads
        this value from config.t32 at runtime via env.T32_PORT.

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


def _strip_cmm_line_comment(line: str) -> str:
    """Strip a PRACTICE inline ';' comment from a single line.
    Only strips the first ';' that is not inside a double-quoted string."""
    in_string = False
    for i, ch in enumerate(line):
        if ch == '"':
            in_string = not in_string
        elif ch == ';' and not in_string:
            return line[:i]
    return line


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

_ENDDO_RE = re.compile(r'^\s*ENDDO\b', re.IGNORECASE | re.MULTILINE)

# PRACTICE IF blocks are:  IF (cond)\n(\n  body\n)
# The closing ')' terminates the block (ELSE is optionally between two blocks).
# We track a depth counter by counting standalone '(' / ')' lines.

def _check_cmm_syntax(fp: Path) -> List[str]:
    """Return error strings for syntax problems in a single CMM file."""
    try:
        raw = fp.read_text(encoding='latin-1', errors='replace')
    except OSError as exc:
        return [f"[FAIL] Could not read {fp}: {exc}"]

    if _is_readme_cmm(raw):
        return []   # documentation placeholder – skip syntax checks

    errors: List[str] = []

    # --- (a) balanced block delimiters '(' / ')' --------------------------
    # Strip inline comments before analysing so that a ';' comment containing
    # a lone '(' or ')' is not mistaken for a real block delimiter.
    depth = 0
    for lineno, line in enumerate(raw.splitlines(), start=1):
        code = _strip_cmm_line_comment(line).strip()
        if not code:
            continue
        # In PRACTICE, IF (cond)\n(\n…\n) uses a standalone '(' to open and
        # a standalone ')' to close a block body.
        if code == '(':
            depth += 1
        elif code == ')':
            depth -= 1
            if depth < 0:
                errors.append(
                    f"[FAIL] {fp.name}:{lineno}: unexpected ')' "
                    "(more block-closers than openers)."
                )
                depth = 0  # recover

    if depth > 0:
        errors.append(
            f"[FAIL] {fp.name}: {depth} unclosed block(s) "
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
        code = _strip_cmm_line_comment(line).strip()
        if not code.upper().startswith('ENDDO'):
            continue
        # bare ENDDO (no argument) returns 0 by convention – that is fine.
        # Only flag a non-integer token after ENDDO.
        parts = code.split()
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
# Check 6 – Jenkins config.t32 validity
# ---------------------------------------------------------------------------

#: Path of the config.t32 shipped with the Jenkins CI setup, relative to
#: the GM_VIP_Automation root.
_JENKINS_CONFIG_T32_REL = (
    Path('config-Jenkins')
    / 'Jenkins'
    / 'Scripts'
    / 'target_testing'
    / 'config.t32'
)

#: Directives that must appear in config.t32 (key only; value is validated
#: separately for PORT and PACKLEN).
_REQUIRED_CONFIG_T32_KEYS: List[str] = [
    'RCL',
    'PORT',
    'PACKLEN',
]

_CONFIG_T32_KV_RE = re.compile(r'^([A-Z_]+)=(.*)$')


def _parse_config_t32(fp: Path) -> Tuple[Dict[str, str], List[str]]:
    """Parse key=value directives from a config.t32 file.
    Comment lines (starting with ';') and bare keyword lines (no '=') are
    skipped.  Returns ({key: value_str}, [error strings])."""
    try:
        raw = fp.read_text(encoding='latin-1', errors='replace')
    except OSError as exc:
        return {}, [f"[FAIL] Could not read {fp}: {exc}"]

    directives: Dict[str, str] = {}
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(';'):
            continue
        m = _CONFIG_T32_KV_RE.match(stripped)
        if m:
            directives[m.group(1)] = m.group(2).strip()
    return directives, []


def check_jenkins_config_t32(root: Path) -> List[str]:
    """Validate config-Jenkins/Jenkins/Scripts/target_testing/config.t32."""
    cfg_path = root / _JENKINS_CONFIG_T32_REL
    errors: List[str] = []

    # (a) File must exist.
    if not cfg_path.is_file():
        errors.append(
            f"[FAIL] Jenkins config.t32 not found: {cfg_path}\n"
            "       This file drives T32 auto-detect (lFctn_T32_AutoDetect) and\n"
            "       t32.ini synchronisation (vFctn_T32_SyncT32ini).  Add it under\n"
            "       config-Jenkins/Jenkins/Scripts/target_testing/config.t32."
        )
        return errors

    directives, parse_errors = _parse_config_t32(cfg_path)
    if parse_errors:
        return parse_errors

    # (b) RCL=NETASSIST must be declared.
    rcl_val = directives.get('RCL', '')
    if rcl_val.upper() != 'NETASSIST':
        errors.append(
            f"[FAIL] config.t32: RCL={rcl_val!r} – expected 'NETASSIST'.\n"
            "       T32_API.exe communicates via the NETASSIST socket protocol;\n"
            "       any other RCL mode will cause every API call to fail."
        )

    # (c) PORT= must be present and a valid integer > 0.
    port_str = directives.get('PORT', '')
    if not port_str:
        errors.append(
            "[FAIL] config.t32: PORT= directive is missing or empty.\n"
            "       The NETASSIST port must be specified so T32_API.exe and\n"
            "       the bench CAPL code (vFctn_T32_SyncT32ini) can connect."
        )
    else:
        try:
            port_val = int(port_str)
            if port_val <= 0:
                errors.append(
                    f"[FAIL] config.t32: PORT={port_val} is not > 0."
                )
            else:
                # Informational – surfaced so operators can cross-check the
                # hardcoded Jenkinsfile BVT port.
                print(f"  [INFO] config.t32 PORT={port_val} "
                      "(detected in config.t32 and used by the Jenkinsfile BVT stage).")
        except ValueError:
            errors.append(
                f"[FAIL] config.t32: PORT={port_str!r} is not a valid integer."
            )

    # (d) PACKLEN= must be present and a valid integer > 0.
    packlen_str = directives.get('PACKLEN', '')
    if not packlen_str:
        errors.append(
            "[FAIL] config.t32: PACKLEN= directive is missing or empty.\n"
            "       PACKLEN controls the NETASSIST packet size; its absence\n"
            "       can cause fragmented or dropped API responses."
        )
    else:
        try:
            packlen_val = int(packlen_str)
            if packlen_val <= 0:
                errors.append(
                    f"[FAIL] config.t32: PACKLEN={packlen_val} is not > 0."
                )
        except ValueError:
            errors.append(
                f"[FAIL] config.t32: PACKLEN={packlen_str!r} is not a valid integer."
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
        bvt_errs: List[str] = []
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
    print("--- Check 6: Jenkins config.t32 validity ---")
    errs = check_jenkins_config_t32(root)
    for e in errs:
        print(f"  {e}")
    all_errors.extend(errs)
    if not errs:
        print("  [OK]   config.t32 has RCL=NETASSIST, PORT, and PACKLEN.")

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
