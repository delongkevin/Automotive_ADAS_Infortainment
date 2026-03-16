"""
simulate_tests.py  –  Virtual Bench Simulation for GM VIP Automation
=====================================================================
Discovers all CAPL testcase definitions and generates simulated XML and
JUnit-compatible test reports without physical hardware (ECU / CANoe /
Trace32).

What it does
------------
1. Scans every .can file under GM_VIP_Automation for testcase definitions.
2. Reads every Testsuite_Environment/*.xml file for <capltestcase> references
   grouped by suite and test group.
3. For each suite XML it writes two report files into the output directory:

   <suite_name>_simulated.xml  –  CANoe testmodule schema consumed by
                                    merge_reports.py.  Each testcase is
                                    given verdict="simulated" when its
                                    definition was found in a .can file,
                                    or verdict="error" when it was not.

   <suite_name>_junit.xml      –  JUnit schema for the Jenkins junit()
                                    step.  Found testcases appear as plain
                                    <testcase> elements (green in Jenkins);
                                    missing testcases contain an <error>
                                    element (red in Jenkins).

4. Writes simulation_summary.txt with a per-suite table.

Exit codes
----------
    0  –  simulation complete; all XML <capltestcase> refs resolved
    1  –  root not found, no suites discovered, or ≥1 unresolved refs

Usage
-----
    python simulate_tests.py [--root <GM_VIP_Automation folder>]
                             [--out-dir <output directory>]
"""

from __future__ import annotations

import argparse
import datetime
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# CAPL testcase discovery
# ---------------------------------------------------------------------------

_TESTCASE_DEF_RE = re.compile(
    r'(?:export\s+)?testcase\s+(\w+)\s*\('
)
_BLOCK_COMMENT_RE = re.compile(r'/\*.*?\*/', re.DOTALL)
_LINE_COMMENT_RE  = re.compile(r'//[^\n]*')


def _strip_comments(text: str) -> str:
    """Remove CAPL block and line comments, preserving line count."""
    text = _BLOCK_COMMENT_RE.sub(
        lambda m: '\n' * m.group(0).count('\n'), text
    )
    text = _LINE_COMMENT_RE.sub('', text)
    return text


def discover_testcases(root: Path) -> Dict[str, Path]:
    """
    Return {testcase_name: can_filepath} for all testcase definitions found
    in .can files under *root*.  The first definition wins when duplicates
    exist (same name in multiple files is a configuration error but we handle
    it gracefully).
    """
    defined: Dict[str, Path] = {}
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            if fn.lower().endswith('.can'):
                fp = Path(dirpath) / fn
                try:
                    raw = fp.read_text(encoding='latin-1', errors='replace')
                except OSError:
                    continue
                cleaned = _strip_comments(raw)
                for m in _TESTCASE_DEF_RE.finditer(cleaned):
                    defined.setdefault(m.group(1), fp)
    return defined


# ---------------------------------------------------------------------------
# Test suite discovery
# ---------------------------------------------------------------------------

def discover_suites(
    testsuite_dir: Path,
) -> List[Tuple[str, ET.ElementTree, Path]]:
    """
    Return [(suite_name, parsed_tree, filepath), …] for every XML file in
    *testsuite_dir* that can be parsed.
    """
    suites: List[Tuple[str, ET.ElementTree, Path]] = []
    for fp in sorted(testsuite_dir.glob('*.xml')):
        try:
            tree = ET.parse(fp)
        except ET.ParseError as exc:
            print(f"  WARNING: could not parse {fp}: {exc}", file=sys.stderr)
            continue
        suites.append((fp.stem, tree, fp))
    return suites


# ---------------------------------------------------------------------------
# XML writing helpers
# ---------------------------------------------------------------------------

def _collect_suite_cases(
    suite_tree: ET.ElementTree,
    suite_name: str,
) -> List[Tuple[str, str, str]]:
    """
    Return [(group_title, tc_name, tc_title), …] for every
    <capltestcase> reference in the suite XML, in document order.
    Groups with no live capltestcase children are skipped (e.g. fully
    commented-out blocks).
    """
    suite_root = suite_tree.getroot()
    cases: List[Tuple[str, str, str]] = []

    for tg_elem in suite_root.iter('testgroup'):
        tg_title = tg_elem.get('title', 'Group')
        for tc_elem in tg_elem.findall('capltestcase'):
            tc_name = tc_elem.get('name', '').strip()
            if not tc_name:
                continue
            tc_title = tc_elem.get('title', tc_name)
            cases.append((tg_title, tc_name, tc_title))

    # Top-level <capltestcase> elements not inside any <testgroup>
    for tc_elem in suite_root.findall('capltestcase'):
        tc_name = tc_elem.get('name', '').strip()
        if not tc_name:
            continue
        tc_title = tc_elem.get('title', tc_name)
        cases.append(('(ungrouped)', tc_name, tc_title))

    return cases


