"""
validate_capl.py - Pre-deployment CAPL syntax & correctness checker
====================================================================
Scans all .can/.cin files under GM_VIP_Automation and reports issues
that would prevent Vector CANoe from compiling them, or introduce
silent runtime bugs.  Run this script in CI/CD before deploying to
any test bench to catch mistakes early – without needing a CANoe
licence or a Windows machine.

Checks performed
----------------
1.  Bracket balance        – matched { } [ ] ( ) across each file.
2.  Include existence      – every #include path resolves to a file on disk.
3.  Declarations           – every testcase / testfunction / export testfunction
                             declaration has a paired opening brace.
4.  Cross-file refs        – every <capltestcase name="..."/> in
                             Testsuite_Environment XML files has a matching
                             testcase definition in a .can file.
5.  CAPL API name typos    – detects wrong-case CAPL built-in names that cause
                             parse errors (e.g. testStepfail → testStepFail).
6.  Forbidden identifiers  – calls to C standard-library functions or CAPL
                             API names that do NOT exist in CANoe and will cause
                             an immediate compile error
                             (e.g. atoi → _atoi64, testStop → testCaseFail).
7.  Duplicate definitions  – same testcase or testfunction name defined more
                             than once in the same file (link-time error in
                             CANoe when both modules are loaded together).
8.  snprintf format args   – single-line snprintf() calls where the number of
                             printf-style format specifiers (including CAPL-
                             specific %I64d / %I64u / %ld / %llX etc.) does not
                             match the number of extra arguments provided.
                             Under-specified strings read garbage; over-specified
                             ones silently ignore values.
9.  variables{} block      – every .can testcase file must contain at least one
                             top-level variables { } block; missing one causes
                             CANoe to reject the file.
10. Missing semicolons     – statement lines inside function bodies that end
                             with a closing ')' but have no terminating ';'
                             (a common copy-paste mistake that causes a parse
                             error on the *next* line rather than the culprit).

Usage
-----
    python validate_capl.py [--root <GM_VIP_Automation folder>]

Exit code
---------
    0  – no issues found
    1  – one or more issues detected (details printed to stdout)
"""

import argparse
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_line_comments(text: str) -> str:
    """Remove // … comments (but not inside strings)."""
    result = []
    i = 0
    in_string = False
    while i < len(text):
        ch = text[i]
        if ch == '"' and (i == 0 or text[i - 1] != '\\'):
            in_string = not in_string
        if not in_string and ch == '/' and i + 1 < len(text) and text[i + 1] == '/':
            # skip to end of line
            while i < len(text) and text[i] != '\n':
                i += 1
            continue
        result.append(ch)
        i += 1
    return ''.join(result)


def _strip_block_comments(text: str) -> str:
    """Remove /* … */ block comments (but not inside strings)."""
    result = []
    i = 0
    in_string = False
    while i < len(text):
        ch = text[i]
        # Track string literal state to avoid stripping comment markers inside strings.
        if ch == '"' and (i == 0 or text[i - 1] != '\\'):
            in_string = not in_string
        # Only treat /* as a comment start when we're not inside a string.
        if not in_string and text[i:i + 2] == '/*':
            i += 2
            while i < len(text) and text[i:i + 2] != '*/':
                if text[i] == '\n':
                    result.append('\n')  # preserve line numbers
                i += 1
            # Skip the closing */
            if i < len(text):
                i += 2
        else:
            result.append(ch)
            i += 1
    return ''.join(result)


def strip_comments(text: str) -> str:
    text = _strip_block_comments(text)
    text = _strip_line_comments(text)
    return text


# ---------------------------------------------------------------------------
# Check 1 – bracket balance
# ---------------------------------------------------------------------------

