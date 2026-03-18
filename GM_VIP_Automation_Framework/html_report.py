"""
GM VIP Automation Framework – HTML Test Report Generator
=========================================================
Provides a unittest-compatible test runner that generates a professional HTML
report after each test run.  The report is saved to::

    <repo_root>/GM_VIP_Automation_Framework/Test_Report/<YYYYMMDD_HHMM>/

Any Python test script in this framework should use :class:`SanityHtmlRunner`
as its runner to produce the standardised report automatically.

Usage
-----
Replace ``unittest.main()`` with::

    from GM_VIP_Automation_Framework.html_report import SanityHtmlRunner
    unittest.main(testRunner=SanityHtmlRunner(suite_name="MySuite"))

Or, for full control over the test loader::

    suite = unittest.TestLoader().loadTestsFromModule(my_module)
    runner = SanityHtmlRunner(suite_name="MySuite", verbosity=2)
    runner.run(suite)

Report hierarchy
----------------
The generated HTML is written to::

    <repo_root>/GM_VIP_Automation_Framework/Test_Report/<YYYYMMDD_HHMM>/sanity_report.html

where ``<stamp>`` is a shortened date-time string (e.g. ``20260318_1748``).

T32 symbol / timeout diagnostics
---------------------------------
When a test fails or errors, the failure detail is scanned for known T32 error
patterns (unknown symbols, timeout messages, breakpoint-not-reached errors).
If any are detected, a highlighted warning banner is inserted into the report
above the traceback so that root-cause analysis is faster.
"""

from __future__ import annotations

import datetime
import sys
import traceback
import unittest
from pathlib import Path
from typing import List, Optional, Tuple

__all__ = ["SanityHtmlRunner", "make_report_dir"]

# ---------------------------------------------------------------------------
# T32 diagnostic keyword patterns
# ---------------------------------------------------------------------------

# Substrings that indicate an unresolved / unknown symbol in a T32 error.
_UNKNOWN_SYMBOL_KEYWORDS: Tuple[str, ...] = (
    "t32symbolerror",
    "symbol not found",
    "unknown symbol",
    "symbolerror",
    "symbol.exist",
    "cannot find symbol",
    "address not found",
)

# Substrings that indicate a timeout waiting for the ECU.
_TIMEOUT_KEYWORDS: Tuple[str, ...] = (
    "t32timeouterror",
    "timeout",
    "timed out",
    "did not halt",
    "did not reach",
    "not running",
)

# Substrings that indicate a breakpoint was not reached.
_BP_NOT_REACHED_KEYWORDS: Tuple[str, ...] = (
    "t32breakpointnotreachederror",
    "breakpoint not reached",
    "halted at wrong",
    "expected.*halted",
)


def _classify_detail(detail: str) -> List[str]:
    """Return a list of human-readable diagnostic tags for *detail*."""
    lower = detail.lower()
    tags: List[str] = []
    if any(kw in lower for kw in _UNKNOWN_SYMBOL_KEYWORDS):
        tags.append("unknown-symbol")
    if any(kw in lower for kw in _TIMEOUT_KEYWORDS):
        tags.append("timeout")
    if any(kw in lower for kw in _BP_NOT_REACHED_KEYWORDS):
        tags.append("bp-not-reached")
    return tags


# ---------------------------------------------------------------------------
# Report directory helper
# ---------------------------------------------------------------------------

def make_report_dir(base: Optional[Path] = None) -> Path:
    """Create and return a timestamped report directory.

    Parameters
    ----------
    base:
        Repository root directory.  When *None* the root is inferred from
        this module's location (the parent of ``GM_VIP_Automation_Framework/``).

    Returns
    -------
    Path
        The newly created (or already-existing) directory::

            <base>/GM_VIP_Automation_Framework/Test_Report/<YYYYMMDD_HHMM>/
    """
    if base is None:
        # This file: <repo>/GM_VIP_Automation_Framework/html_report.py
        # repo root: two levels up  → parent.parent
        base = Path(__file__).resolve().parent.parent

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    report_dir = base / "GM_VIP_Automation_Framework" / "Test_Report" / stamp
    report_dir.mkdir(parents=True, exist_ok=True)
    return report_dir


