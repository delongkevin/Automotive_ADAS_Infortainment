"""
GM VIP Automation Framework – JSON-driven Test Runner
======================================================
Loads one or more ``*_test_cases.json`` files and executes an entire test
suite against Trace32 without any changes to Python source code.

File naming convention
----------------------
All test-case JSON files follow the pattern ``*_test_cases.json``, where
``*`` is a free-form label (e.g. ``sanity``, ``stress``, ``powercycle``).
The runner auto-discovers every matching file in a directory so that adding
a new suite requires nothing more than dropping a new JSON file::

    sanity_test_cases.json     ← default sanity suite
    stress_test_cases.json     ← add this file to include stress tests
    powercycle_test_cases.json ← add this file for power-cycle tests

Configuration file
------------------
- **config.json** – Trace32 paths, ports, and timing settings.

Typical workflow
----------------
1. (Optional) Edit ``config.json`` to set ``rcl_port`` and, only if you
   need the framework to launch Trace32, ``t32_exe_path`` / ``t32_config_path``.
2. Edit (or add) ``*_test_cases.json`` to describe your test cases.
3. Start Trace32 manually (run your ``*.cmm`` startup script so that the
   API port is already open).
4. Run all discovered suites at once::

       python main.py --json all

   Or run a single suite by name (without the ``_test_cases.json`` suffix)::

       python main.py --json sanity

   Or invoke the runner directly from Python::

       from GM_VIP_Automation_Framework import runner
       runner.run_from_json('sanity_test_cases.json')

   The framework detects the running Trace32 instance automatically
   (``resilient_connect=True`` by default).  ``t32_exe_path`` in
   ``config.json`` is **not required** when Trace32 is already running.

   To supply a CMM startup script (launched via ``-s`` when Trace32 is
   not yet running)::

       runner.run_from_json(
           'sanity_test_cases.json',
           cmm_entry_script=r'C:\\workspace\\tc4d9xe_debug.cmm',
           auto_launch=True,
       )

Test-case JSON schema
---------------------
Each entry in the ``test_cases`` list supports:

- ``name`` (str, required) – unique test case identifier.
- ``enabled`` (bool, default ``true``) – skip when ``false``.
- ``reset_before`` (bool, default ``false``) – issue ``SYStem.RESetTarget``
  and wait for halt before running the test.
- ``go_before_check`` (bool, default ``false``) – after writing
  ``variables_write`` and setting any ``breakpoints``, issue ``GO`` and
  wait for the ECU to halt *before* reading ``variables_check``.
- ``breakpoints`` (list[str]) – symbols at which to set execution
  breakpoints.
- ``variables_write`` (dict) – variables to write before the GO step.
- ``variables_check`` (dict) – variables to read (and optionally assert)
  after the ECU halts.
- ``symbols_inspect`` (list[str]) – symbols whose existence and address
  are logged (no assertion).

Public API
----------
- :func:`run_from_json` – load a single JSON file and execute the suite.
- :func:`load_test_cases` – parse a ``*_test_cases.json`` into a list of
  dicts (useful for inspection / custom runners).
- :func:`discover_test_case_files` – find all ``*_test_cases.json`` files
  in a directory.
- :func:`run_all_discovered` – discover and run every ``*_test_cases.json``
  in a directory, returning a mapping of suite name → report.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import GM_VIP_Automation_Framework as t32
from .config import settings
from .report import TestCaseReport

__all__ = [
    "run_from_json",
    "load_test_cases",
    "discover_test_case_files",
    "run_all_discovered",
]


# ---------------------------------------------------------------------------
# Schema helpers
# ---------------------------------------------------------------------------

def load_test_cases(path: str) -> List[Dict[str, Any]]:
    """Parse a ``test_cases.json`` file and return the list of test-case dicts.

    Parameters
    ----------
    path:
        Path to the ``test_cases.json`` file.

    Returns
    -------
    list[dict]
        Each element is a raw test-case definition dict (keys: ``name``,
        ``capl_reference``, ``enabled``, ``reset_before``, ``breakpoints``,
        ``variables_write``, ``variables_check``, ``symbols_inspect``).

    Raises
    ------
    FileNotFoundError
        When *path* does not exist.
    ValueError
        When the file is not valid JSON or is missing the ``test_cases`` key.
    """
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"test_cases.json not found: {path}")
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in '{path}': {exc}") from exc

    if "test_cases" not in raw:
        raise ValueError(f"'{path}' must contain a top-level 'test_cases' list.")
    return raw["test_cases"]


# ---------------------------------------------------------------------------
# Discovery helpers
# ---------------------------------------------------------------------------

def discover_test_case_files(directory: str = ".") -> List[Path]:
    """Find all ``*_test_cases.json`` files in *directory*.

    The naming convention ``*_test_cases.json`` allows any number of test
    suites to coexist in the same folder.  Adding a new suite requires only
    dropping a new JSON file – no Python changes are needed::

        sanity_test_cases.json
        stress_test_cases.json
        powercycle_test_cases.json

    Parameters
    ----------
    directory:
        Directory to search.  Defaults to the current working directory.

    Returns
    -------
    list[Path]
        Sorted list of discovered ``*_test_cases.json`` paths.
    """
    base = Path(directory)
    return sorted(base.glob("*_test_cases.json"))


def run_all_discovered(
    directory: str = ".",
    config_json_path: Optional[str] = None,
    auto_launch: bool = False,
    cmm_entry_script: Optional[str] = None,
    resilient_connect: bool = True,
) -> Dict[str, TestCaseReport]:
    """Discover and run every ``*_test_cases.json`` in *directory*.

    This is the simplest way to execute all available test suites without
    specifying individual file names.  Reports are saved automatically next
    to each JSON file (``<name>_report.json`` and ``<name>_report.html``).

    Parameters
    ----------
    directory:
        Directory to scan for ``*_test_cases.json`` files.
    config_json_path:
        Path to ``config.json``.  When *None* the function looks for a
        ``config.json`` in *directory*.
    auto_launch:
        Launch Trace32 automatically if not already running.
    cmm_entry_script:
        Optional CMM startup script path.
    resilient_connect:
        Try connecting to a running Trace32 instance before launching.

    Returns
    -------
    dict[str, TestCaseReport]
        Mapping of suite label (file stem without ``_test_cases`` suffix) to
        its completed :class:`~report.TestCaseReport`.

    Raises
    ------
    FileNotFoundError
        When no ``*_test_cases.json`` files are found in *directory*.
    """
    files = discover_test_case_files(directory)
    if not files:
        raise FileNotFoundError(
            f"No '*_test_cases.json' files found in '{directory}'. "
            "Create a JSON file following the naming convention "
            "(e.g. 'sanity_test_cases.json') to define a test suite."
        )

    results: Dict[str, TestCaseReport] = {}
    for json_path in files:
        # Derive a short suite label: "sanity_test_cases" → "sanity"
        label = json_path.stem
        if label.endswith("_test_cases"):
            label = label[: -len("_test_cases")]
        print(f"\n[GM_VIP] Running suite '{label}' from {json_path.name} …")
        report = run_from_json(
            test_cases_path=str(json_path),
            config_json_path=config_json_path,
            auto_launch=auto_launch,
            cmm_entry_script=cmm_entry_script,
            resilient_connect=resilient_connect,
        )
        results[label] = report
        print(f"[GM_VIP] Suite '{label}' done: {report.summary()}")

    return results


# ---------------------------------------------------------------------------
# Core runner
# ---------------------------------------------------------------------------

def run_from_json(
    test_cases_path: str,
    config_json_path: Optional[str] = None,
    auto_launch: bool = False,
    cmm_entry_script: Optional[str] = None,
    resilient_connect: bool = True,
    report_json: Optional[str] = None,
    report_html: Optional[str] = None,
) -> TestCaseReport:
    """Load ``test_cases.json`` (and optionally ``config.json``) and run all
    enabled test cases against Trace32.

    Parameters
    ----------
    test_cases_path:
        Path to the ``test_cases.json`` file that defines the test suite.
    config_json_path:
        Path to ``config.json``.  When *None* the function looks for a
        ``config.json`` file in the same directory as *test_cases_path*.
        Pass ``""`` to skip JSON config loading entirely (use current
        :data:`~config.settings` values or environment variables).
    auto_launch:
        When ``True`` the Trace32 process is started before connecting
        (only needed when Trace32 is not already running).  When
        *resilient_connect* is ``True`` (the default) the process is only
        launched if an initial connection attempt fails.
    cmm_entry_script:
        Optional path to a CMM (``*.cmm``) startup script.  When supplied
        (or when :attr:`~config.T32Settings.cmm_entry_script` is set in
        the config) and Trace32 needs to be launched, the script is passed
        to Trace32 via the ``-s`` flag so it executes at startup and can
        perform all hardware setup (symbol loading, API port opening, etc.).
        Leave ``None`` when Trace32 is already running with the script
        having been executed separately.
    resilient_connect:
        When ``True`` (default) the framework first attempts to connect to
        an already-running Trace32 instance on the configured RCL port.
        If that succeeds, no launch is performed and ``exe_path`` in
        ``config.json`` is not required.  Only when the initial connection
        attempt fails *and* *auto_launch* is ``True`` will a new Trace32
        process be started.  Set to ``False`` to restore the original
        behaviour where *auto_launch* unconditionally starts a new process.
    report_json:
        Output path for the JSON report.  Defaults to
        ``<test_cases_path_stem>_report.json``.
    report_html:
        Output path for the HTML report.  Defaults to
        ``<test_cases_path_stem>_report.html``.

    Returns
    -------
    TestCaseReport
        The completed report object (results already saved to disk when
        *report_json* / *report_html* are not ``None``).
    """
    tc_path = Path(test_cases_path)

    # ------------------------------------------------------------------
    # 1. Load config.json into settings
    # ------------------------------------------------------------------
    if config_json_path is None:
        candidate = tc_path.parent / "config.json"
        if candidate.is_file():
            config_json_path = str(candidate)

    if config_json_path:
        settings.load_from_json(config_json_path)

    # ------------------------------------------------------------------
    # 2. Parse test_cases.json
    # ------------------------------------------------------------------
    raw_json = json.loads(tc_path.read_text(encoding="utf-8"))
    suite_name = raw_json.get("test_suite", tc_path.stem)
    test_case_defs = raw_json.get("test_cases", [])

    # ------------------------------------------------------------------
    # 3. Resolve CMM entry script (parameter overrides settings)
    # ------------------------------------------------------------------
    entry_script = cmm_entry_script if cmm_entry_script is not None else settings.cmm_entry_script

    # ------------------------------------------------------------------
    # 4. Connect to Trace32
    # ------------------------------------------------------------------
    report = TestCaseReport(name=suite_name)
    conn = t32.T32Connection(
        exe_path=settings.t32_exe_path,
        config_path=settings.t32_config_path,
        port=settings.rcl_port,
        protocol=settings.rcl_protocol,
        cmm_entry_script=entry_script,
    )

    if resilient_connect:
        # Try to connect to a running instance first.
        if not conn.try_connect():
            if auto_launch:
                conn.launch()
            else:
                from .utils.exceptions import T32ConnectionError
                raise T32ConnectionError(
                    f"No running Trace32 found on port {settings.rcl_port}. "
                    "Start Trace32 manually (your *.cmm script can open the API "
                    "port), or set auto_launch=True to have the framework launch "
                    "Trace32 automatically."
                )
    elif auto_launch:
        conn.launch()

    with conn:
        if not conn.is_connected():
            conn.connect()

        import GM_VIP_Automation_Framework.core.debugger as _dbg
        _dbg.default_connection = conn

        # ------------------------------------------------------------------
        # 5. Execute each test case
        # ------------------------------------------------------------------
        for tc_def in test_case_defs:
            # Skip disabled or comment-only entries.
            if not tc_def.get("enabled", True):
                continue
            # Skip entries that are just _comment lines (no "name" key).
            if "name" not in tc_def:
                continue

            _run_one(tc_def, conn, report)

        # Clean up default connection reference.
        _dbg.default_connection = None

    # ------------------------------------------------------------------
    # 6. Save reports
    # ------------------------------------------------------------------
    stem = str(tc_path.with_suffix(""))
    if report_json is None:
        report_json = f"{stem}_report.json"
    if report_html is None:
        report_html = f"{stem}_report.html"

    report.save_json(report_json)
    report.save_html(report_html)
    return report


# ---------------------------------------------------------------------------
# Single test-case executor
# ---------------------------------------------------------------------------

def _run_one(tc_def: dict, conn: t32.T32Connection, report: TestCaseReport) -> None:
    """Execute a single test case defined by *tc_def* and record results."""
    name = tc_def["name"]
    capl_ref = tc_def.get("capl_reference", "")
    reset_before = tc_def.get("reset_before", False)
    breakpoints: List[str] = tc_def.get("breakpoints", [])
    variables_write: Dict[str, Any] = tc_def.get("variables_write", {})
    variables_check: Dict[str, Any] = tc_def.get("variables_check", {})
    symbols_inspect: List[str] = tc_def.get("symbols_inspect", [])
    # When True: after variable writes and breakpoint setup, issue GO and
    # wait for the ECU to halt before reading variables.  Use this when the
    # ECU must run its initialisation / processing code before the variables
    # you want to check reach their expected values.
    go_before_check: bool = tc_def.get("go_before_check", False)

    report.begin_test_case(name)
    # Store CAPL reference as a special variable entry for traceability.
    if capl_ref:
        report.record_variable("_capl_reference", capl_ref)

    try:
        # -- Optional reset -------------------------------------------------
        if reset_before:
            t32.reset_target(connection=conn)
        t32.delete_all_breakpoints(connection=conn)

        # -- Inspect symbols ------------------------------------------------
        for sym in symbols_inspect:
            exists = t32.symbol_exists(sym, connection=conn)
            addr = ""
            if exists:
                try:
                    addr = t32.get_symbol_address(sym, connection=conn)
                except Exception:  # noqa: BLE001
                    addr = "N/A"
            report.record_symbol(sym, exists=exists, address=addr)

        # -- Write pre-condition variables ----------------------------------
        for sym, spec in variables_write.items():
            # Accept both {"value": "1", ...} dict and plain string "1".
            val = spec["value"] if isinstance(spec, dict) else str(spec)
            t32.set_variable(sym, val, connection=conn)
            report.record_variable(f"{sym} (write)", val)

        # -- Set breakpoints ------------------------------------------------
        if breakpoints:
            for sym in breakpoints:
                t32.set_breakpoint(sym, connection=conn)

        # -- GO + wait-for-halt (either via breakpoint or go_before_check) --
        # Case A: explicit breakpoints → GO + wait for each breakpoint hit.
        # Case B: go_before_check=True, no breakpoints → GO + wait for any
        #         halt (e.g. ECU finishes init and reaches a natural break).
        if breakpoints:
            t32.go(connection=conn)

            for sym in breakpoints:
                t32.check_halted_at(sym, connection=conn)
                report.record_breakpoint(sym, hit=True)

        elif go_before_check:
            # Let the ECU run without any breakpoints set.  The ECU will
            # stop when it naturally halts (e.g. hits a programmed break,
            # completes an init sequence, or a watchdog fires).  This is
            # useful when variable values are only valid after the ECU has
            # executed some initialisation code.
            t32.go(connection=conn)
            halted = t32.wait_for_halt(connection=conn)
            if not halted:
                from .utils.exceptions import T32TimeoutError
                raise T32TimeoutError(
                    f"ECU did not halt within {settings.halt_timeout_s}s "
                    "after GO (go_before_check=true). "
                    "Ensure the ECU has a breakpoint or naturally halts."
                )

        # -- Read / validate variables --------------------------------------
        for sym, spec in variables_check.items():
            # Accept both {"expected": "0x01", ...} dict and plain None/string.
            if isinstance(spec, dict):
                expected = spec.get("expected")
            else:
                expected = spec  # None or a string value

            value = t32.read_variable(sym, connection=conn)
            report.record_variable(sym, value)

            if expected is not None:
                t32.check_variable(sym, str(expected), connection=conn)

        # -- Clean up -------------------------------------------------------
        t32.delete_all_breakpoints(connection=conn)
        report.pass_test_case()

    except Exception as exc:  # noqa: BLE001
        try:
            t32.delete_all_breakpoints(connection=conn)
        except Exception:  # noqa: BLE001
            pass
        report.fail_test_case(str(exc))