def check_bracket_balance(filepath: Path, text: str) -> list[str]:
    """Return a list of error strings for unmatched brackets (ignores string literals)."""
    issues = []
    pairs = {')': '(', ']': '[', '}': '{'}
    openers = set('({[')
    stack = []
    flat = text

    # Build line start offsets for efficient lineno/col lookup
    line_start_offsets = [0]
    for idx, ch in enumerate(flat):
        if ch == '\n':
            line_start_offsets.append(idx + 1)

    def offset_to_linecol(offset: int):
        lo, hi = 0, len(line_start_offsets) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if line_start_offsets[mid] <= offset:
                lo = mid
            else:
                hi = mid - 1
        return lo + 1, offset - line_start_offsets[lo] + 1

    i = 0
    n = len(flat)
    in_string = False
    while i < n:
        ch = flat[i]
        # Enter string literal
        if ch == '"' and not in_string:
            in_string = True
            i += 1
            continue
        # Inside string literal
        if in_string:
            if ch == '\\':
                i += 2  # skip escaped character
                continue
            if ch == '"':
                in_string = False
            i += 1
            continue
        # Normal code — check brackets
        if ch in openers:
            lineno, col = offset_to_linecol(i)
            stack.append((ch, lineno, col))
        elif ch in pairs:
            expected = pairs[ch]
            lineno, col = offset_to_linecol(i)
            if not stack:
                issues.append(
                    f"  {filepath}:{lineno}:{col}: unmatched closing '{ch}' (no opener on stack)"
                )
            elif stack[-1][0] != expected:
                issues.append(
                    f"  {filepath}:{lineno}:{col}: mismatched '{ch}' — expected close for"
                    f" '{stack[-1][0]}' opened at line {stack[-1][1]}"
                )
                stack.pop()
            else:
                stack.pop()
        i += 1
    for opener, lineno, col in stack:
        issues.append(
            f"  {filepath}:{lineno}:{col}: unclosed '{opener}' — no matching close found"
        )
    return issues


# ---------------------------------------------------------------------------
# Check 2 – #include existence
# ---------------------------------------------------------------------------

_INCLUDE_RE = re.compile(r'#include\s+"([^"]+)"')


def check_includes(filepath: Path, text: str) -> list[str]:
    """Return a list of error strings for #includes that cannot be resolved."""
    issues = []
    parent = filepath.parent
    for lineno, line in enumerate(text.splitlines(), start=1):
        m = _INCLUDE_RE.search(line)
        if not m:
            continue
        inc_path_raw = m.group(1).replace('\\', os.sep).replace('/', os.sep)
        resolved = (parent / inc_path_raw).resolve()
        if not resolved.exists():
            issues.append(
                f"  {filepath}:{lineno}: #include not found: '{m.group(1)}'"
                f" (resolved to {resolved})"
            )
    return issues


# ---------------------------------------------------------------------------
# Check 3 – function declaration / opening brace
# ---------------------------------------------------------------------------

# Matches declarations ending on the same line with no opening brace yet
_DECL_NO_BRACE_RE = re.compile(
    r'^(?:export\s+)?(?:testfunction|testcase)\s+(\w+)\s*\([^)]*\)\s*$'
)


def check_declarations(filepath: Path, text: str) -> list[str]:
    """
    Verify that every testcase/testfunction declaration is followed by an
    opening brace within the next few non-blank lines.
    """
    issues = []
    lines = text.splitlines()
    for lineno, line in enumerate(lines, start=1):
        stripped = line.strip()
        # Check for declaration pattern without opening brace on same line
        m = _DECL_NO_BRACE_RE.match(stripped)
        if not m:
            continue
        func_name = m.group(1)
        # Look ahead up to 3 lines for the opening brace
        found_brace = False
        for ahead in range(1, 4):
            if lineno - 1 + ahead < len(lines):
                ahead_line = lines[lineno - 1 + ahead].strip()
                if ahead_line.startswith('{'):
                    found_brace = True
                    break
                if ahead_line and not ahead_line.startswith('//'):
                    break  # non-blank, non-comment line that isn't {
        if not found_brace:
            issues.append(
                f"  {filepath}:{lineno}: declaration of '{func_name}' has no"
                " opening brace within 3 lines"
            )
    return issues


# ---------------------------------------------------------------------------
# Check 4 – cross-file: XML testcase names vs .can definitions
# ---------------------------------------------------------------------------

_TESTCASE_DEF_RE = re.compile(
    r'(?:export\s+)?testcase\s+(\w+)\s*\('
)


def collect_testcase_names_from_can(can_files: list[Path]) -> dict[str, Path]:
    """Return mapping of testcase name → file for all .can files."""
    defined: dict[str, Path] = {}
    for fp in can_files:
        try:
            raw = fp.read_text(encoding='latin-1', errors='replace')
        except OSError:
            continue
        cleaned = strip_comments(raw)
        for m in _TESTCASE_DEF_RE.finditer(cleaned):
            defined[m.group(1)] = fp
    return defined


