"""
merge_reports.py  –  Consolidated HTML Report Generator for GM VIP Automation
==============================================================================
Merges all CANoe test-module XML reports and any Trace32 diagnostic XML
reports found under the GM_VIP_Automation tree into a single, easy-to-read
HTML file.

Report sources discovered automatically
----------------------------------------
1. CANoe per-module XML reports stored under  ``Test Reports/**/*.xml``
   (written by the test suite at the paths declared in the .tse files,
   e.g. Test Reports/Sanity/Sanity_report.xml).
2. Trace32 summary report at  ``Trace32/report.xml``  (optional – only
   included when the file exists).
3. Any additional  ``report.xml``  files found immediately inside the
   ``GM_VIP_RBS/`` folder (the "all-tests" roll-up written by GM_VIP_SWtest).

Usage
-----
    python merge_reports.py [--root <GM_VIP_Automation folder>]
                            [--out  <output HTML file>]

Exit codes
----------
    0  – merged report written without errors
    1  – one or more source XML files could not be parsed (details in output)

Supported CANoe XML report schemas
-----------------------------------
The script handles two common CANoe export formats:

  • ``testresults`` root element  (older format, direct ``<testcase>`` children)
  • ``testmodule``  root element  (newer format with ``<testgroup>``
    containers that hold ``<testcase>`` children)

T32 / Trace32 report format
-----------------------------
Any ``<testcase>`` or ``<step>`` elements found in Trace32 XML reports are
extracted and listed in a dedicated "Trace32 Diagnostics" section.  This
ensures T32 connection failures and breakpoint check results are always
visible in the consolidated view alongside the CANoe results.
"""

from __future__ import annotations

import argparse
import datetime
import html
import os
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class TestStep:
    name: str
    result: str          # "pass", "fail", "error", "unknown"
    description: str = ""


@dataclass
class TestCase:
    name: str
    result: str          # "pass", "fail", "error", "unknown"
    title: str = ""
    steps: List[TestStep] = field(default_factory=list)


@dataclass
class TestGroup:
    title: str
    cases: List[TestCase] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.cases)

    @property
    def passed(self) -> int:
        return sum(1 for c in self.cases if c.result == "pass")

    @property
    def failed(self) -> int:
        return sum(1 for c in self.cases if c.result in ("fail", "error"))

    @property
    def simulated(self) -> int:
        return sum(1 for c in self.cases if c.result == "simulated")


@dataclass
class ReportModule:
    source_file: Path
    title: str
    groups: List[TestGroup] = field(default_factory=list)
    is_t32: bool = False

    @property
    def total(self) -> int:
        return sum(g.total for g in self.groups)

    @property
    def passed(self) -> int:
        return sum(g.passed for g in self.groups)

    @property
    def failed(self) -> int:
        return sum(g.failed for g in self.groups)

    @property
    def simulated(self) -> int:
        return sum(g.simulated for g in self.groups)


# ---------------------------------------------------------------------------
# XML parsing helpers
# ---------------------------------------------------------------------------

def _normalise_result(raw: Optional[str]) -> str:
    """Map CANoe result strings to a canonical lower-case token."""
    if raw is None:
        return "unknown"
    lower = raw.strip().lower()
    if lower in ("pass", "passed", "ok", "success", "1", "true"):
        return "pass"
    if lower in ("fail", "failed", "error", "ng", "0", "false"):
        return "fail"
    if lower == "simulated":
        return "simulated"
    return lower or "unknown"


def _text(elem: ET.Element, *tags: str) -> str:
    """Return stripped text of the first matching sub-element, or ''."""
    for tag in tags:
        sub = elem.find(tag)
        if sub is not None and sub.text:
            return sub.text.strip()
    return ""


def _parse_canoe_testresults(root: ET.Element) -> List[TestGroup]:
    """Parse a ``<testresults>`` root (older CANoe XML schema)."""
    groups: List[TestGroup] = []
    default_group = TestGroup(title="Results")

    for tc_elem in root.iter("testcase"):
        name  = tc_elem.get("name", tc_elem.get("title", "unnamed"))
        title = tc_elem.get("title", name)
        res   = _normalise_result(tc_elem.get("verdict", tc_elem.get("result")))

        steps: List[TestStep] = []
        for step_elem in tc_elem.iter("step"):
            sname = step_elem.get("name", step_elem.get("title", ""))
            sres  = _normalise_result(step_elem.get("verdict", step_elem.get("result")))
            sdesc = _text(step_elem, "description", "desc")
            steps.append(TestStep(name=sname, result=sres, description=sdesc))

        default_group.cases.append(TestCase(name=name, title=title, result=res, steps=steps))

    if default_group.cases:
        groups.append(default_group)
    return groups