def _write_canoe_xml(
    suite_name: str,
    suite_tree: ET.ElementTree,
    defined: Dict[str, Path],
    out_path: Path,
    root_dir: Path,
) -> Tuple[int, int]:
    """
    Write a CANoe testmodule-schema XML file for merge_reports.py.
    Returns (found_count, missing_count).
    """
    suite_root = suite_tree.getroot()
    title      = suite_root.get('title', suite_name)
    ts         = datetime.datetime.now().isoformat(timespec='seconds')

    mod_elem = ET.Element(
        'testmodule',
        title=f"{title} [Simulation]",
        generated=ts,
        note="Syntax validated only. Actual results require hardware execution.",
    )

    cases      = _collect_suite_cases(suite_tree, suite_name)
    found      = 0
    missing    = 0

    # Group by tg_title
    from itertools import groupby
    for tg_title, group_iter in groupby(cases, key=lambda t: t[0]):
        grp_elem = ET.SubElement(mod_elem, 'testgroup', title=tg_title)
        for _, tc_name, tc_title in group_iter:
            if tc_name in defined:
                verdict = 'simulated'
                src     = str(defined[tc_name].relative_to(root_dir))
                desc    = f"Syntax validated. Source: {src}"
                found  += 1
            else:
                verdict = 'error'
                desc    = (
                    f"ERROR: testcase '{tc_name}' not found in any .can file. "
                    "Check CAPL source or XML suite configuration."
                )
                missing += 1

            tc_elem   = ET.SubElement(grp_elem, 'testcase',
                                      name=tc_name, title=tc_title,
                                      verdict=verdict)
            step_elem = ET.SubElement(tc_elem, 'step',
                                      name='Simulation', verdict=verdict)
            desc_elem = ET.SubElement(step_elem, 'description')
            desc_elem.text = desc

    out_path.parent.mkdir(parents=True, exist_ok=True)
    tree = ET.ElementTree(mod_elem)
    # ET.indent available since Python 3.9; fall back gracefully on older builds
    if hasattr(ET, 'indent'):
        ET.indent(tree, space='    ')
    with out_path.open('wb') as fh:
        fh.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
        tree.write(fh, encoding='UTF-8', xml_declaration=False)
        fh.write(b'\n')

    return found, missing