def collect_testcase_refs_from_xml(xml_files: list[Path]) -> dict[str, Path]:
    """Return mapping of capltestcase name → XML file."""
    refs: dict[str, Path] = {}
    for fp in xml_files:
        try:
            tree = ET.parse(fp)
        except ET.ParseError:
            continue
        root = tree.getroot()
        for elem in root.iter('capltestcase'):
            name = elem.get('name', '').strip()
            if name:
                refs[name] = fp
    return refs


def check_xml_vs_can_consistency(
    defined: dict[str, Path], refs: dict[str, Path]
) -> list[str]:
    """Report XML references that have no matching testcase definition."""
    issues = []
    for name, xml_fp in sorted(refs.items()):
        if name not in defined:
            issues.append(
                f"  {xml_fp}: <capltestcase name=\"{name}\"> has no"
                " matching testcase definition in any .can file"
            )
    return issues


# ---------------------------------------------------------------------------
# Check 5 – known CAPL API name typos / case errors
# ---------------------------------------------------------------------------
#
# Maps each incorrect (misspelled or wrong-case) identifier to the correct one.
# These cause CANoe parse errors at compile time and are easy to miss by eye
# because CAPL function names are case-sensitive.
#
_CAPL_API_TYPOS: dict[str, str] = {
    # testStepFail is the correct CAPL built-in; 'testStepfail' (lowercase f)
    # triggers a parse error in every CANoe version.
    "testStepfail":  "testStepFail",
    # testStepPass is the correct CAPL built-in; 'testSteppass' (lowercase p)
    # is an undefined identifier and causes a parse error.
    "testSteppass":  "testStepPass",
    # testCaseFail is the correct CAPL built-in; lowercase variants are invalid.
    "testCasefail":  "testCaseFail",
    "testcasefail":  "testCaseFail",
}

# Pre-compiled regex: word-boundary match for each incorrect token so we don't
# flag occurrences inside longer identifiers.
_CAPL_TYPO_RE = re.compile(
    r'\b(' + '|'.join(re.escape(k) for k in _CAPL_API_TYPOS) + r')\b'
)


def check_capl_api_names(filepath: Path, text: str) -> list[str]:
    """Return error strings for known CAPL built-in name typos / case errors."""
    issues = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for m in _CAPL_TYPO_RE.finditer(line):
            wrong = m.group(1)
            correct = _CAPL_API_TYPOS[wrong]
            issues.append(
                f"  {filepath}:{lineno}:{m.start() + 1}: "
                f"incorrect CAPL API name '{wrong}' — use '{correct}' instead"
            )
    return issues


# ---------------------------------------------------------------------------
# Check 6 – forbidden / non-existent CAPL identifiers
# ---------------------------------------------------------------------------
#
# These identifiers do NOT exist in CANoe's CAPL runtime.  Using any of them
# causes an "unknown identifier" parse error at compile time.  Each entry maps
# the bad token to a recommended replacement and an explanation.
#
_CAPL_FORBIDDEN: dict[str, tuple[str, str]] = {
    # C standard-library calls that are absent from CAPL
    "atoi":       ("_atoi64()", "atoi() is not a CAPL built-in; use _atoi64() for integer parsing"),
    "malloc":     ("a fixed-size array", "dynamic memory allocation (malloc) is not supported in CAPL"),
    "free":       ("(remove – CAPL has no heap)", "dynamic memory deallocation (free) is not supported in CAPL"),
    "printf":     ("write() or writeDbgLevel()", "printf() does not exist in CAPL; use write() or writeDbgLevel()"),
    # CAPL test-API names that were removed / never existed
    "testStop":   ("testCaseFail()", "testStop() does not exist in CAPL; use testCaseFail() to abort a test case"),
    "TestAbort":  ("testCaseFail()", "TestAbort() does not exist in CAPL; use testCaseFail() to abort a test case"),
}

# Word-boundary regex for each forbidden token
_FORBIDDEN_RE = re.compile(
    r'\b(' + '|'.join(re.escape(k) for k in _CAPL_FORBIDDEN) + r')\s*\('
)