def _parse_canoe_testmodule(root: ET.Element) -> List[TestGroup]:
    """Parse a ``<testmodule>`` root (newer CANoe XML schema)."""
    groups: List[TestGroup] = []

    for tg_elem in root.iter("testgroup"):
        group = TestGroup(title=tg_elem.get("title", "Group"))
        for tc_elem in tg_elem.iter("testcase"):
            name  = tc_elem.get("name", tc_elem.get("title", "unnamed"))
            title = tc_elem.get("title", name)
            res   = _normalise_result(tc_elem.get("verdict", tc_elem.get("result")))

            steps: List[TestStep] = []
            for step_elem in tc_elem.iter("step"):
                sname = step_elem.get("name", step_elem.get("title", ""))
                sres  = _normalise_result(step_elem.get("verdict", step_elem.get("result")))
                sdesc = _text(step_elem, "description", "desc")
                steps.append(TestStep(name=sname, result=sres, description=sdesc))

            group.cases.append(TestCase(name=name, title=title, result=res, steps=steps))
        if group.cases:
            groups.append(group)

    # Also pick up top-level <testcase> elements not inside any group.
    top_level = TestGroup(title="(ungrouped)")
    for tc_elem in root.findall("testcase"):
        name  = tc_elem.get("name", tc_elem.get("title", "unnamed"))
        title = tc_elem.get("title", name)
        res   = _normalise_result(tc_elem.get("verdict", tc_elem.get("result")))
        top_level.cases.append(TestCase(name=name, title=title, result=res))
    if top_level.cases:
        groups.append(top_level)

    return groups


def _parse_t32_report(root: ET.Element) -> List[TestGroup]:
    """
    Parse a Trace32 report XML into a flat group of diagnostic steps.
    T32 XML does not have a fixed schema; we collect any <testcase> /
    <step> / <result> / <verdict> elements we can find.
    """
    group = TestGroup(title="T32 Diagnostics")

    for tc_elem in root.iter("testcase"):
        name = tc_elem.get("name", tc_elem.get("title", "T32 check"))
        res  = _normalise_result(tc_elem.get("verdict", tc_elem.get("result")))

        # Capture child steps so failure details are visible in the report.
        steps: List[TestStep] = []
        for step_elem in tc_elem.iter("step"):
            sname = step_elem.get("name", step_elem.get("title", ""))
            sres  = _normalise_result(step_elem.get("verdict", step_elem.get("result")))
            sdesc = _text(step_elem, "description", "desc")
            if not sdesc and step_elem.text:
                sdesc = step_elem.text.strip()
            steps.append(TestStep(name=sname, result=sres, description=sdesc))

        group.cases.append(TestCase(name=name, title=name, result=res, steps=steps))

    # If no testcase elements, fall back to step-level entries.
    if not group.cases:
        for step_elem in root.iter("step"):
            name = step_elem.get("name", step_elem.get("title", "T32 step"))
            res  = _normalise_result(step_elem.get("verdict", step_elem.get("result")))
            desc = _text(step_elem, "description", "desc")
            if not desc and step_elem.text:
                desc = step_elem.text.strip()
            group.cases.append(TestCase(name=name, title=name, result=res,
                                        steps=[TestStep(name=name, result=res,
                                                        description=desc)]))

    return [group] if group.cases else []


def parse_report_xml(filepath: Path, is_t32: bool = False) -> Optional[ReportModule]:
    """Parse one XML file into a ReportModule.  Returns None on error."""
    try:
        tree = ET.parse(filepath)
    except ET.ParseError as exc:
        print(f"  WARNING: could not parse {filepath}: {exc}", file=sys.stderr)
        return None

    root = tree.getroot()
    tag  = root.tag.lower()

    if is_t32:
        groups = _parse_t32_report(root)
        title  = root.get("title", "Trace32")
    elif tag == "testresults":
        groups = _parse_canoe_testresults(root)
        title  = root.get("title", filepath.stem)
    elif tag in ("testmodule", "testmoduleresults"):
        groups = _parse_canoe_testmodule(root)
        title  = root.get("title", filepath.stem)
    else:
        # Unknown schema – try both parsers and take whichever yields data.
        groups = _parse_canoe_testmodule(root) or _parse_canoe_testresults(root)
        title  = root.get("title", filepath.stem)

    return ReportModule(source_file=filepath, title=title or filepath.stem,
                        groups=groups, is_t32=is_t32)


# ---------------------------------------------------------------------------
# Report discovery
# ---------------------------------------------------------------------------

