"""
GM VIP Automation Framework – Symbol Auto-Discovery
====================================================
Queries the **active** Trace32 session to enumerate every module (source
file), function, and variable present in the loaded ELF debug information.
The result is a :class:`SymbolInventory` that can be fed directly into the
:mod:`~GM_VIP_Automation_Framework.generator` to create test-case JSON files
and companion Python scripts without any manual editing.

How it works
------------
1. ``SYMBOL.LIST *`` is written to a temporary AREA buffer which is then
   saved to a temp file so Python can parse the text.
2. Lines that contain a ``\\<filename>\\`` prefix are module-qualified;
   the module name is extracted from that prefix.
3. Type classification uses the *section kind* column emitted by T32
   (``CODE`` / ``PROC`` → function; ``DATA`` / ``BSS`` / ``VAR`` →
   variable) with a simple name-based heuristic as a fallback when the
   column is absent (works in both full-ELF and stripped-binary sessions).
4. Each discovered symbol is verified with ``SYMBOL.EXIST()`` and its
   address is resolved with ``ADDRESS.OFFSET(SYMBOL.BEGIN())``.

Public API
----------
- :class:`SymbolKind` – enumeration: MODULE, FUNCTION, VARIABLE, UNKNOWN.
- :class:`DiscoveredSymbol` – immutable record for one discovered symbol.
- :class:`SymbolInventory` – aggregated results organised by module name.
- :func:`discover_symbols` – main entry point; returns a
  :class:`SymbolInventory`.
- :func:`discover_modules` – list unique module (source-file) names.
- :func:`discover_functions` – list function symbols (optionally filtered
  to a module pattern).
- :func:`discover_variables` – list variable symbols (optionally filtered
  to a module pattern).
"""

from __future__ import annotations

import fnmatch
import re
import sys
import tempfile
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

from ..config import settings
from ..utils.exceptions import T32CommandError
from ..utils.logger import get_logger
from .debugger import _conn

logger = get_logger("symbol_discovery")

__all__ = [
    "SymbolKind",
    "DiscoveredSymbol",
    "SymbolInventory",
    "discover_symbols",
    "discover_modules",
    "discover_functions",
    "discover_variables",
]

# ---------------------------------------------------------------------------
# Trace32 PRACTICE patterns
# ---------------------------------------------------------------------------

# Module-qualified symbol: \\source_file.c\\symbol_name  (T32 uses last
# separator to delimit module from symbol name).
# The file separator may be forward or backward slash.
_MODULE_RE = re.compile(r"^[\\\/]{1,2}(.+)[\\\/]([^\\\/]+)$")

# Typical SYMBOL.LIST output column patterns (space-separated):
#   <name>   <address>   <size>   <section_kind>   [<description>]
# Section kinds we recognise:
_FUNC_KINDS   = {"CODE", "PROC", "FUNCTION", "TEXT", ".TEXT"}
_VAR_KINDS    = {"DATA", "VAR", "VARIABLE", "BSS", ".DATA", ".BSS", "RODATA", ".RODATA"}

# Name-based heuristics used when section-kind column is absent.
# Variables in embedded C often start with g_, l_, s_, or are all caps.
_VAR_NAME_RE  = re.compile(r"^(g_|G_|s_|S_|l_|L_|[A-Z][A-Z0-9_]{2,}$)")
# Function names typically have mixed-case or verb-noun patterns.
_FUNC_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

class SymbolKind(str, Enum):
    """Category of a discovered T32 symbol."""
    MODULE   = "MODULE"
    FUNCTION = "FUNCTION"
    VARIABLE = "VARIABLE"
    UNKNOWN  = "UNKNOWN"


