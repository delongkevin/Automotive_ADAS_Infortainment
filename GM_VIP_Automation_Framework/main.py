"""
GM VIP Automation Framework – Main Execution Entry Point
=========================================================
Single entry point for running any test suite or JSON-driven test file.

Quick start
-----------
List everything available::

    python main.py --list

Run the sanity Python test suite (mock mode – no hardware needed)::

    python main.py --suite test_sanity

Run all Python test suites::

    python main.py --suite all

Run the sanity JSON test cases against a live Trace32 instance::

    python main.py --json sanity

Run every ``*_test_cases.json`` file discovered automatically::

    python main.py --json all

Adding a new suite
------------------
Python suite
    Add ``tests/my_new_test.py`` (standard unittest file).
    It is picked up automatically by ``--suite all``.

JSON suite (no Python edits required)
    Add ``my_new_test_cases.json`` to the framework directory.
    It is picked up automatically by ``--json all``.

Hardware toggles (for Python suites)
--------------------------------------
Inside each Python test file (e.g. ``test_sanity.py``) there are
module-level flags that enable live hardware:

    USE_LIVE_T32    = False   # flip to True for real Trace32 connection
    USE_CANOE       = False   # flip to True for Vector CANoe stimulus
    USE_CAN_BUS     = False   # flip to True for python-can adapter
    USE_POWER_SUPPLY = False  # flip to True for BK Precision 1687B PSU

These can also be overridden via command-line argument (see ``--help``).
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
import unittest
from pathlib import Path
from typing import Dict, List, Optional

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

def _discover_python_suites() -> List[Path]:
    """Return sorted list of ``test_*.py`` files in the tests/ directory."""
    return sorted(_TESTS_DIR.glob("test_*.py"))


def _discover_json_files() -> List[Path]:
    """Return sorted list of ``*_test_cases.json`` files in the framework dir."""
    from GM_VIP_Automation_Framework.runner import discover_test_case_files
    return discover_test_case_files(str(_FRAMEWORK_DIR))


def _suite_label(path: Path) -> str:
    """Convert a test file path to a short label for display / selection.

    Examples
    --------
    tests/test_sanity.py          → ``test_sanity``
    sanity_test_cases.json        → ``sanity``
    """
    stem = path.stem
    if stem.endswith("_test_cases"):
        stem = stem[: -len("_test_cases")]
    return stem


def _load_module(path: Path):
    """Dynamically load a Python module from *path*."""
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _print_list() -> None:
    """Print all discovered Python suites and JSON test case files."""
    py_suites  = _discover_python_suites()
    json_files = _discover_json_files()

    print("\n╔══════════════════════════════════════════════════════════════╗")
    print(  "║          GM VIP Automation Framework – Available Suites      ║")
    print(  "╚══════════════════════════════════════════════════════════════╝\n")

    print("  Python test suites  (use with  --suite <name>  or  --suite all)")
    print("  ─────────────────────────────────────────────────────────────")
    if py_suites:
        for p in py_suites:
            print(f"    {_suite_label(p):<30}  {p.relative_to(_REPO_ROOT)}")
    else:
        print("    (none found in tests/)")

    print()
    print("  JSON test-case files  (use with  --json <label>  or  --json all)")
    print("  ─────────────────────────────────────────────────────────────")
    if json_files:
        for f in json_files:
            print(f"    {_suite_label(f):<30}  {f.name}")
    else:
        print("    (none found – add a '*_test_cases.json' file to enable)")

    print()
    print("  Hardware toggles (inside each test_*.py file)")
    print("  ─────────────────────────────────────────────────────────────")
    print("    USE_LIVE_T32     = False   ← flip to True for real Trace32")
    print("    USE_CANOE        = False   ← flip to True for Vector CANoe")
    print("    USE_CAN_BUS      = False   ← flip to True for python-can")
    print("    USE_POWER_SUPPLY = False   ← flip to True for BK Precision PSU")
    print()


# ---------------------------------------------------------------------------
# Python suite runner
# ---------------------------------------------------------------------------

def _run_python_suite(suite_path: Path, verbosity: int = 1) -> unittest.TestResult:
    """Load and run a single Python unittest file, generating an HTML report."""
    from GM_VIP_Automation_Framework.html_report import SanityHtmlRunner

    label = _suite_label(suite_path)
    print(f"\n[GM_VIP] Loading Python suite: {suite_path.name}")

    # Stub lauterbach stubs if test file is run standalone (not via conftest).
    from unittest.mock import MagicMock
    for mod_name in (
        "lauterbach",
        "lauterbach.trace32",
        "lauterbach.trace32.rcl",
        "lauterbach.trace32.rcl._rc",
        "lauterbach.trace32.rcl._rc._error",
    ):
        sys.modules.setdefault(mod_name, MagicMock())

    mod = _load_module(suite_path)

    loader = unittest.TestLoader()
    suite  = loader.loadTestsFromModule(mod)

    # Determine mode label from module flag (if present).
    mode = "LIVE" if getattr(mod, "USE_LIVE_T32", False) else "MOCK"

    runner = SanityHtmlRunner(
        suite_name=label,
        mode=mode,
        verbosity=verbosity,
    )
    return runner.run(suite)


def _run_all_python_suites(verbosity: int = 1) -> Dict[str, unittest.TestResult]:
    results: Dict[str, unittest.TestResult] = {}
    suites = _discover_python_suites()
    if not suites:
        print("[GM_VIP] No Python test suites found in tests/.")
        return results
    for p in suites:
        results[_suite_label(p)] = _run_python_suite(p, verbosity=verbosity)
    return results


# ---------------------------------------------------------------------------
# JSON suite runner
# ---------------------------------------------------------------------------

def _run_json_suite(label: str) -> None:
    """Run a single ``*_test_cases.json`` suite identified by *label*."""
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
    print(f"\n[GM_VIP] Running JSON suite '{label}' from {json_path.name} …")
    report = _runner.run_from_json(str(json_path))
    print(f"[GM_VIP] Suite '{label}' done: {report.summary()}")


def _run_all_json_suites() -> None:
    """Run every ``*_test_cases.json`` discovered in the framework directory."""
    from GM_VIP_Automation_Framework import runner as _runner

    json_files = _discover_json_files()
    if not json_files:
        print(
            "[GM_VIP] No '*_test_cases.json' files found. "
            "Add a JSON file (e.g. 'stress_test_cases.json') to run more suites."
        )
        return

    results = _runner.run_all_discovered(str(_FRAMEWORK_DIR))
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
            "  python main.py --list                   # show available suites\n"
            "  python main.py --suite test_sanity      # run Python sanity suite\n"
            "  python main.py --suite all              # run all Python suites\n"
            "  python main.py --json sanity            # run sanity JSON file\n"
            "  python main.py --json all               # run all JSON files\n"
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
            "JSON test-case suite to run against a live Trace32 instance.  "
            "Pass the label (e.g. 'sanity' for 'sanity_test_cases.json') "
            "or 'all' to run every '*_test_cases.json' file."
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
        # No arguments – show list and a brief usage hint.
        _print_list()
        print("Tip: run  python main.py --help  for usage information.")
        return

    if args.suite:
        if args.suite.lower() == "all":
            _run_all_python_suites(verbosity=verbosity)
        else:
            # Find the matching file by label.
            suites  = _discover_python_suites()
            matches = [p for p in suites if _suite_label(p) == args.suite]
            if not matches:
                available = [_suite_label(p) for p in suites]
                sys.exit(
                    f"[GM_VIP] ERROR: No Python suite named '{args.suite}'.\n"
                    f"         Available: {available or ['(none)']}"
                )
            _run_python_suite(matches[0], verbosity=verbosity)

    if args.json:
        if args.json.lower() == "all":
            _run_all_json_suites()
        else:
            _run_json_suite(args.json)


if __name__ == "__main__":
    main()