def discover_reports(root: Path, xml_dir: Optional[Path] = None) -> List[ReportModule]:
    """
    Discover all report XML files under *root* and return parsed modules.

    If *xml_dir* is provided, only the files directly inside that directory
    (non-recursive, top-level only) are scanned – useful for the
    simulated-report workflow where only ``Test Reports/simulation/*.xml``
    should be included (the ``junit/`` sub-directory is automatically
    excluded).

    Search order when *xml_dir* is None (determines display order in HTML):
      1. Test Reports/**/*.xml  (CANoe per-module reports)
      2. GM_VIP_RBS/report.xml  (all-tests roll-up)
      3. Trace32/report.xml     (T32 diagnostics, optional)
    """
    modules: List[ReportModule] = []
    seen: set = set()

    if xml_dir is not None:
        # Direct-directory mode: scan only the top level of the specified
        # folder (non-recursive) so that sub-directories such as junit/ are
        # not included.
        for xml_path in sorted(xml_dir.glob("*.xml")):
            if xml_path.resolve() in seen:
                continue
            seen.add(xml_path.resolve())
            mod = parse_report_xml(xml_path)
            if mod is not None:
                modules.append(mod)
        return modules

    # 1. CANoe per-module reports
    test_reports_dir = root / "Test Reports"
    if test_reports_dir.is_dir():
        for xml_path in sorted(test_reports_dir.rglob("*.xml")):
            if xml_path.resolve() in seen:
                continue
            seen.add(xml_path.resolve())
            mod = parse_report_xml(xml_path)
            if mod is not None:
                modules.append(mod)

    # 2. All-tests roll-up in GM_VIP_RBS/
    rbs_report = root / "GM_VIP_RBS" / "report.xml"
    if rbs_report.is_file() and rbs_report.resolve() not in seen:
        seen.add(rbs_report.resolve())
        mod = parse_report_xml(rbs_report)
        if mod is not None:
            mod.title = mod.title or "GM_VIP_SWtest (all)"
            modules.append(mod)

    # 3. Trace32 diagnostics
    t32_report = root / "Trace32" / "report.xml"
    if t32_report.is_file() and t32_report.resolve() not in seen:
        seen.add(t32_report.resolve())
        mod = parse_report_xml(t32_report, is_t32=True)
        if mod is not None:
            mod.title = "Trace32 Diagnostics"
            modules.append(mod)

    return modules


# ---------------------------------------------------------------------------
# HTML generation
# ---------------------------------------------------------------------------