@dataclass(frozen=True)
class DiscoveredSymbol:
    """Immutable record for one symbol discovered in Trace32.

    Attributes
    ----------
    name:
        Full Trace32 symbol name (e.g. ``"\\\\src\\\\main.c\\\\myFunc"``).
    short_name:
        Symbol name without module prefix (e.g. ``"myFunc"``).
    module:
        Source module name (e.g. ``"main.c"``).  Empty when not module-qualified.
    kind:
        :class:`SymbolKind` classification.
    address:
        Linear address as hex string (e.g. ``"0x80001234"``).
        Empty when the address could not be resolved.
    size:
        Symbol size in bytes (0 when unknown).
    exists:
        ``True`` when ``SYMBOL.EXIST()`` confirmed the symbol.
    """

    name:       str
    short_name: str       = ""
    module:     str       = ""
    kind:       SymbolKind = SymbolKind.UNKNOWN
    address:    str       = ""
    size:       int       = 0
    exists:     bool      = True

    def to_dict(self) -> dict:
        """Return a JSON-serialisable dict."""
        return {
            "name":       self.name,
            "short_name": self.short_name,
            "module":     self.module,
            "kind":       self.kind.value,
            "address":    self.address,
            "size":       self.size,
            "exists":     self.exists,
        }


class SymbolInventory:
    """Aggregated symbol-discovery results organised by module.

    Attributes
    ----------
    symbols:
        Flat list of all :class:`DiscoveredSymbol` objects.
    by_module:
        Mapping ``{module_name: [DiscoveredSymbol, …]}`` so callers can
        iterate per source file without additional filtering.
    session_timestamp:
        ISO-8601 string marking when discovery was performed.
    """

    def __init__(self, symbols: Sequence[DiscoveredSymbol] = ()) -> None:
        import datetime
        self.symbols: List[DiscoveredSymbol] = list(symbols)
        self.session_timestamp: str = (
            datetime.datetime.now(tz=datetime.timezone.utc).isoformat(timespec="seconds")
        )
        self._build_index()

    # ------------------------------------------------------------------
    # Index
    # ------------------------------------------------------------------

    def _build_index(self) -> None:
        self.by_module: Dict[str, List[DiscoveredSymbol]] = {}
        for sym in self.symbols:
            mod = sym.module or "_global_"
            self.by_module.setdefault(mod, []).append(sym)

    # ------------------------------------------------------------------
    # Filtered views
    # ------------------------------------------------------------------

    @property
    def modules(self) -> List[str]:
        """Unique module names (sorted)."""
        return sorted(self.by_module.keys())

    @property
    def functions(self) -> List[DiscoveredSymbol]:
        """All symbols classified as FUNCTION."""
        return [s for s in self.symbols if s.kind == SymbolKind.FUNCTION]

    @property
    def variables(self) -> List[DiscoveredSymbol]:
        """All symbols classified as VARIABLE."""
        return [s for s in self.symbols if s.kind == SymbolKind.VARIABLE]

    def functions_in(self, module: str) -> List[DiscoveredSymbol]:
        """Return function symbols belonging to *module*."""
        return [
            s for s in self.by_module.get(module, [])
            if s.kind == SymbolKind.FUNCTION
        ]

    def variables_in(self, module: str) -> List[DiscoveredSymbol]:
        """Return variable symbols belonging to *module*."""
        return [
            s for s in self.by_module.get(module, [])
            if s.kind == SymbolKind.VARIABLE
        ]

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def summary(self) -> str:
        """One-line text summary."""
        return (
            f"SymbolInventory: {len(self.modules)} module(s), "
            f"{len(self.functions)} function(s), "
            f"{len(self.variables)} variable(s), "
            f"{len(self.symbols)} total symbol(s)."
        )

    def to_dict(self) -> dict:
        """Return a JSON-serialisable dict of the full inventory."""
        return {
            "session_timestamp": self.session_timestamp,
            "total_symbols": len(self.symbols),
            "total_modules": len(self.modules),
            "total_functions": len(self.functions),
            "total_variables": len(self.variables),
            "symbols": [s.to_dict() for s in self.symbols],
        }

    def __len__(self) -> int:
        return len(self.symbols)

    def __iter__(self):
        return iter(self.symbols)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _print(msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    print(f"[DSC {ts}] {msg}", file=sys.stderr, flush=True)


def _resolve_conn(connection):
    return _conn(connection)


def _classify_kind(name: str, kind_col: str) -> SymbolKind:
    """Classify a symbol as FUNCTION or VARIABLE from T32 type column + name."""
    upper = kind_col.strip().upper()
    if upper in _FUNC_KINDS:
        return SymbolKind.FUNCTION
    if upper in _VAR_KINDS:
        return SymbolKind.VARIABLE
    # Heuristic fallback when T32 doesn't emit a recognisable kind column.
    if _VAR_NAME_RE.match(name):
        return SymbolKind.VARIABLE
    return SymbolKind.FUNCTION   # default: treat as function


def _make_tmp_path(suffix: str) -> Path:
    """Return a writable temp-file path that T32 can also access.

    Trace32 runs as a Windows process that may not have write permission to
    the user's ``AppData\\Local\\Temp`` folder.  Prefer the current working
    directory (the folder from which ``python main.py`` is executed), which
    both Python and T32 can always reach.  Fall back to the OS temp dir only
    if CWD is not writable.
    """
    last_exc: Optional[Exception] = None
    for tmp_dir in (Path.cwd(), None):
        try:
            file_kwargs: dict = dict(suffix=suffix, delete=False, mode="w", encoding="utf-8")
            if tmp_dir is not None:
                file_kwargs["dir"] = str(tmp_dir)
            with tempfile.NamedTemporaryFile(**file_kwargs) as fh:
                return Path(fh.name)
        except OSError as exc:
            last_exc = exc
    raise OSError(
        f"Cannot create a writable temp file in CWD or system temp dir: {last_exc}"
    )


def _fetch_symbol_list(pattern: str, conn) -> str:
    """Run ``SYMBOL.LIST <pattern>`` and return the raw text.

    Tries three strategies in order:

    1. **SYMBOL.LIST.SAVE** – direct file export (modern T32 firmware ≥ ~2020).
       T32 writes the list-window content straight to the temp file.  Returns
       immediately; an empty result means no ELF is loaded.

    2. **PRACTICE DO-script** – writes a temp CMM that uses T32 PRACTICE file
       I/O (``OPEN``/``WRITE``/``CLOSE``) with ``SYMBOL.COUNT()`` and
       ``SYMBOL.NAME(n)`` to enumerate every symbol.  Supported on T32
       firmware from approximately 2010 onward.  When the *pattern* is not
       the catch-all ``"*"`` a Python-level :func:`fnmatch.fnmatch` filter is
       applied to the returned names so only matching symbols are kept.

    3. **AREA-buffer last resort** – opens the PRACTICE AREA, clears it, runs
       ``SYMBOL.LIST``, then saves the AREA.  On most modern T32 versions
       ``SYMBOL.LIST`` outputs to its own GUI window (not the AREA), so this
       strategy is unlikely to succeed; it is kept only as a safety net.  The
       polling timeout is capped at 5 seconds to avoid a 60-second hang.

    Temp files are placed in the current working directory so that the T32
    process (which may lack write access to the system temp folder) can reach
    them.  A fallback to the OS temp dir is used if CWD is not writable.

    Returns an empty string when T32 is not available or all strategies fail.
    """
    tmp_txt: Optional[Path] = None
    tmp_cmm: Optional[Path] = None
    try:
        tmp_txt = _make_tmp_path(".txt")

        # ------------------------------------------------------------------
        # Strategy 1: SYMBOL.LIST.SAVE – direct file export.
        # SYMBOL.LIST opens its own GUI window in Trace32; AREA.SAVE cannot
        # capture that output.  SYMBOL.LIST.SAVE writes the window content
        # directly to a file, bypassing the AREA entirely.
        # ------------------------------------------------------------------
        try:
            conn.cmd(f"SYMBOL.LIST {pattern}")
            conn.cmd(f"SYMBOL.LIST.SAVE {tmp_txt}")
            text = tmp_txt.read_text(encoding="utf-8", errors="replace") if tmp_txt.exists() else ""
            logger.debug("_fetch_symbol_list: SYMBOL.LIST.SAVE strategy succeeded.")
            return text
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "SYMBOL.LIST.SAVE unavailable (%s); trying PRACTICE DO-script.", exc
            )

        # ------------------------------------------------------------------
        # Strategy 2: PRACTICE DO-script using SYMBOL.COUNT / SYMBOL.NAME.
        # Writes a temp CMM that enumerates all symbols via file I/O.
        # The DO command is synchronous: the output file is ready when it
        # returns.  A Python fnmatch filter is applied when pattern != "*".
        # Both the CMM and output .txt are in CWD so T32 can write to them.
        # ------------------------------------------------------------------
        try:
            tmp_cmm = _make_tmp_path(".cmm")
            # Use forward slashes in the CMM so Windows paths don't need
            # extra escaping (T32 PRACTICE accepts both separators).
            txt_path_fwd = str(tmp_txt).replace("\\", "/")
            tmp_cmm.write_text(
                "; Auto-generated by GM VIP Automation Framework\n"
                "; Enumerate all symbols via PRACTICE file I/O\n"
                "LOCAL &i &cnt &sym\n"
                f'OPEN #1 "{txt_path_fwd}" /Create\n'
                "&cnt=SYMBOL.COUNT()\n"
                "&i=0.\n"
                "WHILE &i<&cnt\n"
                "(\n"
                "  &sym=SYMBOL.NAME(&i)\n"
                '  IF "&sym"!=""\n'
                "  (\n"
                '    WRITE #1 "&sym"\n'
                "  )\n"
                "  &i=&i+1.\n"
                ")\n"
                "CLOSE #1\n"
                "ENDDO\n",
                encoding="utf-8",
            )
            cmm_path_fwd = str(tmp_cmm).replace("\\", "/")
            conn.cmd(f"DO {cmm_path_fwd}")
            text = tmp_txt.read_text(encoding="utf-8", errors="replace") if tmp_txt.exists() else ""
            if text:
                # Apply a Python-level glob filter when the caller specified a
                # non-trivial pattern (CMM dumps all symbols; SYMBOL.COUNT()
                # does not accept a wildcard filter in all T32 versions).
                if pattern and pattern != "*":
                    pat_lower = pattern.lower()
                    filtered: List[str] = []
                    for line in text.splitlines():
                        name = line.strip()
                        if not name:
                            continue
                        # Match against the full module-qualified name or just
                        # the short name after the last path separator.
                        short = re.split(r"[/\\]", name)[-1]
                        if (
                            fnmatch.fnmatch(name.lower(), pat_lower)
                            or fnmatch.fnmatch(short.lower(), pat_lower)
                        ):
                            filtered.append(line)
                    text = "\n".join(filtered)
                logger.debug(
                    "_fetch_symbol_list: DO-script strategy succeeded (%d chars).", len(text)
                )
                return text
            logger.debug("_fetch_symbol_list: DO-script returned empty output.")
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "DO-script approach failed (%s); falling back to AREA (last resort).", exc
            )

        # ------------------------------------------------------------------
        # Strategy 3: AREA-buffer last resort.
        # On most modern T32 versions SYMBOL.LIST does NOT output to AREA;
        # this strategy is kept only as a safety net.  The polling timeout is
        # capped at 5 s to avoid a 60-second hang.
        # ------------------------------------------------------------------
        conn.cmd("AREA")
        conn.cmd("AREA.CLEAR")
        conn.cmd(f"SYMBOL.LIST {pattern}")

        deadline = time.monotonic() + min(settings.cmm_timeout_s, 5.0)
        while time.monotonic() < deadline:
            time.sleep(0.2)
            try:
                conn.cmd(f"AREA.SAVE {tmp_txt}")
            except Exception:  # noqa: BLE001
                continue
            if tmp_txt.exists() and tmp_txt.stat().st_size > 0:
                break

        text = tmp_txt.read_text(encoding="utf-8", errors="replace") if tmp_txt.exists() else ""
        return text
    except Exception as exc:  # noqa: BLE001
        logger.warning("_fetch_symbol_list('%s') failed: %s", pattern, exc)
        return ""
    finally:
        if tmp_txt is not None and tmp_txt.exists():
            tmp_txt.unlink(missing_ok=True)
        if tmp_cmm is not None and tmp_cmm.exists():
            tmp_cmm.unlink(missing_ok=True)