def check_forbidden_identifiers(filepath: Path, text: str) -> list[str]:
    """Return error strings for CAPL forbidden / non-existent function calls."""
    issues = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for m in _FORBIDDEN_RE.finditer(line):
            token = m.group(1)
            replacement, reason = _CAPL_FORBIDDEN[token]
            issues.append(
                f"  {filepath}:{lineno}:{m.start() + 1}: "
                f"forbidden call '{token}()' — {reason} (use {replacement} instead)"
            )
    return issues


# ---------------------------------------------------------------------------
# Check 7 – duplicate testcase / testfunction definitions within same file
# ---------------------------------------------------------------------------
#
# CANoe compiles each .can file in the context of the test suite.  If the same
# testcase or testfunction name is defined twice in the same file the linker
# raises an "already defined" error.  This check catches the mistake early.
#
_FUNC_DEF_RE = re.compile(
    r'(?:export\s+)?(?:testcase|testfunction)\s+(\w+)\s*\('
)


def check_duplicate_definitions(filepath: Path, text: str) -> list[str]:
    """Return error strings for testcase/testfunction names defined more than once."""
    seen: dict[str, int] = {}   # name → first lineno
    issues = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for m in _FUNC_DEF_RE.finditer(line):
            name = m.group(1)
            if name in seen:
                issues.append(
                    f"  {filepath}:{lineno}: duplicate definition of '{name}'"
                    f" (first defined at line {seen[name]})"
                )
            else:
                seen[name] = lineno
    return issues


# ---------------------------------------------------------------------------
# Check 8 – snprintf format-specifier vs argument count
# ---------------------------------------------------------------------------
#
# Counts the printf-style format specifiers in the format-string argument of a
# single-line snprintf() call and compares that count to the number of extra
# arguments supplied.  Supports all standard C specifiers PLUS the CAPL /
# Windows-specific %I64d, %I64u, %I32d, %ld, %lld, %llX, etc.
#
# Only single-line calls are checked (multi-line snprintf calls are skipped
# to avoid false positives from the argument parser).
#
# CAPL-specific format specifiers handled:
#   %I64d / %I64u / %I64x  — 64-bit signed/unsigned (Windows __int64)
#   %I32d / %I32u           — 32-bit (same as %d/%u but explicit)
#   %ld / %lu / %lx         — long int variants
#   %lld / %llu / %llX      — long long variants
#   %%                       — literal percent (does NOT consume an argument)
#
_FMT_SPEC_RE = re.compile(
    r'%(?:%|'                                      # %% = escaped, no arg
    r'[-+ #0]*'                                    # optional flags
    r'(?:\d+|\*)?'                                 # optional width
    r'(?:\.(?:\d+|\*))?'                           # optional precision
    r'(?:hh?|ll?|L|I64|I32|q|j|z|t)?'            # length modifier (CAPL: I64, I32)
    r'[diouxXeEfgGcsp]'                            # conversion specifier
    r')'
)

# Matches the entire single-line: snprintf(dest, size, "fmt" [, args]);
_SNPRINTF_RE = re.compile(
    r'\bsnprintf\s*\('
    r'\s*[^,\n]+,'          # dest buffer
    r'\s*[^,\n]+,'          # max size
    r'\s*"([^"\n]*)"'       # format string (captured in group 1)
    r'((?:[^\n;])*?)'       # optional extra args (group 2, may be empty)
    r'\)\s*;'               # closing );
)


def _count_top_level_args(s: str) -> int:
    """Count comma-separated top-level arguments in ``s`` (stops at ')' depth 0)."""
    depth = 0
    count = 0
    has_content = False
    i = 0
    while i < len(s):
        c = s[i]
        if c in '([{':
            depth += 1
        elif c in ')]}':
            if depth == 0:
                break
            depth -= 1
        elif c == ',' and depth == 0:
            count += 1
        elif c == '"':
            has_content = True
            i += 1
            while i < len(s) and not (s[i] == '"' and s[i - 1] != '\\'):
                i += 1
        if c not in ' \t\n':
            has_content = True
        i += 1
    return count + (1 if has_content else 0)


