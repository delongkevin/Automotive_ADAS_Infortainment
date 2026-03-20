"""
GM VIP Automation Framework – Graphical User Interface
=======================================================
A tkinter-based GUI application that exposes **every feature** available in
the command-line ``main.py`` entry point through an intuitive, tester-friendly
interface.

Key capabilities
----------------
* Run any Python test suite (mock or live) – same as ``--suite``
* Run any JSON-driven test-case file – same as ``--json``
* Discover Trace32 symbols with pattern / module / breakpoint filters –
  same as ``--discover``
* Edit and save ``config.json`` without leaving the application
* Real-time colour-coded output log (stdout + stderr captured from background
  threads so the UI never freezes during long runs)
* Stop a running test at any time without killing the application
* Open the generated HTML report directly from the UI

Running the GUI
---------------
From the framework directory::

    python gui.py

Or via the package entry point (once installed with ``pip install -e .``)::

    python -m GM_VIP_Automation_Framework.gui

No additional packages beyond the Python standard library are required.
``tkinter`` ships with every standard CPython distribution.
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import platform
import queue
import subprocess
import sys
import threading
import time
import traceback
import unittest
import webbrowser
from pathlib import Path
from typing import List, Optional

# ---------------------------------------------------------------------------
# Path bootstrap (same as main.py so imports work from any working directory)
# ---------------------------------------------------------------------------
_FRAMEWORK_DIR = Path(__file__).resolve().parent          # GM_VIP_Automation_Framework/
_REPO_ROOT     = _FRAMEWORK_DIR.parent                    # <repo_root>/
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# tkinter imports (stdlib – always available with standard CPython)
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

# ---------------------------------------------------------------------------
# Import helpers from main.py so there is no feature duplication
# ---------------------------------------------------------------------------
from GM_VIP_Automation_Framework.main import (
    _discover_python_suites,
    _discover_json_files,
    _suite_label,
    _ensure_t32_running,
    _run_python_suite,
    _run_all_python_suites,
    _run_json_suite,
    _run_all_json_suites,
    _run_discover,
    _FRAMEWORK_DIR as _FW_DIR,
    _TESTS_DIR,
)

# ---------------------------------------------------------------------------
# Colour palette
# ---------------------------------------------------------------------------
_CLR = {
    "bg":         "#f0f2f5",
    "panel":      "#ffffff",
    "header":     "#1a3a5c",
    "accent":     "#e8230a",   # Magna red
    "btn_run":    "#28a745",
    "btn_stop":   "#dc3545",
    "btn_open":   "#0056b3",
    "btn_clear":  "#6c757d",
    "log_pass":   "#1a7a2e",
    "log_fail":   "#c0392b",
    "log_warn":   "#b7770d",
    "log_info":   "#0056b3",
    "log_debug":  "#555555",
    "log_error":  "#c0392b",
    "log_bg":     "#1e1e1e",
    "log_fg":     "#d4d4d4",
}

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Seconds to wait after sending QUIT before force-killing the T32 process.
_T32_QUIT_WAIT_S = 2

# Common Trace32 executable names used as a fallback when the setting is empty.
_T32_FALLBACK_EXE_NAMES = frozenset({
    "t32marm.exe", "t32marm64.exe", "t32mppc.exe",
    "t32marm",     "t32marm64",     "t32mppc",
})

# ---------------------------------------------------------------------------
# Thread-safe output capture
# ---------------------------------------------------------------------------

class _QueueWriter(io.TextIOBase):
    """File-like writer that posts lines to a :class:`queue.Queue`.

    stdout / stderr are temporarily redirected to this writer during a test
    run so that the GUI log panel receives every line of output without
    blocking the UI event loop.
    """

    def __init__(self, q: "queue.Queue[tuple]", tag: str = "info") -> None:
        self._q   = q
        self._tag = tag
        self._buf = ""

    def write(self, text: str) -> int:
        self._buf += text
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            self._q.put(("log", line, self._classify(line)))
        return len(text)

    def flush(self) -> None:
        if self._buf:
            self._q.put(("log", self._buf, self._classify(self._buf)))
            self._buf = ""

    @staticmethod
    def _classify(line: str) -> str:
        lo = line.lower()
        if any(kw in lo for kw in ("error", "fail", "exception", "traceback")):
            return "error"
        if any(kw in lo for kw in ("warn", "warning")):
            return "warn"
        if any(kw in lo for kw in ("pass", "ok", "✔", "✅", "passed")):
            return "pass"
        if any(kw in lo for kw in ("skip", "discover", "running", "connecting")):
            return "info"
        return "debug"


# ---------------------------------------------------------------------------
# Background runner
# ---------------------------------------------------------------------------

class _TestRunner:
    """Runs tests in a daemon thread; posts status messages via a queue."""

    def __init__(self, q: "queue.Queue[tuple]") -> None:
        self._q      = q
        self._thread: Optional[threading.Thread] = None
        self._stop   = threading.Event()

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def stop(self) -> None:
        """Signal the running thread to stop (best-effort)."""
        self._stop.set()

    def run(self, target, *args, **kwargs) -> None:
        """Launch *target* in a daemon thread, capturing stdout/stderr."""
        if self.running:
            messagebox.showwarning("Busy", "A test is already running. Stop it first.")
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._wrapper,
            args=(target, args, kwargs),
            daemon=True,
        )
        self._thread.start()

    def _wrapper(self, target, args, kwargs) -> None:
        self._q.put(("status", "running"))
        writer = _QueueWriter(self._q)
        old_out, old_err = sys.stdout, sys.stderr
        sys.stdout = writer
        sys.stderr = writer
        try:
            target(*args, stop_event=self._stop, **kwargs)
        except Exception:
            tb = traceback.format_exc()
            self._q.put(("log", tb, "error"))
        finally:
            sys.stdout = old_out
            sys.stderr = old_err
            writer.flush()
            self._q.put(("status", "idle"))


# ---------------------------------------------------------------------------
# Tooltip helper
# ---------------------------------------------------------------------------

class _ToolTip:
    def __init__(self, widget: tk.Widget, text: str) -> None:
        self._widget = widget
        self._text   = text
        self._tip: Optional[tk.Toplevel] = None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)

    def _show(self, _event=None) -> None:
        if self._tip:
            return
        x = self._widget.winfo_rootx() + 20
        y = self._widget.winfo_rooty() + self._widget.winfo_height() + 4
        self._tip = tk.Toplevel(self._widget)
        self._tip.wm_overrideredirect(True)
        self._tip.wm_geometry(f"+{x}+{y}")
        lbl = tk.Label(
            self._tip, text=self._text, justify=tk.LEFT,
            background="#fffde7", relief="solid", borderwidth=1,
            font=("Helvetica", 9), wraplength=300, padx=6, pady=4,
        )
        lbl.pack()

    def _hide(self, _event=None) -> None:
        if self._tip:
            self._tip.destroy()
            self._tip = None


# ---------------------------------------------------------------------------
# Main application window
# ---------------------------------------------------------------------------

class GMVIPGui(tk.Tk):
    """Root window for the GM VIP Automation Framework GUI."""

    # How often (ms) the event loop polls the output queue
    _POLL_MS = 80

    def __init__(self) -> None:
        super().__init__()

        self.title("GM VIP Automation Framework")
        self.geometry("1100x760")
        self.minsize(900, 600)
        self.configure(bg=_CLR["bg"])

        # Shared state
        self._q: "queue.Queue[tuple]" = queue.Queue()
        self._runner = _TestRunner(self._q)
        self._last_report_path: Optional[Path] = None
        self._t32_process: Optional[subprocess.Popen] = None

        # --- tkinter variables (must live on self so GC keeps them) ---------
        self._mode_var        = tk.StringVar(value="mock")
        self._port_var        = tk.StringVar(value="20000")
        self._auto_launch_var = tk.BooleanVar(value=False)
        self._cmm_var         = tk.StringVar(value="")
        self._verbose_var     = tk.BooleanVar(value=False)
        self._status_var      = tk.StringVar(value="Ready")
        self._anim_idx        = 0

        self._build_ui()
        self._refresh_suite_lists()
        self._poll_queue()

    # ------------------------------------------------------------------ build

    def _build_ui(self) -> None:
        """Assemble all UI regions."""
        self._build_menu()
        self._build_header()

        # Main content area: left settings + right tabs
        main = tk.Frame(self, bg=_CLR["bg"])
        main.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 6))

        self._build_settings_panel(main)
        self._build_notebook(main)

        # Output log (bottom, full width)
        self._build_log_panel()

        # Status bar
        self._build_status_bar()

    def _build_menu(self) -> None:
        bar = tk.Menu(self)
        self.config(menu=bar)

        file_menu = tk.Menu(bar, tearoff=0)
        file_menu.add_command(label="Refresh Suite Lists",  command=self._refresh_suite_lists)
        file_menu.add_command(label="Open HTML Report…",    command=self._open_report_dialog)
        file_menu.add_separator()
        file_menu.add_command(label="Exit",                 command=self.destroy)
        bar.add_cascade(label="File", menu=file_menu)

        run_menu = tk.Menu(bar, tearoff=0)
        run_menu.add_command(label="Run Selected",  command=self._run_selected)
        run_menu.add_command(label="Stop",          command=self._stop_run)
        run_menu.add_separator()
        run_menu.add_command(label="Open Last Report in Browser", command=self._open_last_report)
        bar.add_cascade(label="Run", menu=run_menu)

        help_menu = tk.Menu(bar, tearoff=0)
        help_menu.add_command(label="About",  command=self._show_about)
        help_menu.add_command(label="README", command=self._open_readme)
        bar.add_cascade(label="Help", menu=help_menu)

    def _build_header(self) -> None:
        hdr = tk.Frame(self, bg=_CLR["header"], pady=8)
        hdr.pack(fill=tk.X)

        title = tk.Label(
            hdr,
            text="  GM VIP Automation Framework",
            font=("Arial Black", 15, "bold"),
            fg="#ffffff", bg=_CLR["header"],
        )
        title.pack(side=tk.LEFT, padx=14)

        accent = tk.Label(
            hdr,
            text="● MAGNA",
            font=("Arial", 10, "bold"),
            fg=_CLR["accent"], bg=_CLR["header"],
        )
        accent.pack(side=tk.RIGHT, padx=14)

    def _build_settings_panel(self, parent: tk.Frame) -> None:
        """Left-hand settings pane (connection + misc options)."""
        pane = tk.LabelFrame(
            parent, text=" Connection Settings ",
            font=("Arial", 9, "bold"), bg=_CLR["panel"],
            relief="groove", bd=2, padx=10, pady=8,
        )
        pane.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 8), pady=6)

        # Mode
        tk.Label(pane, text="Mode:", bg=_CLR["panel"], font=("Arial", 9)).grid(
            row=0, column=0, sticky=tk.W, pady=(0, 2))
        mode_frame = tk.Frame(pane, bg=_CLR["panel"])
        mode_frame.grid(row=1, column=0, sticky=tk.W, pady=(0, 6))
        for text, val in (("Mock (no hardware)", "mock"), ("Live (real T32)", "live")):
            rb = tk.Radiobutton(
                mode_frame, text=text, variable=self._mode_var, value=val,
                bg=_CLR["panel"], font=("Arial", 9), activebackground=_CLR["panel"],
            )
            rb.pack(anchor=tk.W)
        _ToolTip(mode_frame,
                 "Mock: all T32 calls simulated – no hardware needed.\n"
                 "Live: connect to a real running Trace32 instance.")

        # Port
        tk.Label(pane, text="RCL Port:", bg=_CLR["panel"], font=("Arial", 9)).grid(
            row=2, column=0, sticky=tk.W)
        port_entry = tk.Entry(pane, textvariable=self._port_var, width=10,
                              font=("Courier", 9))
        port_entry.grid(row=3, column=0, sticky=tk.W, pady=(2, 6))
        _ToolTip(port_entry, "Trace32 RCL port (default 20000). Must match PORT= in config.t32.")

        # Auto-launch
        al_cb = tk.Checkbutton(
            pane, text="Auto-launch T32", variable=self._auto_launch_var,
            bg=_CLR["panel"], font=("Arial", 9), activebackground=_CLR["panel"],
        )
        al_cb.grid(row=4, column=0, sticky=tk.W, pady=(0, 2))
        _ToolTip(al_cb, "Launch Trace32 automatically when not already running.\n"
                        "Requires t32_exe_path set in config.json or Configuration tab.")

        # CMM script
        tk.Label(pane, text="CMM Script (optional):", bg=_CLR["panel"],
                 font=("Arial", 9)).grid(row=5, column=0, sticky=tk.W, pady=(4, 0))
        cmm_frame = tk.Frame(pane, bg=_CLR["panel"])
        cmm_frame.grid(row=6, column=0, sticky=tk.EW, pady=(2, 2))
        cmm_entry = tk.Entry(cmm_frame, textvariable=self._cmm_var, width=18,
                             font=("Courier", 8))
        cmm_entry.pack(side=tk.LEFT)
        tk.Button(cmm_frame, text="…", font=("Arial", 9), padx=2,
                  command=self._browse_cmm).pack(side=tk.LEFT, padx=2)
        _ToolTip(cmm_entry,
                 "Optional CMM startup script passed to T32 at launch.\n"
                 "Only used when Auto-launch is enabled.")

        # CMM edit + reload buttons
        cmm_action_frame = tk.Frame(pane, bg=_CLR["panel"])
        cmm_action_frame.grid(row=7, column=0, sticky=tk.EW, pady=(0, 4))
        tk.Button(
            cmm_action_frame, text="✏ Edit CMM", font=("Arial", 8),
            bg="#17a2b8", fg="#fff", relief="flat", padx=4, pady=2,
            cursor="hand2", command=self._edit_cmm_in_editor,
        ).pack(side=tk.LEFT, padx=(0, 4))
        tk.Button(
            cmm_action_frame, text="↺ Reload CMM", font=("Arial", 8),
            bg=_CLR["btn_clear"], fg="#fff", relief="flat", padx=4, pady=2,
            cursor="hand2", command=self._reload_cmm,
        ).pack(side=tk.LEFT)
        _ToolTip(cmm_action_frame,
                 "Edit CMM: open the selected CMM script in a text editor.\n"
                 "Reload CMM: re-read the CMM path after saving edits.")

        # Verbose
        vb_cb = tk.Checkbutton(
            pane, text="Verbose output", variable=self._verbose_var,
            bg=_CLR["panel"], font=("Arial", 9), activebackground=_CLR["panel"],
        )
        vb_cb.grid(row=8, column=0, sticky=tk.W, pady=(2, 6))

        # --- Open / Close T32 buttons -------------------------------------
        t32_frame = tk.Frame(pane, bg=_CLR["panel"])
        t32_frame.grid(row=9, column=0, sticky=tk.EW, pady=(0, 4))
        tk.Button(
            t32_frame, text="▶ Open T32",
            font=("Arial", 9, "bold"),
            bg="#0056b3", fg="#fff",
            activebackground="#003d80", activeforeground="#fff",
            relief="flat", padx=6, pady=4, cursor="hand2",
            command=self._open_t32,
        ).pack(side=tk.LEFT, padx=(0, 4))
        tk.Button(
            t32_frame, text="✕ Close T32",
            font=("Arial", 9, "bold"),
            bg=_CLR["btn_stop"], fg="#fff",
            activebackground="#c82333", activeforeground="#fff",
            relief="flat", padx=6, pady=4, cursor="hand2",
            command=self._close_t32,
        ).pack(side=tk.LEFT)
        _ToolTip(t32_frame,
                 "Open T32: launch Trace32 using t32_exe_path from config.json.\n"
                 "Close T32: send a quit command; force-kills the process if needed.")

        # --- Run / Stop buttons -------------------------------------------
        sep = ttk.Separator(pane, orient=tk.HORIZONTAL)
        sep.grid(row=10, column=0, sticky=tk.EW, pady=6)

        self._run_btn = tk.Button(
            pane, text="▶  Run",
            font=("Arial", 10, "bold"),
            bg=_CLR["btn_run"], fg="#fff",
            activebackground="#218838", activeforeground="#fff",
            relief="flat", padx=12, pady=6, cursor="hand2",
            command=self._run_selected,
        )
        self._run_btn.grid(row=11, column=0, sticky=tk.EW, pady=2)

        self._stop_btn = tk.Button(
            pane, text="■  Stop",
            font=("Arial", 10, "bold"),
            bg=_CLR["btn_stop"], fg="#fff",
            activebackground="#c82333", activeforeground="#fff",
            relief="flat", padx=12, pady=6, cursor="hand2",
            command=self._stop_run, state=tk.DISABLED,
        )
        self._stop_btn.grid(row=12, column=0, sticky=tk.EW, pady=2)

        self._report_btn = tk.Button(
            pane, text="🌐  Open Report",
            font=("Arial", 9),
            bg=_CLR["btn_open"], fg="#fff",
            activebackground="#003d80", activeforeground="#fff",
            relief="flat", padx=8, pady=5, cursor="hand2",
            command=self._open_last_report, state=tk.DISABLED,
        )
        self._report_btn.grid(row=13, column=0, sticky=tk.EW, pady=(4, 2))

        tk.Button(
            pane, text="↺  Refresh Lists",
            font=("Arial", 9),
            bg=_CLR["btn_clear"], fg="#fff",
            activebackground="#5a6268", activeforeground="#fff",
            relief="flat", padx=8, pady=5, cursor="hand2",
            command=self._refresh_suite_lists,
        ).grid(row=14, column=0, sticky=tk.EW, pady=2)

    def _build_notebook(self, parent: tk.Frame) -> None:
        """Right-hand tabbed area."""
        style = ttk.Style()
        style.configure("TNotebook.Tab", font=("Arial", 9, "bold"), padding=[10, 4])

        nb = ttk.Notebook(parent)
        nb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, pady=6)
        self._nb = nb

        self._build_py_suite_tab(nb)
        self._build_json_tab(nb)
        self._build_discover_tab(nb)
        self._build_config_tab(nb)

    # ── Python suites tab ──────────────────────────────────────────────────

    def _build_py_suite_tab(self, nb: ttk.Notebook) -> None:
        frame = tk.Frame(nb, bg=_CLR["panel"])
        nb.add(frame, text="  Python Suites  ")

        tk.Label(
            frame,
            text="Select a Python test suite to run  (equivalent to: python main.py --suite <name>)",
            font=("Arial", 9), bg=_CLR["panel"], fg="#555",
        ).pack(anchor=tk.W, padx=12, pady=(10, 4))

        list_frame = tk.Frame(frame, bg=_CLR["panel"])
        list_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=4)

        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self._py_listbox = tk.Listbox(
            list_frame, font=("Courier", 10), selectmode=tk.SINGLE,
            yscrollcommand=scrollbar.set, activestyle="dotbox",
            selectbackground="#0056b3", selectforeground="#fff",
            height=10,
        )
        self._py_listbox.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=self._py_listbox.yview)
        self._py_listbox.bind("<Double-1>", lambda _e: self._run_selected())

        # Action buttons row
        py_btn_frame = tk.Frame(frame, bg=_CLR["panel"])
        py_btn_frame.pack(anchor=tk.W, padx=12, pady=(2, 4))
        tk.Button(
            py_btn_frame, text="✏ Edit in IDLE", font=("Arial", 9),
            bg="#17a2b8", fg="#fff", relief="flat", padx=8, pady=4,
            cursor="hand2", command=self._edit_py_in_idle,
        ).pack(side=tk.LEFT, padx=(0, 6))
        tk.Button(
            py_btn_frame, text="↺ Reload List", font=("Arial", 9),
            bg=_CLR["btn_clear"], fg="#fff", relief="flat", padx=8, pady=4,
            cursor="hand2", command=self._refresh_suite_lists,
        ).pack(side=tk.LEFT)
        _ToolTip(py_btn_frame,
                 "Edit in IDLE: open the selected .py suite in Python IDLE "
                 "(falls back to the OS default text editor if IDLE is unavailable).\n"
                 "Reload List: re-scan for Python suite files after saving.")

        # "Run all" checkbox
        self._run_all_py_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            frame, text="Run ALL Python suites (--suite all)",
            variable=self._run_all_py_var,
            bg=_CLR["panel"], font=("Arial", 9), activebackground=_CLR["panel"],
        ).pack(anchor=tk.W, padx=12, pady=(2, 8))

    # ── JSON suites tab ────────────────────────────────────────────────────

    def _build_json_tab(self, nb: ttk.Notebook) -> None:
        frame = tk.Frame(nb, bg=_CLR["panel"])
        nb.add(frame, text="  JSON Suites  ")

        tk.Label(
            frame,
            text="Select a JSON test-case file to run  (equivalent to: python main.py --json <label>)",
            font=("Arial", 9), bg=_CLR["panel"], fg="#555",
        ).pack(anchor=tk.W, padx=12, pady=(10, 4))

        list_frame = tk.Frame(frame, bg=_CLR["panel"])
        list_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=4)

        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self._json_listbox = tk.Listbox(
            list_frame, font=("Courier", 10), selectmode=tk.SINGLE,
            yscrollcommand=scrollbar.set, activestyle="dotbox",
            selectbackground="#0056b3", selectforeground="#fff",
            height=10,
        )
        self._json_listbox.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=self._json_listbox.yview)
        self._json_listbox.bind("<Double-1>", lambda _e: self._run_selected())

        # Action buttons row
        json_btn_frame = tk.Frame(frame, bg=_CLR["panel"])
        json_btn_frame.pack(anchor=tk.W, padx=12, pady=(2, 4))
        tk.Button(
            json_btn_frame, text="✏ Edit in IDLE", font=("Arial", 9),
            bg="#17a2b8", fg="#fff", relief="flat", padx=8, pady=4,
            cursor="hand2", command=self._edit_json_in_idle,
        ).pack(side=tk.LEFT, padx=(0, 6))
        tk.Button(
            json_btn_frame, text="↺ Reload List", font=("Arial", 9),
            bg=_CLR["btn_clear"], fg="#fff", relief="flat", padx=8, pady=4,
            cursor="hand2", command=self._refresh_suite_lists,
        ).pack(side=tk.LEFT)
        _ToolTip(json_btn_frame,
                 "Edit in IDLE: open the selected JSON suite in Python IDLE "
                 "(falls back to the OS default text editor if IDLE is unavailable).\n"
                 "Reload List: re-scan for JSON suite files after saving.")

        note = tk.Label(
            frame,
            text="ℹ️  JSON suites always connect to a live Trace32 instance (--mode is ignored).",
            font=("Arial", 9, "italic"), bg=_CLR["panel"], fg="#888",
        )
        note.pack(anchor=tk.W, padx=12, pady=(0, 4))

        self._run_all_json_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            frame, text="Run ALL JSON suites (--json all)",
            variable=self._run_all_json_var,
            bg=_CLR["panel"], font=("Arial", 9), activebackground=_CLR["panel"],
        ).pack(anchor=tk.W, padx=12, pady=(0, 8))

    # ── Symbol discovery tab ───────────────────────────────────────────────

    def _build_discover_tab(self, nb: ttk.Notebook) -> None:
        frame = tk.Frame(nb, bg=_CLR["panel"])
        nb.add(frame, text="  Symbol Discovery  ")

        info = (
            "Connect to a running Trace32, discover all loaded symbols, and generate\n"
            "a test-case JSON + standalone session script.  Equivalent to:\n"
            "  python main.py --discover --mode live [--module …] [--pattern …] [--breakpoint …]"
        )
        tk.Label(frame, text=info, font=("Arial", 9), bg=_CLR["panel"],
                 fg="#555", justify=tk.LEFT).pack(anchor=tk.W, padx=12, pady=(10, 8))

        grid = tk.Frame(frame, bg=_CLR["panel"])
        grid.pack(fill=tk.X, padx=12)
        grid.columnconfigure(1, weight=1)

        self._disc_pattern_var   = tk.StringVar(value="*")
        self._disc_module_var    = tk.StringVar(value="")
        self._disc_bp_var        = tk.StringVar(value="")
        self._disc_output_var    = tk.StringVar(value="")
        self._disc_suite_var     = tk.StringVar(value="test_symbol_discovery")
        self._disc_max_sym_var   = tk.StringVar(value="500")
        self._disc_resolve_var   = tk.BooleanVar(value=True)
        self._disc_verbose_var   = tk.BooleanVar(value=False)

        fields = [
            ("Symbol Pattern (GLOB):", self._disc_pattern_var,
             "Trace32 SYMBOL.LIST wildcard. Default '*' discovers everything.\n"
             "Example: 'g_*' discovers only global variables."),
            ("Module Filter (substring):", self._disc_module_var,
             "Only include symbols whose source file path contains this string.\n"
             "Example: 'main.c' limits results to symbols in main.c."),
            ("Breakpoint Symbol (verify):", self._disc_bp_var,
             "Set a one-shot breakpoint on this symbol after discovery to verify\n"
             "the function is reachable before writing the output files."),
            ("Suite Name:", self._disc_suite_var,
             "Label used for file names and report titles."),
            ("Max Symbols:", self._disc_max_sym_var,
             "Maximum number of symbols to individually verify (SYMBOL.EXIST).\n"
             "Reduce for faster results; increase for more thorough discovery."),
        ]

        for row, (lbl_text, var, tip) in enumerate(fields):
            lbl = tk.Label(grid, text=lbl_text, bg=_CLR["panel"], font=("Arial", 9),
                           anchor=tk.W)
            lbl.grid(row=row, column=0, sticky=tk.W, pady=3, padx=(0, 8))
            entry = tk.Entry(grid, textvariable=var, font=("Courier", 9))
            entry.grid(row=row, column=1, sticky=tk.EW, pady=3)
            _ToolTip(entry, tip)

        # Output dir row
        r = len(fields)
        tk.Label(grid, text="Output Directory:", bg=_CLR["panel"],
                 font=("Arial", 9), anchor=tk.W).grid(
            row=r, column=0, sticky=tk.W, pady=3, padx=(0, 8))
        out_frame = tk.Frame(grid, bg=_CLR["panel"])
        out_frame.grid(row=r, column=1, sticky=tk.EW, pady=3)
        out_entry = tk.Entry(out_frame, textvariable=self._disc_output_var,
                             font=("Courier", 9))
        out_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Button(out_frame, text="…", font=("Arial", 9), padx=2,
                  command=self._browse_output_dir).pack(side=tk.LEFT, padx=2)
        _ToolTip(out_entry,
                 "Directory where the JSON and session-script artifacts are written.\n"
                 "Defaults to <current_dir>/TestScripts when left empty.")

        # Resolve addresses checkbox
        tk.Checkbutton(
            frame, text="Resolve symbol addresses (SYMBOL.EXIST – slower but more accurate)",
            variable=self._disc_resolve_var,
            bg=_CLR["panel"], font=("Arial", 9), activebackground=_CLR["panel"],
        ).pack(anchor=tk.W, padx=12, pady=(6, 2))

        # Verbose debugging checkbox
        vb_disc_cb = tk.Checkbutton(
            frame, text="Verbose debug output (show raw T32 commands and responses)",
            variable=self._disc_verbose_var,
            bg=_CLR["panel"], font=("Arial", 9), activebackground=_CLR["panel"],
        )
        vb_disc_cb.pack(anchor=tk.W, padx=12, pady=(0, 4))
        _ToolTip(vb_disc_cb,
                 "Enable verbose mode to see every T32 command sent and the raw "
                 "response received.\nUseful when aligning discovery commands with "
                 "the installed Trace32 version so you can diagnose and correct issues.")

        tk.Button(
            frame,
            text="▶  Run Discovery",
            font=("Arial", 10, "bold"),
            bg=_CLR["btn_run"], fg="#fff",
            relief="flat", padx=14, pady=6, cursor="hand2",
            command=self._run_discovery,
        ).pack(anchor=tk.W, padx=12, pady=(4, 8))

    # ── Configuration editor tab ───────────────────────────────────────────

    def _build_config_tab(self, nb: ttk.Notebook) -> None:
        frame = tk.Frame(nb, bg=_CLR["panel"])
        nb.add(frame, text="  Configuration  ")

        tk.Label(
            frame,
            text="Edit config.json settings.  Changes take effect on next test run.",
            font=("Arial", 9), bg=_CLR["panel"], fg="#555",
        ).pack(anchor=tk.W, padx=12, pady=(10, 4))

        btn_frame = tk.Frame(frame, bg=_CLR["panel"])
        btn_frame.pack(anchor=tk.W, padx=12, pady=(0, 4))

        tk.Button(btn_frame, text="Load config.json", font=("Arial", 9),
                  bg="#17a2b8", fg="#fff", relief="flat", padx=8, pady=4,
                  command=self._load_config_json).pack(side=tk.LEFT, padx=(0, 6))
        tk.Button(btn_frame, text="Save config.json", font=("Arial", 9),
                  bg=_CLR["btn_run"], fg="#fff", relief="flat", padx=8, pady=4,
                  command=self._save_config_json).pack(side=tk.LEFT, padx=(0, 6))
        tk.Button(btn_frame, text="Browse…", font=("Arial", 9),
                  bg=_CLR["btn_clear"], fg="#fff", relief="flat", padx=8, pady=4,
                  command=self._browse_config_json).pack(side=tk.LEFT)

        cfg_scroll = tk.Scrollbar(frame)
        cfg_scroll.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 4))

        self._cfg_text = tk.Text(
            frame, font=("Courier", 9), wrap=tk.NONE,
            yscrollcommand=cfg_scroll.set, bg="#fdfdfd",
            relief="solid", borderwidth=1,
        )
        self._cfg_text.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 8))
        cfg_scroll.config(command=self._cfg_text.yview)

        self._config_json_path = _FRAMEWORK_DIR / "config.json"
        self._load_config_json()

    # ── Output log panel ───────────────────────────────────────────────────

    def _build_log_panel(self) -> None:
        log_frame = tk.LabelFrame(
            self, text=" Output Log ",
            font=("Arial", 9, "bold"), bg=_CLR["bg"],
            relief="groove", bd=2,
        )
        log_frame.pack(fill=tk.X, padx=10, pady=(0, 4))

        btn_row = tk.Frame(log_frame, bg=_CLR["bg"])
        btn_row.pack(anchor=tk.W, padx=6, pady=2)

        tk.Button(btn_row, text="Clear", font=("Arial", 8),
                  bg=_CLR["btn_clear"], fg="#fff", relief="flat", padx=6, pady=2,
                  command=self._clear_log).pack(side=tk.LEFT, padx=2)
        tk.Button(btn_row, text="Copy All", font=("Arial", 8),
                  bg="#17a2b8", fg="#fff", relief="flat", padx=6, pady=2,
                  command=self._copy_log).pack(side=tk.LEFT, padx=2)
        tk.Button(btn_row, text="Save Log…", font=("Arial", 8),
                  bg="#6f42c1", fg="#fff", relief="flat", padx=6, pady=2,
                  command=self._save_log).pack(side=tk.LEFT, padx=2)
        tk.Button(btn_row, text="Open Last Report", font=("Arial", 8),
                  bg=_CLR["btn_open"], fg="#fff", relief="flat", padx=6, pady=2,
                  command=self._open_last_report).pack(side=tk.LEFT, padx=10)

        self._log = scrolledtext.ScrolledText(
            log_frame,
            height=10,
            font=("Courier", 9),
            bg=_CLR["log_bg"],
            fg=_CLR["log_fg"],
            insertbackground="#fff",
            state=tk.DISABLED,
            relief="flat",
        )
        self._log.pack(fill=tk.X, padx=6, pady=(0, 6))

        # Colour tags
        tag_colours = {
            "pass":  _CLR["log_pass"],
            "fail":  _CLR["log_fail"],
            "error": _CLR["log_error"],
            "warn":  _CLR["log_warn"],
            "info":  _CLR["log_info"],
            "debug": _CLR["log_debug"],
        }
        for tag, colour in tag_colours.items():
            self._log.tag_config(tag, foreground=colour)

    def _build_status_bar(self) -> None:
        bar = tk.Frame(self, bg=_CLR["header"], height=22)
        bar.pack(fill=tk.X, side=tk.BOTTOM)

        self._status_lbl = tk.Label(
            bar, textvariable=self._status_var,
            font=("Arial", 9), fg="#fff", bg=_CLR["header"], padx=10,
        )
        self._status_lbl.pack(side=tk.LEFT)

    # ------------------------------------------------------------------ data

    def _refresh_suite_lists(self) -> None:
        """Reload Python suite and JSON file lists from disk."""
        # Python suites
        self._py_suites: List[Path] = _discover_python_suites()
        self._py_listbox.delete(0, tk.END)
        for p in self._py_suites:
            self._py_listbox.insert(tk.END, f"  {_suite_label(p):<35}  {p.name}")

        # JSON suites
        self._json_files: List[Path] = _discover_json_files()
        self._json_listbox.delete(0, tk.END)
        for f in self._json_files:
            self._json_listbox.insert(tk.END, f"  {_suite_label(f):<35}  {f.name}")

        self._log_line(
            f"[GUI] Refreshed: {len(self._py_suites)} Python suite(s), "
            f"{len(self._json_files)} JSON file(s) found.",
            "info",
        )

    # ------------------------------------------------------------------ actions

    def _run_selected(self) -> None:
        """Dispatch a run based on the currently active tab."""
        tab_idx = self._nb.index(self._nb.select())
        if tab_idx == 0:
            self._run_py_suite()
        elif tab_idx == 1:
            self._run_json_suite()
        elif tab_idx == 2:
            self._run_discovery()
        else:
            messagebox.showinfo("Info", "Use the buttons on the Configuration tab.")

    def _run_py_suite(self) -> None:
        if self._runner.running:
            messagebox.showwarning("Busy", "A test is already running.")
            return

        run_all = self._run_all_py_var.get()
        if not run_all:
            sel = self._py_listbox.curselection()
            if not sel:
                messagebox.showwarning("No selection", "Please select a Python suite.")
                return
            suite_path = self._py_suites[sel[0]]
        else:
            suite_path = None  # sentinel for "all"

        mode     = self._mode_var.get()
        port     = self._port_var.get()
        al       = self._auto_launch_var.get()
        cmm      = self._cmm_var.get() or None
        verbose  = self._verbose_var.get()

        # Inject port into the shared settings object before running
        self._apply_port(port)

        self._log_line(
            f"\n[GUI] ── Starting Python suite "
            f"{'ALL' if run_all else _suite_label(suite_path)}  "
            f"[mode={mode.upper()}] ──", "info",
        )
        self._runner.run(
            self._do_run_py,
            suite_path=suite_path,
            mode=mode, auto_launch=al, cmm=cmm, verbosity=2 if verbose else 1,
        )

    def _run_json_suite(self) -> None:
        if self._runner.running:
            messagebox.showwarning("Busy", "A test is already running.")
            return

        run_all = self._run_all_json_var.get()
        if not run_all:
            sel = self._json_listbox.curselection()
            if not sel:
                messagebox.showwarning("No selection", "Please select a JSON suite.")
                return
            json_path = self._json_files[sel[0]]
            label = _suite_label(json_path)
        else:
            label = None  # sentinel for "all"

        port = self._port_var.get()
        al   = self._auto_launch_var.get()
        cmm  = self._cmm_var.get() or None
        self._apply_port(port)

        self._log_line(
            f"\n[GUI] ── Starting JSON suite {'ALL' if run_all else label}  "
            "[mode=LIVE, detect-first] ──", "info",
        )
        self._runner.run(
            self._do_run_json,
            label=label, auto_launch=al, cmm=cmm,
        )

    def _run_discovery(self) -> None:
        if self._runner.running:
            messagebox.showwarning("Busy", "A test is already running.")
            return

        port     = self._port_var.get()
        al       = self._auto_launch_var.get()
        cmm      = self._cmm_var.get() or None
        pattern  = self._disc_pattern_var.get() or "*"
        module   = self._disc_module_var.get()
        bp       = self._disc_bp_var.get()
        suite    = self._disc_suite_var.get() or "test_symbol_discovery"
        out_raw  = self._disc_output_var.get()
        resolve  = self._disc_resolve_var.get()
        verbose  = self._disc_verbose_var.get()
        try:
            max_sym = int(self._disc_max_sym_var.get())
        except ValueError:
            max_sym = 500

        out_dir = Path(out_raw) if out_raw else None
        self._apply_port(port)

        self._log_line(
            f"\n[GUI] ── Symbol Discovery  pattern={pattern!r}  "
            f"module={module!r}  verbose={verbose}  ──", "info",
        )
        self._runner.run(
            self._do_run_discover,
            out_dir=out_dir, suite=suite, pattern=pattern,
            module=module, bp=bp, port=int(port), al=al, cmm=cmm,
            resolve=resolve, max_sym=max_sym, verbose=verbose,
        )

    def _stop_run(self) -> None:
        if self._runner.running:
            self._runner.stop()
            self._log_line("[GUI] Stop requested – waiting for current step to finish …",
                           "warn")

    # ------------------------------------------------------------------ worker fns
    # These run inside the background thread; they use main.py helpers directly.

    @staticmethod
    def _do_run_py(
        suite_path: Optional[Path],
        mode: str,
        auto_launch: bool,
        cmm: Optional[str],
        verbosity: int,
        stop_event: threading.Event,
    ) -> None:
        """Worker: run one or all Python suites."""
        if suite_path is None:
            _run_all_python_suites(
                mode=mode, auto_launch=auto_launch, cmm_script=cmm,
                verbosity=verbosity,
            )
        else:
            _run_python_suite(
                suite_path, mode=mode, auto_launch=auto_launch,
                cmm_script=cmm, verbosity=verbosity,
            )

    @staticmethod
    def _do_run_json(
        label: Optional[str],
        auto_launch: bool,
        cmm: Optional[str],
        stop_event: threading.Event,
    ) -> None:
        """Worker: run one or all JSON suites."""
        if label is None:
            _run_all_json_suites(auto_launch=auto_launch, cmm_script=cmm)
        else:
            _run_json_suite(label, auto_launch=auto_launch, cmm_script=cmm)

    @staticmethod
    def _do_run_discover(
        out_dir: Optional[Path],
        suite: str,
        pattern: str,
        module: str,
        bp: str,
        port: int,
        al: bool,
        cmm: Optional[str],
        resolve: bool,
        max_sym: int,
        verbose: bool,
        stop_event: threading.Event,
    ) -> None:
        """Worker: symbol discovery."""
        _run_discover(
            output_dir=out_dir,
            suite_name=suite,
            pattern=pattern,
            module_filter=module,
            breakpoint_symbol=bp,
            port=port,
            auto_launch=al,
            cmm_script=cmm,
            resolve_addresses=resolve,
            max_symbols=max_sym,
            verbose=verbose,
        )

    # ------------------------------------------------------------------ config

    def _apply_port(self, port_str: str) -> None:
        """Push the GUI port value into the shared settings singleton."""
        try:
            from GM_VIP_Automation_Framework.config import settings
            settings.rcl_port = int(port_str)
        except Exception:
            pass

    def _load_config_json(self) -> None:
        path = self._config_json_path
        if path.is_file():
            text = path.read_text(encoding="utf-8")
        else:
            text = json.dumps({"rcl_port": 20000}, indent=2)
        self._cfg_text.config(state=tk.NORMAL)
        self._cfg_text.delete("1.0", tk.END)
        self._cfg_text.insert(tk.END, text)
        self._cfg_text.config(state=tk.NORMAL)
        self._log_line(f"[GUI] Loaded {path}", "info")

    def _save_config_json(self) -> None:
        text = self._cfg_text.get("1.0", tk.END).strip()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            messagebox.showerror("JSON Error",
                                 f"Cannot save – invalid JSON:\n{exc}")
            return
        self._config_json_path.write_text(
            json.dumps(parsed, indent=2), encoding="utf-8"
        )
        # Reload framework settings
        try:
            from GM_VIP_Automation_Framework.config import settings
            settings.load_from_json(str(self._config_json_path))
        except Exception:
            pass
        self._log_line(f"[GUI] Saved {self._config_json_path}", "pass")
        messagebox.showinfo("Saved", f"config.json saved to:\n{self._config_json_path}")

    def _browse_config_json(self) -> None:
        path = filedialog.askopenfilename(
            title="Select config.json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialdir=str(_FRAMEWORK_DIR),
        )
        if path:
            self._config_json_path = Path(path)
            self._load_config_json()

    # ------------------------------------------------------------------ log

    def _log_line(self, text: str, tag: str = "debug") -> None:
        """Append *text* to the log widget (call from main thread only)."""
        if not hasattr(self, "_log"):
            return  # log panel not yet built; silently skip early calls
        self._log.config(state=tk.NORMAL)
        ts = time.strftime("%H:%M:%S")
        self._log.insert(tk.END, f"[{ts}] {text}\n", tag)
        self._log.see(tk.END)
        self._log.config(state=tk.DISABLED)

    def _clear_log(self) -> None:
        self._log.config(state=tk.NORMAL)
        self._log.delete("1.0", tk.END)
        self._log.config(state=tk.DISABLED)

    def _copy_log(self) -> None:
        text = self._log.get("1.0", tk.END)
        self.clipboard_clear()
        self.clipboard_append(text)
        self._status_var.set("Log copied to clipboard")
        self.after(2000, lambda: self._status_var.set("Ready"))

    def _save_log(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Save log as…",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialfile=f"gm_vip_log_{time.strftime('%Y%m%d_%H%M%S')}.txt",
        )
        if path:
            text = self._log.get("1.0", tk.END)
            Path(path).write_text(text, encoding="utf-8")
            self._log_line(f"[GUI] Log saved to {path}", "info")

    # ------------------------------------------------------------------ reports

    def _open_last_report(self) -> None:
        """Open the most recent HTML report in the default browser."""
        if self._last_report_path and self._last_report_path.is_file():
            webbrowser.open(self._last_report_path.as_uri())
            return

        # Fall back: scan Test_Report/ for the newest report
        report_root = _FRAMEWORK_DIR / "Test_Report"
        if not report_root.exists():
            messagebox.showinfo("No Report", "No HTML report found yet.\nRun a test suite first.")
            return

        reports = sorted(report_root.rglob("*.html"), key=lambda p: p.stat().st_mtime)
        if not reports:
            messagebox.showinfo("No Report", "No HTML report found yet.\nRun a test suite first.")
            return

        latest = reports[-1]
        self._last_report_path = latest
        webbrowser.open(latest.as_uri())

    def _open_report_dialog(self) -> None:
        path = filedialog.askopenfilename(
            title="Open HTML Report",
            filetypes=[("HTML files", "*.html"), ("All files", "*.*")],
            initialdir=str(_FRAMEWORK_DIR / "Test_Report"),
        )
        if path:
            webbrowser.open(Path(path).as_uri())

    def _open_readme(self) -> None:
        readme = _FRAMEWORK_DIR / "README.md"
        if readme.is_file():
            webbrowser.open(readme.as_uri())
        else:
            messagebox.showinfo("README", f"README not found at:\n{readme}")

    # ------------------------------------------------------------------ browse

    def _browse_cmm(self) -> None:
        path = filedialog.askopenfilename(
            title="Select CMM startup script",
            filetypes=[("CMM scripts", "*.cmm"), ("All files", "*.*")],
        )
        if path:
            self._cmm_var.set(path)

    def _browse_output_dir(self) -> None:
        path = filedialog.askdirectory(title="Select output directory")
        if path:
            self._disc_output_var.set(path)

    # ------------------------------------------------------------------ T32 open/close

    def _open_t32(self) -> None:
        """Launch Trace32 using the exe path from config.json / settings."""
        from GM_VIP_Automation_Framework.config import settings
        from GM_VIP_Automation_Framework.core.connection import T32Connection
        from GM_VIP_Automation_Framework.utils.exceptions import T32LaunchError

        exe = settings.t32_exe_path or ""
        if not exe or not Path(exe).is_file():
            messagebox.showerror(
                "Cannot Open T32",
                f"Trace32 executable not found:\n  {exe or '(not set)'}\n\n"
                "Set 't32_exe_path' in the Configuration tab and save config.json first.",
            )
            return

        cmm = self._cmm_var.get() or None
        try:
            conn = T32Connection(
                exe_path=exe,
                config_path=settings.t32_config_path,
                cmm_entry_script=cmm,
            )
            proc = conn.launch()
            self._t32_process = proc
            self._log_line(
                f"[GUI] Trace32 launched  PID={proc.pid}  exe={exe}", "info",
            )
        except T32LaunchError as exc:
            messagebox.showerror("T32 Launch Error", str(exc))
        except Exception as exc:
            messagebox.showerror("T32 Launch Error", f"Unexpected error:\n{exc}")

    def _close_t32(self) -> None:
        """Close Trace32: graceful quit via RCL, then force-kill if needed."""
        from GM_VIP_Automation_Framework.core.connection import T32Connection

        port = self._port_var.get()
        graceful_ok = False

        # Attempt graceful quit via RCL QUIT command
        try:
            conn = T32Connection(port=int(port))
            if conn.try_connect():
                try:
                    conn.cmd("QUIT")
                    self._log_line("[GUI] Sent QUIT command to Trace32 via RCL.", "info")
                finally:
                    conn.disconnect()
                # Schedule the rest of the shutdown after the wait so the UI stays responsive
                self.after(int(_T32_QUIT_WAIT_S * 1000), self._finish_close_t32)
                graceful_ok = True
            else:
                self._finish_close_t32(graceful_ok=False)
        except Exception as exc:
            self._log_line(f"[GUI] Graceful QUIT failed: {exc}", "warn")
            self._finish_close_t32(graceful_ok=False)

    def _finish_close_t32(self, graceful_ok: bool = True) -> None:
        """Complete T32 shutdown: kill managed process or fall back to name-based kill."""
        from GM_VIP_Automation_Framework.core.connection import T32Connection

        port = self._port_var.get()

        # Kill the process we launched (if any) and it is still alive
        proc: Optional[subprocess.Popen] = getattr(self, "_t32_process", None)
        if proc is not None and proc.poll() is None:
            if not graceful_ok:
                self._log_line(
                    f"[GUI] Force-killing Trace32 PID={proc.pid} …", "warn",
                )
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                try:
                    proc.kill()
                    proc.wait(timeout=3)
                except Exception as exc2:
                    self._log_line(f"[GUI] Kill failed: {exc2}", "error")
            finally:
                self._t32_process = None
            self._log_line("[GUI] Trace32 process stopped.", "info")
            return

        # No managed process – only attempt name-based kill when graceful shutdown failed
        if graceful_ok:
            self._log_line("[GUI] Trace32 exited gracefully.", "info")
            return

        # Re-probe the RCL port to confirm Trace32 is still reachable before killing by name
        still_running = False
        try:
            probe = T32Connection(port=int(port))
            if probe.try_connect():
                still_running = True
                probe.disconnect()
        except Exception:
            still_running = False

        if still_running:
            killed = self._kill_t32_by_name()
            if not killed:
                messagebox.showinfo(
                    "Close T32",
                    "No Trace32 process was found to close.\n"
                    "It may have already exited, or was started externally.",
                )
        else:
            messagebox.showinfo(
                "Close T32",
                "No Trace32 process was found to close.\n"
                "It may have already exited, or was started externally.",
            )

    def _kill_t32_by_name(self) -> bool:
        """Find and kill Trace32 processes by executable name. Returns True if any killed."""
        from GM_VIP_Automation_Framework.config import settings

        configured_names = {n.lower() for n in (settings.t32_exe_names or [])}
        t32_names = configured_names | _T32_FALLBACK_EXE_NAMES
        killed = False
        system = platform.system().lower()

        if system == "windows":
            for name in t32_names:
                try:
                    result = subprocess.run(
                        ["taskkill", "/F", "/IM", name],
                        capture_output=True, check=False,
                    )
                    if result.returncode == 0:
                        killed = True
                        self._log_line(f"[GUI] taskkill /F /IM {name}", "warn")
                except Exception:
                    pass
        else:
            for name in t32_names:
                try:
                    result = subprocess.run(
                        ["pkill", "-f", name],
                        capture_output=True, check=False,
                    )
                    if result.returncode == 0:
                        killed = True
                        self._log_line(f"[GUI] pkill -f {name}", "warn")
                except Exception:
                    pass
        return killed

    # ------------------------------------------------------------------ CMM editor

    def _edit_cmm_in_editor(self) -> None:
        """Open the CMM script in a text editor (IDLE preferred)."""
        path_str = self._cmm_var.get().strip()
        if not path_str:
            messagebox.showwarning(
                "No CMM Script",
                "No CMM script path is set.\nBrowse for a .cmm file first.",
            )
            return
        path = Path(path_str)
        if not path.is_file():
            messagebox.showerror(
                "File Not Found",
                f"CMM script not found:\n{path}",
            )
            return
        self._open_in_editor(path)

    def _reload_cmm(self) -> None:
        """Re-confirm the CMM path is valid and log it (useful after external edits)."""
        path_str = self._cmm_var.get().strip()
        if not path_str:
            self._log_line("[GUI] CMM path is empty – nothing to reload.", "warn")
            return
        path = Path(path_str)
        if path.is_file():
            self._log_line(
                f"[GUI] CMM script ready: {path}  "
                f"({path.stat().st_size} bytes, modified {time.strftime('%H:%M:%S', time.localtime(path.stat().st_mtime))})",
                "info",
            )
        else:
            self._log_line(f"[GUI] CMM script not found: {path}", "error")

    # ------------------------------------------------------------------ IDLE / editor helpers

    def _edit_py_in_idle(self) -> None:
        """Open the selected Python suite in IDLE (or fallback editor)."""
        sel = self._py_listbox.curselection()
        if not sel:
            messagebox.showwarning("No Selection", "Please select a Python suite first.")
            return
        path = self._py_suites[sel[0]]
        self._open_in_editor(path)

    def _edit_json_in_idle(self) -> None:
        """Open the selected JSON suite in IDLE (or fallback editor)."""
        sel = self._json_listbox.curselection()
        if not sel:
            messagebox.showwarning("No Selection", "Please select a JSON suite first.")
            return
        path = self._json_files[sel[0]]
        self._open_in_editor(path)

    def _open_in_editor(self, path: Path) -> None:
        """Open *path* in Python IDLE; fall back to OS default text editor."""
        # Try IDLE first (works for .py and can display .json / .cmm as text)
        try:
            subprocess.Popen(
                [sys.executable, "-m", "idlelib", str(path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._log_line(f"[GUI] Opened in IDLE: {path}", "info")
            return
        except Exception as exc:
            self._log_line(f"[GUI] IDLE not available ({exc}); trying OS editor …", "debug")

        # OS-specific fallback
        system = platform.system().lower()
        try:
            if system == "windows":
                os.startfile(str(path))
            elif system == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
            self._log_line(f"[GUI] Opened in OS editor: {path}", "info")
        except Exception as exc:
            messagebox.showerror(
                "Cannot Open File",
                f"Failed to open file in editor:\n{path}\n\nError: {exc}",
            )

    # ------------------------------------------------------------------ queue poll

    def _poll_queue(self) -> None:
        """Drain the inter-thread queue and update the GUI (runs in main thread)."""
        try:
            while True:
                msg = self._q.get_nowait()
                if msg[0] == "log":
                    _, text, tag = msg
                    self._log_line(text, tag)
                elif msg[0] == "status":
                    state = msg[1]
                    self._on_status_change(state)
        except queue.Empty:
            pass
        self.after(self._POLL_MS, self._poll_queue)

    def _on_status_change(self, state: str) -> None:
        if state == "running":
            self._run_btn.config(state=tk.DISABLED)
            self._stop_btn.config(state=tk.NORMAL)
            self._report_btn.config(state=tk.DISABLED)
            self._status_var.set("⏳ Running …")
            self._spin()
        elif state == "idle":
            self._run_btn.config(state=tk.NORMAL)
            self._stop_btn.config(state=tk.DISABLED)
            self._status_var.set("✅ Done")
            self._enable_report_btn()

    def _spin(self) -> None:
        """Simple text spinner in the status bar while a test runs."""
        if not self._runner.running:
            return
        frames = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")
        self._anim_idx = (self._anim_idx + 1) % len(frames)
        self._status_var.set(f"{frames[self._anim_idx]} Running …")
        self.after(120, self._spin)

    def _enable_report_btn(self) -> None:
        """Enable the 'Open Report' button if a new HTML report exists."""
        report_root = _FRAMEWORK_DIR / "Test_Report"
        if not report_root.exists():
            return
        reports = sorted(report_root.rglob("*.html"), key=lambda p: p.stat().st_mtime)
        if reports:
            self._last_report_path = reports[-1]
            self._report_btn.config(state=tk.NORMAL)

    # ------------------------------------------------------------------ about

    def _show_about(self) -> None:
        messagebox.showinfo(
            "About GM VIP Automation Framework GUI",
            "GM VIP Automation Framework\n"
            "Graphical User Interface\n\n"
            "Brings all command-line features of main.py into a\n"
            "tester-friendly point-and-click interface.\n\n"
            "Features:\n"
            "  • Run Python test suites (mock or live)\n"
            "  • Run JSON-driven test cases\n"
            "  • Discover Trace32 symbols\n"
            "  • Edit config.json settings\n"
            "  • Real-time colour-coded output log\n"
            "  • Stop long-running tests at any time\n"
            "  • Open HTML reports in the browser\n\n"
            "Trace32 is a product of Lauterbach GmbH.\n"
            "MAGNA is a registered trademark of Magna International.",
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Launch the GUI application."""
    app = GMVIPGui()
    app.mainloop()


if __name__ == "__main__":
    main()