def _parse_symbol_list(raw: str) -> List[DiscoveredSymbol]:
    """Parse the raw AREA text from ``SYMBOL.LIST`` into :class:`DiscoveredSymbol` objects.

    Handles multiple T32 output layouts:
    - Module-qualified:  ``\\src\\main.c\\myFunc   0x80001234   0x20   CODE``
    - Flat:              ``myFunc   0x80001234   0x20   CODE``
    - Name-only:         ``myFunc``
    """
    symbols: List[DiscoveredSymbol] = []
    seen: set = set()

    for raw_line in raw.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(";") or line.startswith("//"):
            continue
        # Skip header / separator lines (all dashes, equals signs, or tabs).
        if re.match(r"^[-=\s]+$", line):
            continue

        parts = line.split()
        if not parts:
            continue

        raw_name = parts[0]
        # Skip lines that look like addresses without a symbol (pure hex).
        if re.match(r"^0[xX][0-9A-Fa-f]+$", raw_name):
            continue

        # Parse module-qualified name.
        m = _MODULE_RE.match(raw_name)
        if m:
            module     = m.group(1)          # e.g. "src/main.c"
            short_name = m.group(2)          # e.g. "myFunc"
        else:
            module     = ""
            short_name = raw_name

        # Parse optional address, size, kind columns.
        address  = ""
        size     = 0
        kind_col = ""
        if len(parts) >= 2 and re.match(r"^0[xX]", parts[1]):
            address = parts[1]
        if len(parts) >= 3 and re.match(r"^0[xX]", parts[2]):
            try:
                size = int(parts[2], 16)
            except ValueError:
                size = 0
        if len(parts) >= 4:
            kind_col = parts[3]

        kind = _classify_kind(short_name, kind_col)

        key = (module, short_name)
        if key in seen:
            continue
        seen.add(key)

        symbols.append(
            DiscoveredSymbol(
                name=raw_name,
                short_name=short_name,
                module=module,
                kind=kind,
                address=address,
                size=size,
                exists=True,
            )
        )

    return symbols


