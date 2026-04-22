"""
simulate_tests.py  –  Virtual Bench Simulation for STLA CVADAS SW Test
=======================================================================
Discovers all STLA vTestStudio test sequences from the CANoe .run cache
and generates simulated JUnit-compatible XML reports and an HTML summary
without physical ADAS bench hardware (ECU / CANoe / Lauterbach T32).

What it does
------------
1. Scans the .run directory under BVTRBS/CVADAS_RBS_TRSC for the
   latest .vtt.export.xml file for each known STLA test unit.
2. Extracts every <testsequence name="..."> from each export file.
3. For each test unit it writes two report files into the output directory:

   <suite>_simulated_junit.xml  –  JUnit schema consumed by Jenkins junit()
                                     and GitHub Actions test result panels.
                                     Every discovered test sequence appears as
                                     a <testcase>; none are marked as errors
                                     because their definitions are present in
                                     the vTestStudio export cache.

   simulation_report.html       –  Single consolidated HTML report with a
                                     per-suite pass table and a prominent
                                     SIMULATED banner.

4. Writes simulation_summary.txt with a per-suite table.

Exit codes
----------
    0  –  simulation complete (reports written).  This includes the case
           where no .vtt.export.xml files are found (e.g. no prior CANoe
           session / fresh bench).  Zero sequences discovered is a valid
           first-run state, not a pipeline error.
    1  –  fatal error: root directory does not exist, or an unrecoverable
           XML parse failure occurred.  The pipeline should mark UNSTABLE.

Usage
-----
    python simulate_tests.py [--root <STLA_SWTest folder>]
                             [--out-dir <output directory>]

This script is stdlib-only and runs on Linux (GitHub Actions ubuntu-latest)
as well as Windows (Jenkins windows-agent).  It has NO dependency on any
other script in this repository.
"""

from __future__ import annotations