_CSS = """
/* ===== Reset & Base ===================================================== */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

:root {
  --brand:        #003580;
  --brand-light:  #1a5cb5;
  --brand-bg:     #eef4ff;
  --pass:         #1a7d1a;
  --pass-bg:      #eaffea;
  --fail:         #b30000;
  --fail-bg:      #fff0f0;
  --sim:          #7a5200;
  --sim-bg:       #fff8e6;
  --sim-border:   #e6b800;
  --warn:         #856404;
  --unknown:      #6b7280;
  --t32:          #6d28d9;
  --t32-bg:       #f5f3ff;
  --text:         #1a1a2e;
  --muted:        #555;
  --border:       #d1d5db;
  --surface:      #ffffff;
  --surface-alt:  #f8fafc;
  --shadow:       0 2px 8px rgba(0,0,0,.10);
  --radius:       8px;
}

html { scroll-behavior: smooth; }
@media (prefers-reduced-motion: reduce) { html { scroll-behavior: auto; } }

body {
  font-family: 'Segoe UI', Arial, sans-serif;
  font-size: 0.875rem;
  line-height: 1.6;
  color: var(--text);
  background: #f0f4f8;
}

/* ===== Page Layout ====================================================== */
.page-wrapper {
  display: flex;
  min-height: 100vh;
}

/* ===== Sidebar ========================================================== */
.sidebar {
  width: 260px;
  min-width: 220px;
  background: var(--brand);
  color: #fff;
  padding: 24px 0;
  position: sticky;
  top: 0;
  height: 100vh;
  overflow-y: auto;
  flex-shrink: 0;
}
.sidebar-logo {
  padding: 0 20px 20px;
  border-bottom: 1px solid rgba(255,255,255,.2);
}
.sidebar-logo h1 {
  font-size: 1.05em;
  font-weight: 700;
  color: #fff;
  line-height: 1.3;
}
.sidebar-logo .tagline {
  font-size: .75em;
  opacity: .75;
  margin-top: 4px;
}
.sidebar nav { padding: 16px 0; }
.sidebar nav ul { list-style: none; }
.sidebar nav a {
  display: block;
  padding: 7px 20px;
  color: rgba(255,255,255,.85);
  text-decoration: none;
  font-size: .85em;
  border-left: 3px solid transparent;
  transition: background .15s, border-color .15s;
}
.sidebar nav a:hover,
.sidebar nav a.active {
  background: rgba(255,255,255,.12);
  border-left-color: #7eb8ff;
  color: #fff;
}
.sidebar nav a .status-icon { margin-right: 6px; }
.sidebar-footer {
  padding: 16px 20px 0;
  border-top: 1px solid rgba(255,255,255,.2);
  font-size: .72em;
  opacity: .65;
}

/* ===== Main Content ===================================================== */
.main-content {
  flex: 1;
  padding: 28px 32px;
  max-width: 1100px;
  overflow-x: hidden;
}

/* ===== Page Header ====================================================== */
.page-header {
  margin-bottom: 24px;
  padding-bottom: 16px;
  border-bottom: 2px solid var(--brand);
}
.page-header h1 {
  font-size: 1.7em;
  font-weight: 700;
  color: var(--brand);
}
.page-header .meta {
  color: var(--muted);
  font-size: .85em;
  margin-top: 4px;
}

/* ===== Simulated Banner ================================================= */
.sim-banner {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  background: var(--sim-bg);
  border: 2px solid var(--sim-border);
  border-radius: var(--radius);
  padding: 16px 20px;
  margin-bottom: 24px;
  color: var(--sim);
}
.sim-banner .sim-icon {
  font-size: 2em;
  line-height: 1;
  flex-shrink: 0;
}
.sim-banner .sim-text { flex: 1; }
.sim-banner .sim-title {
  font-size: 1.05em;
  font-weight: 700;
  margin-bottom: 4px;
  text-transform: uppercase;
  letter-spacing: .05em;
}
.sim-banner .sim-desc { font-size: .88em; }

/* ===== Summary Cards ==================================================== */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 16px;
  margin-bottom: 28px;
}
.stat-card {
  background: var(--surface);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  padding: 18px 20px;
  text-align: center;
  border-top: 4px solid var(--border);
}
.stat-card.pass-card  { border-top-color: var(--pass); }
.stat-card.fail-card  { border-top-color: var(--fail); }
.stat-card.sim-card   { border-top-color: var(--sim-border); }
.stat-card.total-card { border-top-color: var(--brand); }
.stat-card.overall-card.ok  { border-top-color: var(--pass); }
.stat-card.overall-card.bad { border-top-color: var(--fail); }
.stat-card.overall-card.sim { border-top-color: var(--sim-border); }
.stat-card .stat-value {
  font-size: 2.2em;
  font-weight: 700;
  line-height: 1;
  margin-bottom: 6px;
}
.stat-card .stat-label {
  font-size: .78em;
  text-transform: uppercase;
  letter-spacing: .06em;
  color: var(--muted);
}
.stat-card.pass-card  .stat-value { color: var(--pass); }
.stat-card.fail-card  .stat-value { color: var(--fail); }
.stat-card.sim-card   .stat-value { color: var(--warn); }
.stat-card.total-card .stat-value { color: var(--brand); }
.stat-card.overall-card.ok  .stat-value { color: var(--pass); }
.stat-card.overall-card.bad .stat-value { color: var(--fail); }
.stat-card.overall-card.sim .stat-value { color: var(--warn); }

/* ===== Progress Bar ===================================================== */
.progress-section {
  background: var(--surface);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  padding: 18px 22px;
  margin-bottom: 28px;
}
.progress-section .progress-label {
  font-size: .82em;
  font-weight: 600;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: .05em;
  margin-bottom: 8px;
}
.progress-bar {
  height: 18px;
  border-radius: 9px;
  overflow: hidden;
  background: #e5e7eb;
  display: flex;
}
.progress-bar .seg-pass { background: var(--pass); }
.progress-bar .seg-fail { background: var(--fail); }
.progress-bar .seg-sim  { background: var(--sim-border); }
.progress-bar .seg-unk  { background: #9ca3af; }
.progress-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  margin-top: 10px;
  font-size: .8em;
  color: var(--muted);
}
.progress-legend .leg {
  display: flex;
  align-items: center;
  gap: 5px;
}
.progress-legend .dot {
  width: 10px; height: 10px;
  border-radius: 50%;
  display: inline-block;
}
.dot-pass { background: var(--pass); }
.dot-fail { background: var(--fail); }
.dot-sim  { background: var(--sim-border); }

/* ===== Module Cards ===================================================== */
.module-card {
  background: var(--surface);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  margin-bottom: 24px;
  overflow: hidden;
}
.module-card.t32-card { border-left: 4px solid var(--t32); }
.module-card.sim-card { border-left: 4px solid var(--sim-border); }

.module-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 20px;
  background: var(--brand-bg);
  border-bottom: 1px solid var(--border);
  cursor: pointer;
  user-select: none;
}
.module-card.t32-card .module-card-header { background: var(--t32-bg); }
.module-card.sim-card .module-card-header { background: var(--sim-bg); }
.module-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.module-title {
  font-size: 1.02em;
  font-weight: 700;
  color: var(--brand);
}
.module-card.t32-card .module-title { color: var(--t32); }
.module-badges {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  align-items: center;
}
.badge {
  display: inline-block;
  padding: 2px 9px;
  border-radius: 12px;
  font-size: .75em;
  font-weight: 600;
  letter-spacing: .03em;
}
.badge-pass { background: var(--pass-bg); color: var(--pass); }
.badge-fail { background: var(--fail-bg); color: var(--fail); }
.badge-sim  { background: var(--sim-bg);  color: var(--warn); border: 1px solid var(--sim-border); }
.badge-t32  { background: var(--t32-bg);  color: var(--t32); }
.toggle-icon {
  font-size: .85em;
  color: var(--muted);
  transition: transform .2s;
}
.module-card.collapsed .toggle-icon { transform: rotate(-90deg); }

.module-card-body { padding: 0 20px 16px; }
.module-meta {
  font-size: .78em;
  color: var(--muted);
  padding: 10px 0 12px;
  word-break: break-all;
}

/* ===== Test Group ======================================================= */
.group-title {
  font-size: .88em;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: .06em;
  color: var(--muted);
  padding: 10px 0 6px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 2px;
}

/* ===== Test Case Table ================================================== */
table {
  border-collapse: collapse;
  width: 100%;
  margin-bottom: 16px;
  font-size: .86em;
}
th {
  background: var(--brand);
  color: #fff;
  padding: 8px 12px;
  text-align: left;
  font-weight: 600;
  font-size: .82em;
  letter-spacing: .04em;
  text-transform: uppercase;
}
td {
  padding: 7px 12px;
  border-bottom: 1px solid #eef0f3;
  vertical-align: top;
}
tr:nth-child(even) td { background: var(--surface-alt); }
tr:hover td           { background: #e8effe; }

.tc-name { font-family: 'Consolas', 'Courier New', monospace; font-size: .92em; }
.tc-title { color: var(--muted); font-size: .88em; }

.result-badge {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 10px;
  font-size: .78em;
  font-weight: 700;
  letter-spacing: .05em;
  text-transform: uppercase;
  white-space: nowrap;
}
.rb-pass      { background: var(--pass-bg); color: var(--pass); }
.rb-fail      { background: var(--fail-bg); color: var(--fail); }
.rb-error     { background: var(--fail-bg); color: var(--fail); }
.rb-simulated { background: var(--sim-bg);  color: var(--warn); border: 1px solid var(--sim-border); }
.rb-unknown   { background: #f3f4f6;        color: var(--unknown); }

/* ===== Step Detail Rows ================================================= */
.step-row td {
  background: var(--fail-bg) !important;
  font-size: .82em;
  color: var(--fail);
}
.step-row .step-name { font-weight: 600; }
.step-row .step-desc { color: #6b1a1a; margin-left: 4px; }

/* ===== T32 Section ====================================================== */
.t32-note {
  font-size: .78em;
  color: var(--t32);
  background: var(--t32-bg);
  border-left: 3px solid var(--t32);
  padding: 6px 12px;
  border-radius: 0 4px 4px 0;
  margin-bottom: 10px;
}

/* ===== Footer =========================================================== */
.page-footer {
  margin-top: 40px;
  padding-top: 16px;
  border-top: 1px solid var(--border);
  font-size: .75em;
  color: var(--muted);
  text-align: center;
}

/* ===== Print ============================================================ */
@media print {
  .sidebar     { display: none; }
  .main-content { padding: 12px; max-width: 100%; }
  .module-card { box-shadow: none; border: 1px solid var(--border); break-inside: avoid; }
  .module-card-header { cursor: default; }
  .module-card.collapsed .module-card-body { display: block !important; }
  body { background: #fff; }
}

/* ===== Responsive ======================================================= */
@media (max-width: 700px) {
  .page-wrapper { flex-direction: column; }
  .sidebar { width: 100%; height: auto; position: relative; }
  .stats-grid { grid-template-columns: repeat(2, 1fr); }
}
"""