def _resolve_addresses(
    symbols: List[DiscoveredSymbol],
    conn,
    max_symbols: int = 500,
) -> List[DiscoveredSymbol]:
    """For each symbol, verify existence and fill in the address if missing.

    Limits to *max_symbols* to keep discovery time reasonable.  Symbols
    beyond the limit are returned unchanged (address stays as parsed from
    the list output, which is usually already correct).
    """
    result: List[DiscoveredSymbol] = []
    for i, sym in enumerate(symbols):
        if i >= max_symbols:
            result.append(sym)
            continue

        # Choose the T32-qualified name for SYMBOL.EXIST.
        t32_name = sym.name

        try:
            raw = conn.fnc(f"SYMBOL.EXIST({t32_name})")
            exists = str(raw).strip().upper() in ("TRUE()", "TRUE", "1")
        except Exception as exc:  # noqa: BLE001
            logger.debug("SYMBOL.EXIST('%s') raised %s: %s", t32_name, type(exc).__name__, exc)
            exists = sym.address != ""  # trust the parsed address if no API

        if exists and not sym.address:
            try:
                raw_addr = conn.fnc(f"ADDRESS.OFFSET(SYMBOL.BEGIN({t32_name}))")
                address = str(raw_addr).strip()
            except Exception as exc:  # noqa: BLE001
                logger.debug(
                    "ADDRESS.OFFSET(SYMBOL.BEGIN('%s')) raised %s: %s",
                    t32_name, type(exc).__name__, exc,
                )
                address = ""
        else:
            address = sym.address

        result.append(
            DiscoveredSymbol(
                name=sym.name,
                short_name=sym.short_name,
                module=sym.module,
                kind=sym.kind,
                address=address,
                size=sym.size,
                exists=exists,
            )
        )
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def discover_symbols(
    pattern: str = "*",
    connection=None,
    resolve_addresses: bool = True,
    max_symbols: int = 500,
) -> SymbolInventory:
    """Discover all symbols in the active Trace32 session.

    Queries T32 with ``SYMBOL.LIST <pattern>``, parses the output, and
    optionally verifies each symbol's existence and address via
    ``SYMBOL.EXIST`` / ``SYMBOL.BEGIN``.

    Parameters
    ----------
    pattern:
        Trace32 wildcard pattern.  ``"*"`` discovers all symbols.
        Use ``"\\\\myModule.c\\\\*"`` to limit to a single source file.
    connection:
        Active :class:`~connection.T32Connection`.  Uses the module-level
        ``default_connection`` when *None*.
    resolve_addresses:
        When ``True`` (default) each symbol's existence and address are
        confirmed via individual PRACTICE function calls.  Set to ``False``
        for a fast first pass that only parses the list output (useful when
        the symbol count is very large).
    max_symbols:
        Maximum number of symbols to resolve individually.  Symbols beyond
        this limit are included in the inventory but their addresses are
        taken from the parsed SYMBOL.LIST output without individual
        ``SYMBOL.EXIST`` confirmation.

    Returns
    -------
    SymbolInventory
        Aggregated results, organised by module name.
    """
    conn = _resolve_conn(connection)
    _print(f"Starting symbol discovery (pattern='{pattern}') …")

    raw = _fetch_symbol_list(pattern, conn)
    if not raw:
        logger.warning("SYMBOL.LIST returned no output.  Is an ELF loaded?")
        return SymbolInventory()

    parsed = _parse_symbol_list(raw)
    _print(f"Parsed {len(parsed)} raw symbol entries.")

    if resolve_addresses:
        resolved = _resolve_addresses(parsed, conn, max_symbols=max_symbols)
    else:
        resolved = parsed

    inventory = SymbolInventory(resolved)
    _print(inventory.summary())
    return inventory