def _write_junit_xml(
    suite_name: str,
    suite_tree: ET.ElementTree,
    defined: Dict[str, Path],
    out_path: Path,
) -> Tuple[int, int]:
    """
    Write a JUnit-schema XML file for the Jenkins junit() step.
    Returns (found_count, missing_count).
    """
    suite_root  = suite_tree.getroot()
    title       = suite_root.get('title', suite_name)
    ts          = datetime.datetime.now().isoformat(timespec='seconds')
    cases       = _collect_suite_cases(suite_tree, suite_name)

    errors  = sum(1 for _, tc, _ in cases if tc not in defined)
    total   = len(cases)

    suite_elem = ET.Element(
        'testsuite',
        name=f"{title} [Simulation]",
        tests=str(total),
        failures='0',
        errors=str(errors),
        skipped='0',
        time='0',
        timestamp=ts,
    )

    for tg_title, tc_name, _ in cases:
        classname = f"{suite_name}.{tg_title}"
        tc_elem   = ET.SubElement(suite_elem, 'testcase',
                                   name=tc_name, classname=classname,
                                   time='0')
        if tc_name not in defined:
            err = ET.SubElement(tc_elem, 'error',
                                message="Testcase not found in any .can file")
            err.text = (
                f"<capltestcase name=\"{tc_name}\"/> referenced in "
                f"{suite_name}.xml has no matching testcase definition "
                "in any .can file under GM_VIP_Automation."
            )
        else:
            out = ET.SubElement(tc_elem, 'system-out')
            out.text = (
                "SIMULATED: Syntax validated. "
                "Testcase definition found in CAPL source. "
                "Awaiting physical hardware execution for actual result."
            )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    tree = ET.ElementTree(suite_elem)
    if hasattr(ET, 'indent'):
        ET.indent(tree, space='    ')
    with out_path.open('wb') as fh:
        fh.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
        tree.write(fh, encoding='UTF-8', xml_declaration=False)
        fh.write(b'\n')

    found = total - errors
    return found, errors


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Virtual bench simulation for GM VIP Automation. "
            "Generates simulated CANoe XML and JUnit test reports "
            "without physical hardware."
        )
    )
    parser.add_argument(
        '--root', '-r',
        type=Path,
        default=Path(__file__).resolve().parent,
        help="Root directory of GM_VIP_Automation (default: same folder as this script)",
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

    out_dir: Path = (args.out_dir or root / 'Test Reports' / 'simulation').resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Step 1: discover all testcase definitions from .can files
    # ------------------------------------------------------------------
    print(f"Scanning for testcase definitions under: {root}")
    defined = discover_testcases(root)
    print(f"  {len(defined)} testcase definition(s) found in .can files")

    # ------------------------------------------------------------------
    # Step 2: discover test suites
    # ------------------------------------------------------------------
    testsuite_dir = root / 'Testsuite_Environment'
    if not testsuite_dir.is_dir():
        print(
            f"ERROR: Testsuite_Environment not found under {root}",
            file=sys.stderr,
        )
        return 1

    suites = discover_suites(testsuite_dir)
    if not suites:
        print(
            "ERROR: no XML suite files found in Testsuite_Environment/",
            file=sys.stderr,
        )
        return 1

    print(f"  {len(suites)} test suite XML(s) found")
    print()

    # ------------------------------------------------------------------
    # Step 3: generate per-suite XML reports
    # ------------------------------------------------------------------
    # CANoe-schema XMLs go directly in out_dir (read by merge_reports.py).
    # JUnit XMLs go in out_dir/junit/ to avoid being picked up by the
    # merge_reports HTML scanner.
    # ------------------------------------------------------------------
    junit_dir = out_dir / 'junit'
    junit_dir.mkdir(parents=True, exist_ok=True)

    total_found   = 0
    total_missing = 0
    summary_lines: List[str] = [
        "GM VIP Automation – Virtual Bench Simulation Summary",
        "=" * 56,
        f"Generated : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Root      : {root}",
        f"Output    : {out_dir}",
        "",
    ]

    for suite_name, suite_tree, suite_path in suites:
        canoe_out = out_dir  / f"{suite_name}_simulated.xml"
        junit_out = junit_dir / f"{suite_name}_junit.xml"

        found, missing = _write_canoe_xml(
            suite_name, suite_tree, defined, canoe_out, root
        )
        _write_junit_xml(suite_name, suite_tree, defined, junit_out)

        total_found   += found
        total_missing += missing

        status = "OK  " if missing == 0 else "WARN"
        print(f"  [{status}] {suite_name:40s}  {found:4d} found  {missing:3d} missing")
        if missing > 0:
            # List the missing names for easy diagnosis
            cases = _collect_suite_cases(suite_tree, suite_name)
            for _, tc_name, _ in cases:
                if tc_name not in defined:
                    print(f"          ! {tc_name}")

        summary_lines += [
            f"Suite: {suite_name}",
            f"  Source XML          : {suite_path.name}",
            f"  Testcases found     : {found}",
            f"  Testcases missing   : {missing}",
            f"  CANoe XML           : {canoe_out.name}",
            f"  JUnit XML           : junit/{junit_out.name}",
            "",
        ]

    summary_lines += [
        "=" * 56,
        f"TOTAL  Found: {total_found}   Missing: {total_missing}",
        "",
        "Definitions",
        "-----------",
        "  found   = testcase definition exists in a .can file",
        "  missing = <capltestcase> in suite XML has no .can definition",
        "",
        "verdict='simulated' – definition found; not executed on hardware",
        "verdict='error'     – definition missing; fix before bench run",
        "",
        "Actual pass/fail results require physical hardware execution.",
    ]

    summary_path = out_dir / 'simulation_summary.txt'
    summary_path.write_text('\n'.join(summary_lines), encoding='utf-8')

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print()
    print("=" * 60)
    overall = "OK – all testcase refs resolved" if total_missing == 0 \
        else f"WARNING – {total_missing} testcase ref(s) not found in .can files"
    print(f"Simulation complete: {total_found} simulated, "
          f"{total_missing} undefined  |  {overall}")
    print(f"Output directory  : {out_dir}")
    print(f"Summary file      : {summary_path}")

    return 1 if total_missing > 0 else 0


if __name__ == '__main__':
    sys.exit(main())