def check_snprintf_format_args(filepath: Path, text: str) -> list[str]:
    """Return error strings where snprintf format-spec count ≠ argument count."""
    issues = []
    for m in _SNPRINTF_RE.finditer(text):
        fmt = m.group(1)
        rest = (m.group(2) or '').strip().lstrip(',').strip()
        # Count specifiers, excluding %% (literal percent)
        specs = [s for s in _FMT_SPEC_RE.findall(fmt) if s != '%%']
        if not specs:
            continue
        n_args = _count_top_level_args(rest) if rest else 0
        if n_args != len(specs):
            lineno = text[:m.start()].count('\n') + 1
            issues.append(
                f"  {filepath}:{lineno}: snprintf format has {len(specs)}"
                f" specifier(s) but {n_args} argument(s) provided"
                f" (format: \"{fmt[:60]}{'...' if len(fmt) > 60 else ''}\")"
            )
    return issues


# ---------------------------------------------------------------------------
# Check 9 – variables{} block required in .can testcase files
# ---------------------------------------------------------------------------
#
# Every CANoe .can module must contain a top-level ``variables { }`` block
# to declare its global variables.  A file that has testcase / testfunction
# definitions but no variables block will cause CANoe to reject it with a
# structural parse error.
#
_VARIABLES_BLOCK_RE = re.compile(r'\bvariables\s*\{')


def check_variables_block(filepath: Path, text: str) -> list[str]:
    """Return an error if a .can file that defines testcases has no variables{} block."""
    # Only applies to .can files (not .cin libraries, which are permitted to
    # omit the variables block when they have no module-level state).
    if filepath.suffix.lower() != '.can':
        return []
    # Skip example/documentation files
    if 'Docs' in filepath.parts:
        return []
    # Must contain at least one testcase or testfunction definition
    has_testfunc = bool(_FUNC_DEF_RE.search(text))
    if not has_testfunc:
        return []
    if not _VARIABLES_BLOCK_RE.search(text):
        return [
            f"  {filepath}: .can file defines testcase/testfunction but has no"
            " top-level variables{} block — CANoe will reject this file"
        ]
    return []


# ---------------------------------------------------------------------------
# Check 10 – missing semicolons on statement lines
# ---------------------------------------------------------------------------
#
# A statement line that ends with ')' inside a function body almost always
# needs a terminating ';'.  When it is omitted CANoe raises a parse error on
# the *following* line, making the real culprit hard to find.
#
# Heuristic: inside a function body (brace depth ≥ 1), a non-blank line that
# • ends with ')' (after stripping whitespace / trailing comments), AND
# • is not a control-flow keyword (if / for / while / switch / do / else), AND
# • is not a function *definition* (the next non-blank line is not '{'), AND
# • the closing ')' is balanced (the line contains a matching '(')
# … is flagged as likely missing a semicolon.
#
_CONTROL_FLOW_RE = re.compile(r'^\s*(if|else\s+if|for|while|switch|do|else)\b')
_FUNC_DECL_STYLE_RE = re.compile(
    r'^\s*(?:export\s+)?'
    r'(?:testcase|testfunction|void|byte|int|long|float|char|word|dword|qword|int64)\s+\w+'
)


def check_missing_semicolons(filepath: Path, text: str) -> list[str]:
    """Return warnings for statement lines that likely need a terminating ';'."""
    issues = []
    lines = text.splitlines()
    brace_depth = 0
    n = len(lines)

    for idx, line in enumerate(lines):
        raw_line = line.rstrip()

        # Safety: strip any residual inline comments the file-level stripper may
        # have missed (can happen when in-string state drifts across a large file).
        clean = re.sub(r'//.*$', '', raw_line).rstrip().strip()

        # Track brace depth (approximation — good enough for heuristics)
        brace_depth += raw_line.count('{') - raw_line.count('}')

        if brace_depth <= 0:
            continue           # at file scope — function definitions are OK without ;
        if not clean:
            continue
        if clean.startswith('#'):
            continue           # preprocessor directives (#pragma, #include, …)
        if not clean.endswith(')'):
            continue
        # Skip control-flow keywords, including patterns like "{if (" or "} else if ("
        if re.match(r'^\{?\s*(if|else\s*if|for|while|switch|do)\b', clean):
            continue
        if re.match(r'^\}\s*(else\s*if|else)\b', clean):
            continue
        if _CONTROL_FLOW_RE.match(clean):
            continue
        # Skip boolean/logical continuation lines (multi-line condition)
        if clean.startswith('||') or clean.startswith('&&'):
            continue
        if _FUNC_DECL_STYLE_RE.match(clean):
            continue

        # The closing ')' must be balanced by a matching opener on this very line
        opens = clean.count('(')
        closes = clean.count(')')
        if opens == 0 or opens != closes:
            continue           # unbalanced — multi-line call or complex expression

        # Check that the next non-blank line is not '{' (= function/block opener)
        for ahead in range(1, 4):
            if idx + ahead >= n:
                break
            nxt = re.sub(r'//.*$', '', lines[idx + ahead]).strip()
            if nxt and not nxt.startswith('//'):
                if nxt.startswith('{'):
                    break      # block opener — this is a declaration, not a call
                lineno = idx + 1
                issues.append(
                    f"  {filepath}:{lineno}: possible missing ';' after"
                    f" closing ')' — statement: {clean[:80]}"
                )
                break

    return issues