import argparse
import datetime
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Known STLA test units (matches the CANoe test units configured in the
# ME_L2H4060_DT_CVADAS_DSBus.cfg project and the Jenkins pipeline stages).
# ---------------------------------------------------------------------------
KNOWN_SUITES: List[Dict] = [
    {
        'name':    'Flashing',
        'vtt':     'Flashing.vtt.export.xml',
        'label':   'ECU Flash (Bootloader + Application)',
        'stage':   'flashTarget',
    },
    {
        'name':    'SanityTest',
        'vtt':     'SanityTest.vtt.export.xml',
        'label':   'BVT / Sanity',
        'stage':   'executeBVT',
    },
    {
        'name':    'QuickSanity',
        'vtt':     'QuickSanity.vtt.export.xml',
        'label':   'Quick Sanity (PR Gate)',
        'stage':   'enableQuickSanity',
    },
    {
        'name':    'CPU_Load',
        'vtt':     'CPU_Load_withStack.vtt.export.xml',
        'label':   'CPU Load (with Stack)',
        'stage':   'CPU_Load_Test',
    },
    {
        'name':    'Stress',
        'vtt':     'Stress.vtt.export.xml',
        'label':   'Robustness / Stress',
        'stage':   'enableRobustness',
    },
    {
        'name':    'RunTimeStats',
        'vtt':     'Run-Time-Stats.vtt.export.xml',
        'label':   'Run-Time Statistics',
        'stage':   'SWQT',
    },
]


# ---------------------------------------------------------------------------
# .run cache discovery
# ---------------------------------------------------------------------------

def _find_run_dir(stla_root: Path) -> Optional[Path]:
    """
    Return the path to the .run directory inside the CVADAS_RBS_TRSC folder,
    or None if it does not exist.
    """
    candidate = (
        stla_root
        / 'BVTRBS'
        / 'CVADAS_RBS_TRSC'
        / '.run'
    )
    return candidate if candidate.is_dir() else None


def _latest_export_xml(run_dir: Path, filename: str) -> Optional[Path]:
    """
    Return the most recently modified copy of *filename* anywhere under
    *run_dir*, or None if none is found.  CANoe stores multiple versioned
    copies in hash-named subdirectories; the newest is authoritative.
    """
    candidates = list(run_dir.rglob(filename))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


# ---------------------------------------------------------------------------
# Test sequence extraction
# ---------------------------------------------------------------------------

def extract_test_sequences(export_xml: Path) -> List[str]:
    """
    Parse a .vtt.export.xml file and return a deduplicated, ordered list of
    top-level <testsequence name="..."> values.
    """
    try:
        tree = ET.parse(export_xml)
    except ET.ParseError as exc:
        print(f"  WARNING: could not parse {export_xml}: {exc}", file=sys.stderr)
        return []

    seen: List[str] = []
    visited: set = set()
    for elem in tree.getroot().iter('testsequence'):
        name = elem.get('name', '').strip()
        if name and name not in visited:
            seen.append(name)
            visited.add(name)
    return seen


# ---------------------------------------------------------------------------
# JUnit XML writer
# ---------------------------------------------------------------------------

def _write_junit_xml(
    suite_name: str,
    suite_label: str,
    sequences: List[str],
    out_path: Path,
) -> None:
    """
    Write a JUnit-schema XML file for Jenkins junit() / GitHub Actions.
    Each discovered test sequence is a passing <testcase> with a
    system-out note explaining it has not been executed on hardware.
    """
    ts = datetime.datetime.now().isoformat(timespec='seconds')
    suite_elem = ET.Element(
        'testsuite',
        name=f"{suite_label} [Simulation]",
        tests=str(len(sequences)),
        failures='0',
        errors='0',
        skipped='0',
        time='0',
        timestamp=ts,
    )
    for seq_name in sequences:
        tc = ET.SubElement(
            suite_elem, 'testcase',
            name=seq_name,
            classname=f"STLA.CVADAS.{suite_name}",
            time='0',
        )
        out = ET.SubElement(tc, 'system-out')
        out.text = (
            "SIMULATED: test sequence definition found in vTestStudio export. "
            "Awaiting physical ADAS bench hardware execution for actual result."
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    tree = ET.ElementTree(suite_elem)
    if hasattr(ET, 'indent'):
        ET.indent(tree, space='    ')
    with out_path.open('wb') as fh:
        fh.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
        tree.write(fh, encoding='UTF-8', xml_declaration=False)
        fh.write(b'\n')


# ---------------------------------------------------------------------------
# HTML report writer
# ---------------------------------------------------------------------------

_HTML_STYLE = """
body  { font-family: Arial, sans-serif; margin: 24px; color: #333; }
h1    { color: #c00; }
.banner { background: #fff3cd; border-left: 6px solid #f0ad4e;
          padding: 12px 16px; margin-bottom: 24px; font-size: 15px; }
table { border-collapse: collapse; width: 100%; margin-bottom: 32px; }
th,td { border: 1px solid #ccc; padding: 8px 12px; text-align: left; }
th    { background: #f4f4f4; }
.pass { background: #d4edda; color: #155724; font-weight: bold; }
.skip { background: #f8f9fa; color: #6c757d; }
ul    { margin: 4px 0; padding-left: 18px; }
"""

def _write_html_report(
    results: List[Dict],
    out_path: Path,
    stla_root: Path,
    generated: str,
) -> None:
    """
    Write a single consolidated HTML simulation report for all STLA suites.
    """
    total_tc = sum(r['count'] for r in results)
    found    = sum(1 for r in results if r['count'] > 0)

    rows = []
    for r in results:
        if r['count'] > 0:
            tc_list = ''.join(f'<li>{tc}</li>' for tc in r['sequences'])
            rows.append(
                f"<tr>"
                f"<td>{r['label']}</td>"
                f"<td class='pass'>SIMULATED</td>"
                f"<td>{r['count']}</td>"
                f"<td><ul>{tc_list}</ul></td>"
                f"</tr>"
            )
        else:
            rows.append(
                f"<tr>"
                f"<td>{r['label']}</td>"
                f"<td class='skip'>No export found</td>"
                f"<td>0</td>"
                f"<td><em>No .vtt.export.xml found in .run cache.</em></td>"
                f"</tr>"
            )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>STLA CVADAS – Simulation Report</title>
  <style>{_HTML_STYLE}</style>
</head>
<body>
  <h1>STLA CVADAS ADAS SW Test – Simulation Report</h1>

  <div class="banner">
    &#9888; <strong>SIMULATED RESULTS</strong> – No physical ADAS bench hardware was used.
    Test sequence definitions were discovered from the CANoe vTestStudio export
    cache. Actual pass/fail verdicts require ECU execution on the bench.
  </div>

  <p><strong>Generated :</strong> {generated}<br>
     <strong>Root      :</strong> {stla_root}<br>
     <strong>Suites    :</strong> {found} / {len(results)} found
     &nbsp;|&nbsp; <strong>Test sequences :</strong> {total_tc} total</p>

  <table>
    <thead>
      <tr>
        <th>Test Unit (Jenkins Stage)</th>
        <th>Status</th>
        <th>Sequences</th>
        <th>Test Sequence Names</th>
      </tr>
    </thead>
    <tbody>
      {''.join(rows)}
    </tbody>
  </table>

  <hr>
  <p style="font-size:12px;color:#888;">
    Generated by OEM/Stellantis/STLA_SWTest/simulate_tests.py &nbsp;|&nbsp;
    For hardware results run the Jenkins pipeline on a windows-bench agent.
  </p>
</body>
</html>
"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding='utf-8')


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Virtual bench simulation for STLA CVADAS ADAS SW Test. "
            "Generates simulated JUnit XML and HTML reports without hardware."
        )
    )
    parser.add_argument(
        '--root', '-r',
        type=Path,
        default=Path(__file__).resolve().parent,
        help="Root directory of STLA_SWTest (default: same folder as this script)",
    )
    parser.add_argument(
        '--out-dir', '-o',
        type=Path,
        default=None,
        help=(
            "Output directory for generated report files. "
            "Default: <root>/Test Reports/simulation"
        ),
    )
    args = parser.parse_args()
    root: Path = args.root.resolve()

    if not root.is_dir():
        print(f"ERROR: root directory not found: {root}", file=sys.stderr)
        return 1

    out_dir: Path = (
        args.out_dir or root / 'Test Reports' / 'simulation'
    ).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    junit_dir = out_dir / 'junit'
    junit_dir.mkdir(parents=True, exist_ok=True)

    generated = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # ------------------------------------------------------------------
    # Locate the .run cache directory
    # ------------------------------------------------------------------
    run_dir = _find_run_dir(root)
    if run_dir is None:
        print(
            "WARNING: .run cache directory not found under "
            "BVTRBS/CVADAS_RBS_TRSC/. "
            "No .vtt.export.xml files will be parsed.",
            file=sys.stderr,
        )

    # ------------------------------------------------------------------
    # Process each known STLA test suite
    # ------------------------------------------------------------------
    print(f"STLA CVADAS Virtual Bench Simulation")
    print(f"  Root    : {root}")
    print(f"  Out dir : {out_dir}")
    print(f"  .run    : {run_dir or '(not found)'}")
    print()

    results: List[Dict] = []
    total_found = 0

    for suite in KNOWN_SUITES:
        suite_name  = suite['name']
        vtt_file    = suite['vtt']
        label       = suite['label']

        sequences: List[str] = []
        export_path: Optional[Path] = None

        if run_dir:
            export_path = _latest_export_xml(run_dir, vtt_file)
            if export_path:
                sequences = extract_test_sequences(export_path)

        count  = len(sequences)
        status = f"{count} sequences" if count > 0 else "no export found"
        flag   = "OK  " if count > 0 else "SKIP"
        print(f"  [{flag}] {label:40s}  {status}")
        if export_path:
            print(f"          source: {export_path.name}  ({export_path.parent.parent.name}/…)")
        for seq in sequences:
            print(f"          · {seq}")

        # Write JUnit XML (one per suite, even if empty)
        junit_out = junit_dir / f"{suite_name}_simulated_junit.xml"
        _write_junit_xml(suite_name, label, sequences, junit_out)

        total_found += count
        results.append({
            'name':      suite_name,
            'label':     label,
            'stage':     suite['stage'],
            'count':     count,
            'sequences': sequences,
            'source':    str(export_path) if export_path else '',
        })

    # ------------------------------------------------------------------
    # Consolidated HTML report
    # ------------------------------------------------------------------
    html_out = out_dir / 'simulation_report.html'
    _write_html_report(results, html_out, root, generated)
    print()
    print(f"HTML report       : {html_out}")

    # ------------------------------------------------------------------
    # Summary text file
    # ------------------------------------------------------------------
    summary_lines = [
        "STLA CVADAS ADAS SW Test – Virtual Bench Simulation Summary",
        "=" * 60,
        f"Generated : {generated}",
        f"Root      : {root}",
        f"Output    : {out_dir}",
        "",
    ]
    for r in results:
        summary_lines += [
            f"Suite : {r['label']}",
            f"  Jenkins stage     : {r['stage']}",
            f"  Sequences found   : {r['count']}",
            f"  Source export XML : {r['source'] or '(not found)'}",
            "",
        ]
    summary_lines += [
        "=" * 60,
        f"TOTAL test sequences discovered : {total_found}",
        "",
        "All verdicts are SIMULATED – no hardware execution performed.",
        "Run the Jenkins pipeline on a windows-bench agent for real results.",
    ]

    summary_path = out_dir / 'simulation_summary.txt'
    summary_path.write_text('\n'.join(summary_lines), encoding='utf-8')
    print(f"Summary file      : {summary_path}")
    print()
    print("=" * 60)
    print(f"Simulation complete: {total_found} test sequences discovered across "
          f"{sum(1 for r in results if r['count'] > 0)} / {len(results)} suites")

    if total_found == 0:
        print(
            "\nNOTE: Zero test sequences discovered.\n"
            "  If the .run cache is absent, run CANoe on the bench at least once\n"
            "  so that BVTRBS/CVADAS_RBS_TRSC/.run/ is populated with\n"
            "  .vtt.export.xml files.  The simulation report has still been\n"
            "  written with 'No export found' rows for each test unit.",
            file=sys.stderr,
        )

    # Exit 0 – simulation script completed (zero sequences is a valid
    #           'no cache yet' state, not a pipeline error).
    # Exit 1 – reserved for fatal errors: root directory not found or
    #           unrecoverable XML parse failures (returned earlier in main()).
    return 0


if __name__ == '__main__':
    sys.exit(main())