# ---------------------------------------------------------------------------
# Status colour palette
# ---------------------------------------------------------------------------

_STATUS_COLOUR = {
    "PASS":  "#28a745",
    "FAIL":  "#dc3545",
    "ERROR": "#fd7e14",
    "SKIP":  "#6c757d",
}

_TAG_LABELS = {
    "unknown-symbol": ("⚠️ Unknown / unresolved T32 symbol",
                       "Verify the ELF is loaded and the symbol name is spelled correctly."),
    "timeout":        ("⏱️ T32 / ECU timeout",
                       "The ECU did not reach the expected state within the configured "
                       "timeout.  Check hardware connections and timing settings."),
    "bp-not-reached": ("🔴 Breakpoint not reached",
                       "The ECU halted at an unexpected address.  Confirm the breakpoint "
                       "symbol resolves to the correct code location in the loaded ELF."),
}


# ---------------------------------------------------------------------------
# HTML renderer
# ---------------------------------------------------------------------------

def _badge(status: str) -> str:
    colour = _STATUS_COLOUR.get(status, "#6c757d")
    return (
        f'<span style="background:{colour};color:#fff;padding:2px 10px;'
        f'border-radius:4px;font-weight:bold;font-size:0.88em">{status}</span>'
    )


def _diagnostic_banners(tags: List[str]) -> str:
    parts: List[str] = []
    for tag in tags:
        if tag in _TAG_LABELS:
            title, hint = _TAG_LABELS[tag]
            parts.append(
                f'<p style="background:#fff3cd;border-left:4px solid #ffc107;'
                f'padding:8px 12px;margin:6px 0;border-radius:0 4px 4px 0">'
                f'<strong>{title}</strong><br>'
                f'<span style="font-size:0.9em;color:#555">{hint}</span></p>'
            )
    return "\n".join(parts)