# ---------------------------------------------------------------------------
# Main driver
# ---------------------------------------------------------------------------

def find_files(root: Path, extensions: list[str]) -> list[Path]:
    result = []
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            if any(fn.lower().endswith(ext) for ext in extensions):
                result.append(Path(dirpath) / fn)
    return sorted(result)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Pre-deployment CAPL syntax consistency checker for GM VIP Automation"
    )
    parser.add_argument(
        '--root',
        type=Path,
        default=Path(__file__).resolve().parent,
        help="Root directory of GM_VIP_Automation (default: same folder as this script)",
    )
    args = parser.parse_args()
    root: Path = args.root.resolve()

    if not root.is_dir():
        print(f"ERROR: root directory not found: {root}", file=sys.stderr)
        return 1

    capl_files = find_files(root, ['.can', '.cin'])
    testsuite_dir = root / 'Testsuite_Environment'
    if not testsuite_dir.is_dir():
        print(
            f"WARNING: Testsuite_Environment folder not found under {root}. "
            "Cross-file XML-vs-CAPL consistency check will be skipped.",
            file=sys.stderr,
        )
        xml_files = []
    else:
        xml_files = find_files(testsuite_dir, ['.xml'])

    all_issues: list[str] = []

    print(f"Scanning {len(capl_files)} CAPL file(s) and {len(xml_files)} XML file(s) under {root}\n")

    # ---- Per-file checks ----
    for fp in capl_files:
        try:
            raw = fp.read_text(encoding='latin-1', errors='replace')
        except OSError as exc:
            all_issues.append(f"  {fp}: could not read file: {exc}")
            continue

        cleaned = strip_comments(raw)

        file_issues = []
        file_issues += check_bracket_balance(fp, cleaned)
        file_issues += check_includes(fp, raw)            # raw: keep line numbers accurate
        file_issues += check_declarations(fp, cleaned)
        file_issues += check_capl_api_names(fp, cleaned)
        file_issues += check_forbidden_identifiers(fp, cleaned)
        file_issues += check_duplicate_definitions(fp, cleaned)
        file_issues += check_snprintf_format_args(fp, cleaned)
        file_issues += check_variables_block(fp, cleaned)
        file_issues += check_missing_semicolons(fp, cleaned)

        if file_issues:
            print(f"[FAIL] {fp.relative_to(root)}")
            for issue in file_issues:
                print(issue)
            print()
            all_issues += file_issues
        else:
            print(f"[OK]   {fp.relative_to(root)}")

    # ---- Cross-file checks ----
    if xml_files:
        print("\n--- Cross-file consistency (XML test suites vs .can definitions) ---")
        defined = collect_testcase_names_from_can(capl_files)
        refs = collect_testcase_refs_from_xml(xml_files)
        cross_issues = check_xml_vs_can_consistency(defined, refs)
        if cross_issues:
            for issue in cross_issues:
                print(issue)
            all_issues += cross_issues
        else:
            print("[OK]   All XML <capltestcase> names resolved to a .can definition.")

    # ---- Summary ----
    print(f"\n{'='*60}")
    if all_issues:
        print(f"RESULT: {len(all_issues)} issue(s) found. Fix before deploying to benches.")
        return 1
    else:
        print("RESULT: No issues found. CAPL files are consistent.")
        return 0


if __name__ == '__main__':
    sys.exit(main())