def discover_modules(connection=None) -> List[str]:
    """Return the unique source-module names from the T32 symbol table.

    Each name typically corresponds to a ``.c`` file compiled into the
    loaded ELF (e.g. ``"src/main.c"``).

    Parameters
    ----------
    connection:
        Active :class:`~connection.T32Connection`.

    Returns
    -------
    list[str]
        Sorted list of module names.
    """
    inventory = discover_symbols("*", connection=connection, resolve_addresses=False)
    return inventory.modules


def discover_functions(
    module_pattern: str = "*",
    connection=None,
) -> List[DiscoveredSymbol]:
    """Return function symbols from the T32 session.

    Parameters
    ----------
    module_pattern:
        Trace32 wildcard pattern.  Pass ``"\\\\myModule.c\\\\*"`` to restrict
        discovery to a single source file.
    connection:
        Active :class:`~connection.T32Connection`.

    Returns
    -------
    list[DiscoveredSymbol]
        Function symbols only, sorted by module then name.
    """
    inventory = discover_symbols(module_pattern, connection=connection)
    return sorted(inventory.functions, key=lambda s: (s.module, s.short_name))


def discover_variables(
    module_pattern: str = "*",
    connection=None,
) -> List[DiscoveredSymbol]:
    """Return variable symbols from the T32 session.

    Parameters
    ----------
    module_pattern:
        Trace32 wildcard pattern.
    connection:
        Active :class:`~connection.T32Connection`.

    Returns
    -------
    list[DiscoveredSymbol]
        Variable symbols only, sorted by module then name.
    """
    inventory = discover_symbols(module_pattern, connection=connection)
    return sorted(inventory.variables, key=lambda s: (s.module, s.short_name))