def render_html(
    suite_name: str,
    results: List[Tuple[str, str, str]],
    generated_at: str,
    mode: str = "MOCK",
) -> str:
    """Render a self-contained, professional HTML report.

    Parameters
    ----------
    suite_name:
        Human-readable suite name shown in the report header.
    results:
        List of ``(test_name, status, detail)`` tuples.  *detail* is a
        traceback / error string for FAIL/ERROR entries; empty for PASS.
        **PASS entries are included only in the summary table**, not in the
        detail section, to keep the report focused on actionable failures.
    generated_at:
        ISO-8601 timestamp string.
    mode:
        Connection mode label (``"MOCK"`` or ``"LIVE"``).

    Returns
    -------
    str
        A complete, self-contained HTML document.
    """
    total   = len(results)
    passed  = sum(1 for _, s, _ in results if s == "PASS")
    failed  = sum(1 for _, s, _ in results if s == "FAIL")
    skipped = sum(1 for _, s, _ in results if s == "SKIP")
    errored = sum(1 for _, s, _ in results if s == "ERROR")

    overall_ok = failed == 0 and errored == 0
    overall_colour = _STATUS_COLOUR["PASS"] if overall_ok else _STATUS_COLOUR["FAIL"]
    overall_label  = "✅ OVERALL: PASS" if overall_ok else "❌ OVERALL: FAIL"

    # --- Detail section (FAIL + ERROR only) --------------------------------
    non_pass = [(n, s, d) for n, s, d in results if s not in ("PASS",)]
    if non_pass:
        detail_blocks: List[str] = []
        for name, status, detail in non_pass:
            tags = _classify_detail(detail)
            banners = _diagnostic_banners(tags)
            safe_detail = (detail or "(no detail)").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            detail_blocks.append(f"""
        <details open>
          <summary style="padding:4px 0">{_badge(status)} <strong>{name}</strong></summary>
          <div style="margin-top:8px">
            {banners}
            <pre style="background:#f8f9fa;padding:12px;border-radius:4px;
                        overflow-x:auto;font-size:0.82em;white-space:pre-wrap;
                        border:1px solid #dee2e6;margin-top:6px">{safe_detail}</pre>
          </div>
        </details>""")
        details_html = "\n".join(detail_blocks)
    else:
        details_html = (
            '<p style="color:#28a745;font-size:1.05em;padding:12px;background:#d4edda;'
            'border-radius:6px">✅ All tests passed – no failures or errors to report.</p>'
        )

    # --- Summary table (all results) ----------------------------------------
    summary_rows = ""
    for name, status, _ in results:
        colour = _STATUS_COLOUR.get(status, "#6c757d")
        summary_rows += (
            f'<tr><td style="font-family:monospace;font-size:0.82em">{name}</td>'
            f'<td><span style="color:{colour};font-weight:bold">{status}</span></td></tr>\n'
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>T32 Sanity Report – {suite_name}</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: Arial, Helvetica, sans-serif;
      background: #f0f2f5;
      color: #222;
      padding: 28px 20px;
    }}
    .card {{
      background: #fff;
      border-radius: 10px;
      box-shadow: 0 2px 8px rgba(0,0,0,.10);
      padding: 22px 28px;
      margin-bottom: 24px;
    }}
    h1 {{ font-size: 1.65em; margin-bottom: 2px; }}
    h2 {{ font-size: 1.05em; color: #666; font-weight: normal; margin-bottom: 18px; }}
    h3 {{ font-size: 1.05em; border-bottom: 2px solid #e9ecef;
          padding-bottom: 8px; margin-bottom: 14px; }}
    .kpi-row {{ display: flex; gap: 28px; flex-wrap: wrap; margin: 16px 0 10px; }}
    .kpi {{ text-align: center; }}
    .kpi-num {{ font-size: 2.2em; font-weight: bold; line-height: 1.1; }}
    .kpi-lbl {{ font-size: 0.78em; color: #888; text-transform: uppercase; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ padding: 7px 12px; text-align: left; border-bottom: 1px solid #e9ecef; }}
    th {{ background: #f4f4f4; font-size: 0.82em; color: #555; font-weight: 600; }}
    tr:hover td {{ background: #fafbfc; }}
    details {{
      border: 1px solid #dee2e6;
      border-radius: 6px;
      margin-bottom: 12px;
      padding: 10px 14px;
    }}
    summary {{
      cursor: pointer;
      list-style: none;
      user-select: none;
    }}
    summary::-webkit-details-marker {{ display: none; }}
    summary:hover {{ color: #0056b3; }}
    .overall {{
      font-size: 1.15em;
      font-weight: bold;
      color: {overall_colour};
      margin: 10px 0 6px;
    }}
    .meta {{ color: #888; font-size: 0.83em; margin-top: 4px; }}
    .footer {{
      text-align: center;
      color: #bbb;
      font-size: 0.78em;
      margin-top: 36px;
    }}
    .note {{ color: #888; font-size: 0.83em; margin-bottom: 12px; }}
  </style>
</head>
<body>
  <!-- ═══ Header card ═══ -->
  <div class="card">
    <h1>🔬 T32 Sanity Test Report</h1>
    <h2>{suite_name} &nbsp;<span style="color:#aaa;font-size:0.9em">Mode: {mode}</span></h2>

    <div class="kpi-row">
      <div class="kpi">
        <div class="kpi-num">{total}</div>
        <div class="kpi-lbl">Total</div>
      </div>
      <div class="kpi">
        <div class="kpi-num" style="color:#28a745">{passed}</div>
        <div class="kpi-lbl">Pass</div>
      </div>
      <div class="kpi">
        <div class="kpi-num" style="color:#dc3545">{failed}</div>
        <div class="kpi-lbl">Fail</div>
      </div>
      <div class="kpi">
        <div class="kpi-num" style="color:#fd7e14">{errored}</div>
        <div class="kpi-lbl">Error</div>
      </div>
      <div class="kpi">
        <div class="kpi-num" style="color:#6c757d">{skipped}</div>
        <div class="kpi-lbl">Skip</div>
      </div>
    </div>

    <p class="overall">{overall_label}</p>
    <p class="meta">Generated: {generated_at}</p>
  </div>

  <!-- ═══ Failure / Error detail card ═══ -->
  <div class="card">
    <h3>Failure &amp; Error Details</h3>
    <p class="note">
      PASS results are intentionally omitted from this section to keep the
      report focused on actionable issues.  See the <em>Full Summary</em>
      table below for a complete list of all test outcomes.
    </p>
    {details_html}
  </div>

  <!-- ═══ Full summary card ═══ -->
  <div class="card">
    <h3>Full Test Summary</h3>
    <table>
      <thead><tr><th>Test Case</th><th>Status</th></tr></thead>
      <tbody>{summary_rows}</tbody>
    </table>
  </div>

  <div class="footer">
    GM VIP Automation Framework &middot; T32 Sanity Suite &middot; {generated_at}
  </div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Custom TestResult
# ---------------------------------------------------------------------------

class _HtmlTestResult(unittest.TextTestResult):
    """Extends :class:`unittest.TextTestResult` to accumulate
    ``(name, status, detail)`` tuples for subsequent HTML rendering.
    """

    def __init__(self, stream, descriptions, verbosity):
        super().__init__(stream, descriptions, verbosity)
        self._entries: List[Tuple[str, str, str]] = []

    @staticmethod
    def _short_name(test) -> str:
        return str(test)

    def addSuccess(self, test):
        super().addSuccess(test)
        self._entries.append((self._short_name(test), "PASS", ""))

    def addFailure(self, test, err):
        super().addFailure(test, err)
        detail = "".join(traceback.format_exception(*err))
        self._entries.append((self._short_name(test), "FAIL", detail))

    def addError(self, test, err):
        super().addError(test, err)
        detail = "".join(traceback.format_exception(*err))
        self._entries.append((self._short_name(test), "ERROR", detail))

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self._entries.append((self._short_name(test), "SKIP", reason))

    def addExpectedFailure(self, test, err):
        super().addExpectedFailure(test, err)
        detail = "".join(traceback.format_exception(*err))
        self._entries.append((self._short_name(test), "PASS", detail))

    def addUnexpectedSuccess(self, test):
        super().addUnexpectedSuccess(test)
        self._entries.append((self._short_name(test), "ERROR",
                               "Test passed unexpectedly (marked xfail)."))


# ---------------------------------------------------------------------------
# Public runner
# ---------------------------------------------------------------------------

class SanityHtmlRunner(unittest.TextTestRunner):
    """Drop-in replacement for :class:`unittest.TextTestRunner` that also
    generates a professional HTML report in the framework's ``Test_Report``
    directory.

    Parameters
    ----------
    suite_name:
        Human-readable name shown in the HTML report header.
    report_dir:
        Override the output directory.  When *None* (default) the report is
        saved to ``<repo_root>/GM_VIP_Automation_Framework/Test_Report/<stamp>/``.
    mode:
        Connection mode label (``"MOCK"`` or ``"LIVE"``).  Shown in the
        report header for traceability.
    **kwargs:
        Forwarded to :class:`unittest.TextTestRunner` (e.g. ``verbosity``).
    """

    resultclass = _HtmlTestResult

    def __init__(
        self,
        suite_name: str = "GM_VIP_Sanity",
        report_dir: Optional[Path] = None,
        mode: str = "MOCK",
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._suite_name = suite_name
        self._report_dir = report_dir
        self._mode = mode

    def run(self, test) -> unittest.TestResult:
        result = super().run(test)
        self._save_report(result)
        return result

    def _save_report(self, result: _HtmlTestResult) -> None:
        generated_at = datetime.datetime.now().isoformat(timespec="seconds")
        out_dir = self._report_dir if self._report_dir is not None else make_report_dir()
        report_path = out_dir / "sanity_report.html"

        entries = getattr(result, "_entries", [])
        html = render_html(
            suite_name=self._suite_name,
            results=entries,
            generated_at=generated_at,
            mode=self._mode,
        )
        report_path.write_text(html, encoding="utf-8")
        print(f"\n[GM_VIP] HTML report saved → {report_path}", file=sys.stderr)