_JS = """
document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('.module-card-header').forEach(function (hdr) {
    function toggle() {
      var card = hdr.closest('.module-card');
      var body = card.querySelector('.module-card-body');
      var collapsed = card.classList.toggle('collapsed');
      body.style.display = collapsed ? 'none' : '';
      hdr.setAttribute('aria-expanded', String(!collapsed));
    }
    hdr.addEventListener('click', toggle);
    hdr.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        toggle();
      }
    });
  });
});
"""

_RESULT_CLASS = {
    "pass":      "pass",
    "fail":      "fail",
    "error":     "error",
    "unknown":   "unknown",
    "simulated": "simulated",
}


def _result_badge(result: str) -> str:
    """Return a styled HTML badge span for the given result string."""
    css = f"rb-{_RESULT_CLASS.get(result, 'unknown')}"
    return f'<span class="result-badge {css}">{html.escape(result.upper())}</span>'


# Keep legacy name used by callers that may exist outside this file.
def _result_cell(result: str) -> str:
    return _result_badge(result)


def _progress_bar_html(passed: int, failed: int, simulated: int, total: int) -> str:
    """Return an HTML progress bar segment string."""
    if total == 0:
        return '<div class="progress-bar"><div class="seg-unk" style="width:100%"></div></div>'

    def pct(n: int) -> str:
        return f"{n * 100 / total:.1f}%"

    segs = []
    if passed:
        segs.append(f'<div class="seg-pass" style="width:{pct(passed)}" title="{passed} passed"></div>')
    if simulated:
        segs.append(f'<div class="seg-sim" style="width:{pct(simulated)}" title="{simulated} simulated"></div>')
    if failed:
        segs.append(f'<div class="seg-fail" style="width:{pct(failed)}" title="{failed} failed/error"></div>')
    rest = total - passed - simulated - failed
    if rest > 0:
        segs.append(f'<div class="seg-unk" style="width:{pct(rest)}" title="{rest} unknown"></div>')

    return f'<div class="progress-bar">{"".join(segs)}</div>'


