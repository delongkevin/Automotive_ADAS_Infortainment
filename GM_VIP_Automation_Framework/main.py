"""
GM VIP Automation Framework – Main Execution Entry Point
=========================================================
Single entry point for running any test suite or JSON-driven test file.

Quick start
-----------
List everything available::

    python main.py --list

Run the sanity Python test suite in **mock** mode (default – no hardware)::

    python main.py --suite test_sanity

Run the sanity Python test suite against **real Trace32 hardware**::

    python main.py --suite test_sanity --mode live

Run all Python test suites::

    python main.py --suite all
    python main.py --suite all --mode live

Run a Python test suite **from any directory** by passing its path directly::

    python main.py --suite /path/to/my_custom_test.py
    python main.py --suite ../other_project/test_ecu.py --mode live

Run the sanity JSON test cases (always live – connects to running Trace32)::

    python main.py --json sanity

Run a JSON test-case file **from any directory** by passing its path directly::

    python main.py --json /path/to/stress_test_cases.json
    python main.py --json ../tests/powercycle_test_cases.json --auto-launch

If Trace32 is **not** already running, launch it automatically::

    python main.py --json sanity --auto-launch
    python main.py --suite test_sanity --mode live --auto-launch

Run every ``*_test_cases.json`` file discovered automatically::

    python main.py --json all

Scan a **different directory** for suites and JSON files::

    python main.py --dir /path/to/custom_tests --suite all
    python main.py --dir /path/to/custom_tests --json all
    python main.py --dir /path/to/custom_tests --list

Mode
----
``--mode mock`` (default)
    All Trace32 API calls are simulated.  No hardware, no Trace32
    installation, and no ``lauterbach.trace32.rcl`` library are required.
    Ideal for CI pipelines and rapid local development.

``--mode live``
    **Default behaviour (detect first, launch only if asked):**
    Before loading the test module, ``main.py`` probes the configured port
    (default 20000).  If Trace32 is already running it connects immediately.
    Only when Trace32 is not found *and* ``--auto-launch`` is given will a
    new Trace32 process be started.  ``t32_exe_path`` in ``config.json``
    is not required when Trace32 is already running.

    Pre-requisites for live mode:

    1. ``pip install lauterbach.trace32.rcl``
    2. Trace32 PowerView open with your ARM debug session loaded (or use
       ``--auto-launch`` and set ``t32_exe_path`` in ``config.json``).
    3. ``config.t32`` must contain::

           RCL=NETASSIST
           PACKLEN=1024
           PORT=20000

    For CAN tests also set ``USE_CANOE`` or ``USE_CAN_BUS`` inside the
    test file, or connect a BK Precision 1687B and set ``USE_POWER_SUPPLY``.

JSON suites (``--json``)
    JSON-driven suites always run against a live Trace32 instance.  The
    same detect-first logic applies: the framework tries to connect to the
    running Trace32 before considering a launch.

Adding a new suite
------------------
Python suite
    Add ``tests/my_new_test.py`` (standard unittest file).
    It is picked up automatically by ``--suite all``.
    Or pass its path directly: ``python main.py --suite /path/to/my_new_test.py``.

JSON suite (no Python edits required)
    Add ``my_new_test_cases.json`` to the framework directory.
    It is picked up automatically by ``--json all``.
    Or pass its path directly: ``python main.py --json /path/to/my_new_test_cases.json``.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
import time as _time
from pathlib import Path
from typing import Dict, List, Optional
import unittest

# ---------------------------------------------------------------------------
# Path bootstrap – works whether main.py is invoked directly or via pytest.
# Layout: <repo_root>/GM_VIP_Automation_Framework/main.py
# ---------------------------------------------------------------------------
_FRAMEWORK_DIR = Path(__file__).resolve().parent          # GM_VIP_Automation_Framework/
_REPO_ROOT     = _FRAMEWORK_DIR.parent                    # <repo_root>/
_TESTS_DIR     = _FRAMEWORK_DIR / "tests"

if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _discover_python_suites(directory: Optional[Path] = None) -> List[Path]:
    """Return sorted list of ``test_*.py`` files.

    Parameters
    ----------
    directory:
        Directory to scan.  Defaults to ``GM_VIP_Automation_Framework/tests/``
        when *None*.  Pass any :class:`~pathlib.Path` to scan a different
        location (e.g. a project-level tests folder or an external directory).
    """
    search = directory if directory is not None else _TESTS_DIR
    return sorted(search.glob("test_*.py"))


def _discover_json_files(directory: Optional[Path] = None) -> List[Path]:
    """Return sorted list of ``*_test_cases.json`` files.

    Parameters
    ----------
    directory:
        Directory to scan.  Defaults to ``GM_VIP_Automation_Framework/``
        when *None*.  Pass any :class:`~pathlib.Path` to scan a different
        location.
    """
    from GM_VIP_Automation_Framework.runner import discover_test_case_files
    search = directory if directory is not None else _FRAMEWORK_DIR
    return discover_test_case_files(str(search))


def _suite_label(path: Path) -> str:
    """Convert a test file path to a short label for display / selection.

    Examples
    --------
    tests/test_sanity.py       → ``test_sanity``
    sanity_test_cases.json     → ``sanity``
    """
    stem = path.stem
    if stem.endswith("_test_cases"):
        stem = stem[: -len("_test_cases")]
    return stem


def _resolve_suite_path(
    name_or_path: str,
    directory: Optional[Path] = None,
) -> Optional[Path]:
    """Resolve a ``--suite`` argument to a concrete file path.

    Accepts either:

    - A **direct file path** (absolute or relative) pointing to any
      ``*.py`` file, e.g. ``/path/to/test_ecu.py`` or
      ``../other/test_foo.py``.  The file must exist.
    - A **label** (file stem without ``.py``), e.g. ``test_sanity``, looked
      up inside *directory* (defaults to ``tests/``).

    Returns *None* when no matching file is found.
    """
    # Try as a direct path first.
    p = Path(name_or_path)
    if p.is_file():
        return p.resolve()

    # Fall back to label-based discovery.
    suites = _discover_python_suites(directory)
    matches = [s for s in suites if _suite_label(s) == name_or_path]
    return matches[0] if matches else None


def _resolve_json_path(
    label_or_path: str,
    directory: Optional[Path] = None,
) -> Optional[Path]:
    """Resolve a ``--json`` argument to a concrete file path.

    Accepts either:

    - A **direct file path** (absolute or relative) pointing to any
      ``*_test_cases.json`` file, e.g.
      ``/path/to/stress_test_cases.json``.  The file must exist.
    - A **label** (everything before ``_test_cases``), e.g. ``sanity``
      for ``sanity_test_cases.json``, looked up inside *directory*
      (defaults to the framework root).

    Returns *None* when no matching file is found.
    """
    # Try as a direct path first.
    p = Path(label_or_path)
    if p.is_file():
        return p.resolve()

    # Fall back to label-based discovery.
    json_files = _discover_json_files(directory)
    matches = [f for f in json_files if _suite_label(f) == label_or_path]
    return matches[0] if matches else None


def _load_module(path: Path):
    """Dynamically load a Python module from *path*."""
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _print_list(directory: Optional[Path] = None) -> None:
    """Print all discovered Python suites and JSON test case files.

    Parameters
    ----------
    directory:
        Directory to scan for test files.  When *None* the defaults apply
        (``tests/`` for Python suites, framework root for JSON files).
        Pass a path to inspect a custom location.
    """
    py_suites  = _discover_python_suites(directory)
    json_files = _discover_json_files(directory)

    scan_label = str(directory) if directory else "(default locations)"

    print("\n╔══════════════════════════════════════════════════════════════╗")
    print(  "║          GM VIP Automation Framework – Available Suites      ║")
    print(  "╚══════════════════════════════════════════════════════════════╝\n")
    print(f"  Scanning: {scan_label}\n")

    print("  Python test suites  (--suite <name> [--mode mock|live])")
    print("  ─────────────────────────────────────────────────────────────")
    if py_suites:
        for p in py_suites:
            print(f"    {_suite_label(p):<30}  {p.relative_to(_REPO_ROOT)}")
    else:
        print("    (none found in tests/)")

    print()
    print("  JSON test-case files  (--json <label> [--auto-launch])")
    print("  ─────────────────────────────────────────────────────────────")
    if json_files:
        for f in json_files:
            print(f"    {_suite_label(f):<30}  {f.name}")
    else:
        print("    (none found – add a '*_test_cases.json' file to enable)")

    print()
    print("  Mode flag  (applies to --suite; JSON suites always need live hardware)")
    print("  ─────────────────────────────────────────────────────────────")
    print("    --mode mock  (default)  All T32 calls simulated – no hardware needed")
    print("    --mode live             Detect running Trace32, connect automatically")
    print("                           Add --auto-launch to also start T32 if not open")
    print()
    print("  Additional per-test-file hardware toggles (live mode)")
    print("  ─────────────────────────────────────────────────────────────")
    print("    USE_CANOE        = False   ← flip to True for Vector CANoe stimulus")
    print("    USE_CAN_BUS      = False   ← flip to True for python-can adapter")
    print("    USE_POWER_SUPPLY = False   ← flip to True for BK Precision 1687B PSU")
    print()


# ---------------------------------------------------------------------------
# T32 pre-flight: detect running instance or launch
# ---------------------------------------------------------------------------

def _ensure_t32_running(
    auto_launch: bool = False,
    cmm_script: Optional[str] = None,
) -> None:
    """Verify Trace32 is reachable on the configured port; launch it if not.

    This is called **before** a live-mode Python test module is loaded.
    Test files like ``test_sanity.py`` open a real ``T32Connection`` at
    *import time*, so Trace32 must already be listening on its RCL port
    by the time :func:`_load_module` runs.

    Behaviour
    ---------
    1. Probe the configured RCL port (default 20000).
    2. If Trace32 is already running  → print a status message and return.
    3. If not running and *auto_launch* is ``True``
       → launch Trace32 (using ``t32_exe_path`` from ``config.json``),
         then poll until the port is open (up to ``connect_max_wait_s``).
    4. If not running and *auto_launch* is ``False``
       → raise :exc:`T32ConnectionError` with a clear remediation hint.

    Parameters
    ----------
    auto_launch:
        Start Trace32 automatically when not already running.
    cmm_script:
        Optional CMM startup script passed via ``-s`` at launch time.
    """
    from GM_VIP_Automation_Framework.core.connection import T32Connection
    from GM_VIP_Automation_Framework.config import settings
    from GM_VIP_Automation_Framework.utils.exceptions import T32ConnectionError

    port = settings.rcl_port
    conn = T32Connection(
        exe_path=settings.t32_exe_path,
        config_path=settings.t32_config_path,
        port=port,
        protocol=settings.rcl_protocol,
        cmm_entry_script=cmm_script or settings.cmm_entry_script,
    )

    # ── Step 1: probe for a running instance ─────────────────────────────
    if conn.try_connect():
        print(
            f"[GM_VIP] Trace32 detected on port {port} "
            "– connecting to existing instance."
        )
        conn.disconnect()   # release our probe socket; the test module reconnects
        return

    # ── Step 2: T32 not found ─────────────────────────────────────────────
    if not auto_launch:
        raise T32ConnectionError(
            f"No running Trace32 found on port {port}. "
            "Start Trace32 manually and run your *.cmm startup script "
            "(which must open the RCL port), then re-run.  "
            "Alternatively, set --auto-launch to have the framework "
            "launch Trace32 automatically (requires t32_exe_path in config.json)."
        )

    # ── Step 3: launch and wait for the RCL port to open ─────────────────
    print(
        f"[GM_VIP] Trace32 not found on port {port} – launching automatically …"
    )
    conn.launch()

    deadline = _time.monotonic() + settings.connect_max_wait_s
    while _time.monotonic() < deadline:
        if conn.try_connect():
            conn.disconnect()
            print(f"[GM_VIP] Trace32 ready on port {port}.")
            return
        _time.sleep(1.0)

    raise T32ConnectionError(
        f"Trace32 was launched but did not open port {port} within "
        f"{settings.connect_max_wait_s}s.  Check that your CMM script "
        "includes 'RCL=NETASSIST / PORT=<port>' in config.t32."
    )


# ---------------------------------------------------------------------------
# Python suite runner
# ---------------------------------------------------------------------------

def _run_python_suite(
    suite_path: Path,
    mode: str = "mock",
    auto_launch: bool = False,
    cmm_script: Optional[str] = None,
    verbosity: int = 1,
) -> unittest.TestResult:
    """Load and run a single Python unittest file, generating an HTML report.

    Parameters
    ----------
    suite_path:
        Path to the ``test_*.py`` file.
    mode:
        ``"mock"`` (default) – stub all Trace32 calls; no hardware needed.
        ``"live"``           – connect to a real running Trace32 instance.
    auto_launch:
        When *mode* is ``"live"`` and Trace32 is not already running,
        launch it automatically.  Ignored in mock mode.
    cmm_script:
        Optional CMM startup script passed at launch time (live mode only).
    verbosity:
        Passed to :class:`~GM_VIP_Automation_Framework.html_report.SanityHtmlRunner`.
    """
    from GM_VIP_Automation_Framework.html_report import SanityHtmlRunner

    label      = _suite_label(suite_path)
    mode_upper = mode.upper()
    print(f"\n[GM_VIP] Suite: {suite_path.name}  [mode={mode_upper}]")

    # ------------------------------------------------------------------
    # Prepare the execution environment BEFORE the module is imported.
    #
    # Why before import?
    #   Test files like test_sanity.py run module-level code at import
    #   time that depends on USE_LIVE_T32:
    #     - mock mode → stubs lauterbach.trace32.rcl
    #     - live mode → opens a real T32Connection
    #   We must configure sys.modules / sys.argv *before* exec_module()
    #   so those decisions are made correctly.
    # ------------------------------------------------------------------
    argv_saved = sys.argv[:]

    if mode.lower() == "live":
        # Pre-flight: ensure T32 is reachable before the module imports
        # and tries to connect.  Launches T32 if --auto-launch is set.
        _ensure_t32_running(auto_launch=auto_launch, cmm_script=cmm_script)

        # Inject "live" at sys.argv[1] so the module's own argv-override
        # logic (the _LIVE_FLAGS check in test_sanity.py) activates
        # USE_LIVE_T32.  The flag is consumed and stripped by the module
        # itself, so the unittest argument parser never sees it.
        sys.argv = [sys.argv[0], "live"] + sys.argv[1:]
    else:
        # Mock mode: register lauterbach stubs so import-time code that
        # tries `import lauterbach.trace32.rcl` does not fail.
        from unittest.mock import MagicMock
        for _mod in (
            "lauterbach",
            "lauterbach.trace32",
            "lauterbach.trace32.rcl",
            "lauterbach.trace32.rcl._rc",
            "lauterbach.trace32.rcl._rc._error",
        ):
            sys.modules.setdefault(_mod, MagicMock())

    try:
        mod = _load_module(suite_path)
    finally:
        # Always restore sys.argv even if loading raises.
        sys.argv = argv_saved

    loader = unittest.TestLoader()
    suite  = loader.loadTestsFromModule(mod)

    runner = SanityHtmlRunner(
        suite_name=label,
        mode=mode_upper,
        verbosity=verbosity,
    )
    return runner.run(suite)


def _run_all_python_suites(
    mode: str = "mock",
    auto_launch: bool = False,
    cmm_script: Optional[str] = None,
    verbosity: int = 1,
) -> Dict[str, unittest.TestResult]:
    """Run every ``test_*.py`` file found in the tests/ directory."""
    results: Dict[str, unittest.TestResult] = {}
    suites = _discover_python_suites()
    if not suites:
        print("[GM_VIP] No Python test suites found in tests/.")
        return results
    for p in suites:
        results[_suite_label(p)] = _run_python_suite(
            p,
            mode=mode,
            auto_launch=auto_launch,
            cmm_script=cmm_script,
            verbosity=verbosity,
        )
    return results


# ---------------------------------------------------------------------------
# JSON suite runner
# ---------------------------------------------------------------------------

def _run_json_suite(
    label: str,
    auto_launch: bool = False,
    cmm_script: Optional[str] = None,
) -> None:
    """Run a single ``*_test_cases.json`` suite identified by *label*.

    The runner first probes the configured port for a running Trace32
    instance.  Only when Trace32 is not found *and* ``auto_launch`` is
    ``True`` will a new Trace32 process be started.
    """
    from GM_VIP_Automation_Framework import runner as _runner

    json_files = _discover_json_files()
    matches = [f for f in json_files if _suite_label(f) == label]

    if not matches:
        available = [_suite_label(f) for f in json_files]
        sys.exit(
            f"[GM_VIP] ERROR: No JSON suite named '{label}' found.\n"
            f"         Available labels: {available or ['(none)']}"
        )

    json_path = matches[0]
    print(
        f"\n[GM_VIP] Running JSON suite '{label}' from {json_path.name}  "
        "[mode=LIVE, detect-first]"
    )
    report = _runner.run_from_json(
        str(json_path),
        auto_launch=auto_launch,
        cmm_entry_script=cmm_script,
        resilient_connect=True,   # always detect existing T32 first
    )
    print(f"[GM_VIP] Suite '{label}' done: {report.summary()}")


def _run_all_json_suites(
    auto_launch: bool = False,
    cmm_script: Optional[str] = None,
) -> None:
    """Run every ``*_test_cases.json`` discovered in the framework directory."""
    from GM_VIP_Automation_Framework import runner as _runner

    json_files = _discover_json_files()
    if not json_files:
        print(
            "[GM_VIP] No '*_test_cases.json' files found. "
            "Add a JSON file (e.g. 'stress_test_cases.json') to run more suites."
        )
        return

    print(
        f"\n[GM_VIP] Running all JSON suites  "
        f"[mode=LIVE, detect-first, auto_launch={auto_launch}]"
    )
    results = _runner.run_all_discovered(
        str(_FRAMEWORK_DIR),
        auto_launch=auto_launch,
        cmm_entry_script=cmm_script,
        resilient_connect=True,
    )
    print(f"\n[GM_VIP] All JSON suites complete. {len(results)} suite(s) ran.")


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python main.py",
        description=(
            "GM VIP Automation Framework – test execution entry point.\n\n"
            "Examples:\n"
            "  python main.py --list\n"
            "  python main.py --suite test_sanity                  # mock (default)\n"
            "  python main.py --suite test_sanity --mode live      # real hardware\n"
            "  python main.py --suite all --mode live\n"
            "  python main.py --json sanity                        # detect T32, connect\n"
            "  python main.py --json sanity --auto-launch          # launch T32 if needed\n"
            "  python main.py --json all\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all available Python suites and JSON test-case files, then exit.",
    )
    parser.add_argument(
        "--suite",
        metavar="NAME",
        help=(
            "Python test suite to run.  Pass the file stem without .py "
            "(e.g. 'test_sanity') or 'all' to run every test_*.py file."
        ),
    )
    parser.add_argument(
        "--json",
        metavar="LABEL",
        help=(
            "JSON test-case suite to run.  The framework detects a running "
            "Trace32 first; use --auto-launch if Trace32 is not yet open.  "
            "Pass the label (e.g. 'sanity' for 'sanity_test_cases.json') "
            "or 'all' to run every '*_test_cases.json' file."
        ),
    )
    parser.add_argument(
        "--mode",
        choices=["mock", "live"],
        default="mock",
        help=(
            "Hardware mode for Python test suites (default: mock).  "
            "'mock' – no hardware needed, all T32 calls are simulated.  "
            "'live' – detect running Trace32 on the configured port and "
            "connect automatically; use --auto-launch if T32 is not open.  "
            "Note: JSON suites (--json) always run in live mode regardless "
            "of this flag."
        ),
    )
    parser.add_argument(
        "--auto-launch",
        action="store_true",
        dest="auto_launch",
        help=(
            "Launch Trace32 automatically when it is not already running.  "
            "Requires t32_exe_path (and t32_config_path) to be set in "
            "config.json.  Applies to both --mode live and --json runs."
        ),
    )
    parser.add_argument(
        "--cmm",
        metavar="PATH",
        dest="cmm_script",
        default=None,
        help=(
            "Path to a CMM startup script (*.cmm) passed to Trace32 via "
            "the -s flag at launch time.  Only used when --auto-launch is set."
        ),
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Increase verbosity of unittest output.",
    )
    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> None:
    parser = _build_parser()
    args   = parser.parse_args(argv)

    verbosity = 2 if args.verbose else 1

    if args.list:
        _print_list()
        return

    if not args.suite and not args.json:
        # No target specified – show the list and a usage hint.
        _print_list()
        print("Tip: run  python main.py --help  for full usage information.")
        return

    # ------------------------------------------------------------------
    # Python test suites
    # ------------------------------------------------------------------
    if args.suite:
        if args.auto_launch and args.mode == "mock":
            print(
                "[GM_VIP] Note: --auto-launch has no effect in mock mode "
                "(no real Trace32 connection is opened)."
            )

        if args.suite.lower() == "all":
            _run_all_python_suites(
                mode=args.mode,
                auto_launch=args.auto_launch,
                cmm_script=args.cmm_script,
                verbosity=verbosity,
            )
        else:
            suites  = _discover_python_suites()
            matches = [p for p in suites if _suite_label(p) == args.suite]
            if not matches:
                available = [_suite_label(p) for p in suites]
                sys.exit(
                    f"[GM_VIP] ERROR: No Python suite named '{args.suite}'.\n"
                    f"         Available: {available or ['(none)']}"
                )
            _run_python_suite(
                matches[0],
                mode=args.mode,
                auto_launch=args.auto_launch,
                cmm_script=args.cmm_script,
                verbosity=verbosity,
            )

    # ------------------------------------------------------------------
    # JSON test-case suites (always live Trace32, detect-first)
    # ------------------------------------------------------------------
    if args.json:
        if args.mode == "mock":
            print(
                "[GM_VIP] Note: JSON suites always connect to a real Trace32 "
                "instance (--mode mock is ignored for --json runs)."
            )

        if args.json.lower() == "all":
            _run_all_json_suites(
                auto_launch=args.auto_launch,
                cmm_script=args.cmm_script,
            )
        else:
            _run_json_suite(
                args.json,
                auto_launch=args.auto_launch,
                cmm_script=args.cmm_script,
            )


if __name__ == "__main__":
    main()

