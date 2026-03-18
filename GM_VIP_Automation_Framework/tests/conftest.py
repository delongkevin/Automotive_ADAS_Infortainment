"""
conftest.py – inject lauterbach.trace32.rcl stubs before any test imports,
and register a pytest plugin that generates an HTML report after each session.
This allows the framework to be imported in CI without the Lauterbach library
installed, while still producing a professional HTML report for every run.
"""

import sys
import types
from unittest.mock import MagicMock


def _make_lauterbach_stubs():
    """Create minimal module stubs for lauterbach.trace32.rcl."""
    lauterbach = types.ModuleType("lauterbach")
    trace32 = types.ModuleType("lauterbach.trace32")
    rcl = MagicMock(name="lauterbach.trace32.rcl")
    rc = MagicMock(name="lauterbach.trace32.rcl._rc")
    error = MagicMock(name="lauterbach.trace32.rcl._rc._error")

    lauterbach.trace32 = trace32
    trace32.rcl = rcl

    sys.modules.setdefault("lauterbach", lauterbach)
    sys.modules.setdefault("lauterbach.trace32", trace32)
    sys.modules.setdefault("lauterbach.trace32.rcl", rcl)
    sys.modules.setdefault("lauterbach.trace32.rcl._rc", rc)
    sys.modules.setdefault("lauterbach.trace32.rcl._rc._error", error)


_make_lauterbach_stubs()


# ---------------------------------------------------------------------------
# Pytest plugin: generate HTML report after every test session
# ---------------------------------------------------------------------------

import datetime  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import List, Tuple  # noqa: E402


def pytest_configure(config):
    """Register the HTML-report plugin with pytest."""
    config.pluginmanager.register(_HtmlReportPlugin(), "_gm_vip_html_report")


class _HtmlReportPlugin:
    """Collects per-test results and writes a single HTML report at session end."""

    def __init__(self):
        self._results: List[Tuple[str, str, str]] = []

    def pytest_runtest_logreport(self, report):
        """Called after each test setup, call, and teardown phase."""
        if report.when != "call":
            # Only capture the 'call' phase result.
            return
        name = report.nodeid
        if report.passed:
            self._results.append((name, "PASS", ""))
        elif report.failed:
            detail = str(report.longrepr) if report.longrepr else ""
            self._results.append((name, "FAIL", detail))
        elif report.skipped:
            reason = str(report.longrepr) if report.longrepr else ""
            self._results.append((name, "SKIP", reason))

    def pytest_sessionfinish(self, session, exitstatus):
        """Generate the HTML report at the end of the session."""
        if not self._results:
            return
        try:
            from GM_VIP_Automation_Framework.html_report import (
                make_report_dir,
                render_html,
            )
        except ImportError:
            return

        generated_at = datetime.datetime.now().isoformat(timespec="seconds")
        out_dir = make_report_dir()
        report_path = out_dir / "sanity_report.html"
        html = render_html(
            suite_name="GM_VIP_Sanity",
            results=self._results,
            generated_at=generated_at,
            mode="MOCK",
        )
        report_path.write_text(html, encoding="utf-8")
        print(f"\n[GM_VIP] HTML report saved → {report_path}", file=sys.stderr)