def generate_html(modules: List[ReportModule], generated_at: datetime.datetime,
                  simulated: bool = False) -> str:
    grand_total     = sum(m.total     for m in modules)
    grand_passed    = sum(m.passed    for m in modules)
    grand_failed    = sum(m.failed    for m in modules)
    grand_simulated = sum(m.simulated for m in modules)

    # Determine overall verdict
    if simulated and grand_simulated > 0 and grand_failed == 0:
        overall_key  = "sim"
        overall_text = f"{grand_simulated} SIMULATED"
        overall_sub  = "Syntax validated — no hardware executed"
    elif grand_failed == 0:
        overall_key  = "ok"
        overall_text = "ALL PASSED"
        overall_sub  = f"{grand_passed} test(s) passed"
    else:
        overall_key  = "bad"
        overall_text = f"{grand_failed} FAILURE(S)"
        overall_sub  = f"{grand_passed} passed, {grand_failed} failed"

    ts = html.escape(generated_at.strftime("%Y-%m-%d %H:%M:%S"))

    L: List[str] = []

    # ------------------------------------------------------------------ HEAD
    L.append("<!DOCTYPE html>")
    L.append("<html lang='en'>")
    L.append("<head>")
    L.append('<meta charset="UTF-8">')
    L.append('<meta name="viewport" content="width=device-width, initial-scale=1.0">')
    L.append("<title>GM VIP Automation \u2013 Test Report</title>")
    L.append(f"<style>{_CSS}</style>")
    L.append("</head>")
    L.append("<body>")
    L.append('<div class="page-wrapper">')

    # --------------------------------------------------------------- SIDEBAR
    L.append('<nav class="sidebar" aria-label="Module navigation">')
    L.append('<div class="sidebar-logo">')
    L.append('<h1>GM VIP Automation</h1>')
    report_kind = "Simulation Report" if simulated else "Consolidated Test Report"
    L.append(f'<div class="tagline">{html.escape(report_kind)}</div>')
    L.append('</div>')
    L.append('<nav>')
    L.append('<ul>')
    L.append('<li><a href="#summary">&#x1F4CA; Summary</a></li>')
    for idx, mod in enumerate(modules):
        anchor = f"mod-{idx}"
        if mod.failed > 0:
            icon = "&#x274C;"
        elif mod.simulated > 0 and mod.passed == 0:
            icon = "&#x1F52C;"
        elif mod.total > 0:
            icon = "&#x2705;"
        else:
            icon = "&ndash;"
        L.append(
            f'<li><a href="#{anchor}">'
            f'<span class="status-icon">{icon}</span>'
            f'{html.escape(mod.title)}</a></li>'
        )
    L.append('</ul>')
    L.append('</nav>')
    L.append(f'<div class="sidebar-footer">Generated {ts}</div>')
    L.append('</nav>')

    # ----------------------------------------------------------- MAIN CONTENT
    L.append('<main class="main-content">')

    # Page header
    L.append('<div class="page-header">')
    L.append('<h1>GM VIP Automation \u2013 Test Report</h1>')
    L.append(f'<div class="meta">Generated: {ts} &nbsp;|&nbsp; '
             f'{len(modules)} module(s) scanned</div>')
    L.append('</div>')

    # Simulated banner
    if simulated:
        L.append('<div class="sim-banner" role="status">')
        L.append('<div class="sim-icon">&#9888;</div>')
        L.append('<div class="sim-text">')
        L.append('<div class="sim-title">Simulated Report &mdash; No Hardware Executed</div>')
        L.append(
            '<div class="sim-desc">This report was generated by static analysis of '
            'CAPL test-case definitions. Each test&nbsp;case has been verified to '
            'exist in a <code>.can</code> source file but <strong>has not been '
            'executed on physical hardware</strong>. Verdicts shown as '
            '<em>SIMULATED</em> require a real ECU bench run for actual '
            'pass/fail results. Entries shown as <em>ERROR</em> indicate '
            'missing definitions that must be resolved before bench execution.</div>'
        )
        L.append('</div>')
        L.append('</div>')

    # ---------------------------------------------------- Summary anchor
    L.append('<a id="summary"></a>')

    # Stat cards
    L.append('<div class="stats-grid">')
    L.append(
        f'<div class="stat-card total-card">'
        f'<div class="stat-value">{grand_total}</div>'
        f'<div class="stat-label">Total Tests</div></div>'
    )
    L.append(
        f'<div class="stat-card pass-card">'
        f'<div class="stat-value">{grand_passed}</div>'
        f'<div class="stat-label">Passed</div></div>'
    )
    L.append(
        f'<div class="stat-card fail-card">'
        f'<div class="stat-value">{grand_failed}</div>'
        f'<div class="stat-label">Failed / Error</div></div>'
    )
    if grand_simulated > 0 or simulated:
        L.append(
            f'<div class="stat-card sim-card">'
            f'<div class="stat-value">{grand_simulated}</div>'
            f'<div class="stat-label">Simulated</div></div>'
        )
    L.append(
        f'<div class="stat-card overall-card {overall_key}">'
        f'<div class="stat-value" style="font-size:1.15em">{html.escape(overall_text)}</div>'
        f'<div class="stat-label">{html.escape(overall_sub)}</div></div>'
    )
    L.append('</div>')  # stats-grid

    # Progress bar
    if grand_total > 0:
        L.append('<div class="progress-section">')
        L.append('<div class="progress-label">Test result distribution</div>')
        L.append(_progress_bar_html(grand_passed, grand_failed, grand_simulated, grand_total))
        L.append('<div class="progress-legend">')
        if grand_passed:
            L.append(f'<span class="leg"><span class="dot dot-pass"></span>'
                     f'{grand_passed} passed</span>')
        if grand_simulated:
            L.append(f'<span class="leg"><span class="dot dot-sim"></span>'
                     f'{grand_simulated} simulated</span>')
        if grand_failed:
            L.append(f'<span class="leg"><span class="dot dot-fail"></span>'
                     f'{grand_failed} failed/error</span>')
        L.append('</div>')  # legend
        L.append('</div>')  # progress-section

    if not modules:
        L.append("<p><em>No test reports found. Run the test suites first.</em></p>")
        L.append('</main></div>')
        L.append("</body></html>")
        return "\n".join(L)

    # -------------------------------------------------- Per-module cards
    for idx, mod in enumerate(modules):
        anchor = f"mod-{idx}"

        # Card class
        card_cls = "module-card"
        if mod.is_t32:
            card_cls += " t32-card"
        elif mod.simulated > 0 and mod.passed == 0:
            card_cls += " sim-card"

        L.append(f'<div class="{card_cls}" id="{anchor}">')

        # Card header (clickable toggle)
        L.append('<div class="module-card-header" role="button" '
                 'aria-expanded="true" tabindex="0">')
        L.append('<div class="module-title-row">')

        if mod.failed > 0:
            hdr_icon = "&#x274C;"
        elif mod.simulated > 0 and mod.passed == 0:
            hdr_icon = "&#x1F52C;"
        elif mod.total > 0:
            hdr_icon = "&#x2705;"
        else:
            hdr_icon = "&ndash;"

        L.append(f'<span>{hdr_icon}</span>')
        L.append(f'<span class="module-title">{html.escape(mod.title)}</span>')
        L.append('</div>')  # module-title-row

        # Badges
        L.append('<div class="module-badges">')
        if mod.is_t32:
            L.append('<span class="badge badge-t32">T32</span>')
        if mod.passed > 0:
            L.append(f'<span class="badge badge-pass">{mod.passed} passed</span>')
        if mod.failed > 0:
            L.append(f'<span class="badge badge-fail">{mod.failed} failed</span>')
        if mod.simulated > 0:
            L.append(f'<span class="badge badge-sim">{mod.simulated} simulated</span>')
        L.append(f'<span style="font-size:.8em;color:var(--muted)">'
                 f'{mod.passed}/{mod.total}</span>')
        L.append('<span class="toggle-icon">&#x25BE;</span>')
        L.append('</div>')  # module-badges

        L.append('</div>')  # module-card-header

        # Card body
        L.append('<div class="module-card-body">')
        L.append(f'<div class="module-meta">Source: '
                 f'<code>{html.escape(str(mod.source_file))}</code></div>')

        if mod.is_t32:
            L.append('<div class="t32-note">&#x1F50C; Trace32 diagnostic results '
                     '&ndash; hardware connection and breakpoint checks</div>')

        if not mod.groups:
            L.append("<p><em>No test-case data found in this report.</em></p>")
        else:
            for group in mod.groups:
                L.append(f'<div class="group-title">{html.escape(group.title)}</div>')
                L.append("<table>")
                L.append(
                    "<tr>"
                    "<th style='width:55%'>Test Case</th>"
                    "<th style='width:25%'>Function Name</th>"
                    "<th style='width:20%'>Result</th>"
                    "</tr>"
                )
                for case in group.cases:
                    title_str = html.escape(case.title or case.name)
                    name_str  = html.escape(case.name)
                    L.append(
                        f"<tr>"
                        f"<td class='tc-title'>{title_str}</td>"
                        f"<td class='tc-name'>{name_str}</td>"
                        f"<td>{_result_badge(case.result)}</td>"
                        f"</tr>"
                    )

                    # Expand failing / errored steps inline
                    for step in case.steps:
                        if step.result in ("fail", "error"):
                            sname = html.escape(step.name)
                            sdesc = html.escape(step.description or step.name)
                            L.append(
                                f'<tr class="step-row">'
                                f'<td colspan="2">'
                                f'&nbsp;&nbsp;&#x21B3;&nbsp;'
                                f'<span class="step-name">{sname}</span>'
                                f'<span class="step-desc">{sdesc}</span>'
                                f'</td>'
                                f'<td>{_result_badge(step.result)}</td>'
                                f'</tr>'
                            )
                L.append("</table>")

        L.append('</div>')  # module-card-body
        L.append('</div>')  # module-card

    # Footer
    L.append(
        f'<div class="page-footer">'
        f'GM VIP Automation &mdash; {html.escape(report_kind)} &mdash; '
        f'Generated {ts}'
        f'</div>'
    )
    L.append('</main>')
    L.append('</div>')  # page-wrapper

    L.append(f'<script>{_JS}</script>')
    L.append("</body></html>")
    return "\n".join(L)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Merge CANoe and Trace32 test reports into one HTML file."
    )
    parser.add_argument(
        "--root", "-r",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="Root directory of GM_VIP_Automation (default: same folder as this script)",
    )
    parser.add_argument(
        "--out", "-o",
        type=Path,
        default=None,
        help=(
            "Output HTML file path. "
            "Default: <root>/Test Reports/consolidated_report.html"
        ),
    )
    parser.add_argument(
        "--simulated",
        action="store_true",
        default=False,
        help=(
            "Mark the report as a simulation run. "
            "Adds a prominent SIMULATED banner and adjusts the summary to "
            "show simulated counts instead of pass/fail. "
            "Use together with --xml-dir to scope the report to simulation XMLs only."
        ),
    )
    parser.add_argument(
        "--xml-dir",
        type=Path,
        default=None,
        help=(
            "Scan only this directory (recursively) for XML report files "
            "instead of the normal discovery logic under <root>/Test Reports. "
            "Useful for generating a simulation-only report from "
            "'Test Reports/simulation/'."
        ),
    )
    args = parser.parse_args()
    root: Path = args.root.resolve()

    if not root.is_dir():
        print(f"ERROR: root directory not found: {root}", file=sys.stderr)
        return 1

    xml_dir: Optional[Path] = args.xml_dir.resolve() if args.xml_dir else None

    out_path: Path = args.out or (root / "Test Reports" / "consolidated_report.html")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    scan_label = str(xml_dir) if xml_dir else str(root)
    print(f"Scanning for reports under: {scan_label}")
    modules = discover_reports(root, xml_dir=xml_dir)

    if not modules:
        print("  No report XML files found. Run the test suites first.", file=sys.stderr)

    for mod in modules:
        sim_tag = " [SIM]" if mod.simulated > 0 and mod.passed == 0 else ""
        status  = "OK" if mod.failed == 0 else "FAIL"
        t32_tag = " [T32]" if mod.is_t32 else ""
        try:
            rel = mod.source_file.relative_to(root)
        except ValueError:
            rel = mod.source_file
        print(f"  [{status}]{t32_tag}{sim_tag} {rel}"
              f"  –  {mod.passed}/{mod.total} passed")

    html_content = generate_html(modules, datetime.datetime.now(),
                                 simulated=args.simulated)

    try:
        out_path.write_text(html_content, encoding="utf-8")
    except OSError as exc:
        print(f"ERROR: could not write {out_path}: {exc}", file=sys.stderr)
        return 1

    print(f"\nConsolidated report written to: {out_path}")

    total_failed = sum(m.failed for m in modules)
    return 1 if total_failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
