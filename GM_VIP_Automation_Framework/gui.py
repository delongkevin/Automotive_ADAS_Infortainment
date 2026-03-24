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

import datetime
import importlib.util
import io
import json
import os
import platform
import queue
import re
import subprocess
import sys
import threading
import time
import traceback
import unittest
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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
    "btn_new":    "#6f42c1",   # purple – create/new actions
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
_T32_QUIT_WAIT_S = 5

# Persistent GUI state file (saves all inputs across sessions).
_GUI_STATE_PATH = _FRAMEWORK_DIR / "gui_state.json"

# Interval in seconds between automatic T32 connection probes.
_T32_MONITOR_INTERVAL_S = 3

# Seconds of continuous T32 detection failure before showing a retry dialog.
_T32_DETECT_WARN_S = 30

# Common Trace32 executable names used as a fallback when the setting is empty.
_T32_FALLBACK_EXE_NAMES = frozenset({
    "t32marm.exe", "t32marm64.exe", "t32mppc.exe",
    "t32marm",     "t32marm64",     "t32mppc",
})

# C keyword / type names excluded from symbol extraction results.
_C_KEYWORDS: frozenset = frozenset({
    'if', 'else', 'for', 'while', 'do', 'switch', 'case', 'break',
    'continue', 'return', 'goto', 'sizeof', 'typedef', 'struct',
    'union', 'enum', 'void', 'int', 'char', 'float', 'double',
    'short', 'long', 'unsigned', 'signed', 'const', 'static',
    'extern', 'volatile', 'auto', 'register', 'inline',
    'NULL', 'true', 'false', 'uint8_t', 'uint16_t', 'uint32_t',
    'int8_t', 'int16_t', 'int32_t', 'bool',
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
        self.geometry("1100x780")
        self.minsize(900, 620)
        self.configure(bg=_CLR["bg"])

        # Shared state
        self._q: "queue.Queue[tuple]" = queue.Queue()
        self._runner = _TestRunner(self._q)
        self._last_report_path: Optional[Path] = None
        self._t32_process: Optional[subprocess.Popen] = None
        self._t32_wait_thread: Optional[threading.Thread] = None
        self._t32_monitor_thread: Optional[threading.Thread] = None
        self._t32_connected: bool = False
        self._t32_monitor_stop = threading.Event()
        # Thread-safe copy of the RCL port for the monitor thread (plain int,
        # updated on the main thread whenever the Entry widget changes or state loads).
        self._monitor_port: int = 20000
        # Thread-safe copy of the configured RCL packlen for the monitor/wait threads.
        # Updated from settings when a port change is applied.
        self._monitor_packlen: int = 1024
        # Thread-safe mode copy for the monitor thread (plain str).
        self._monitor_mode: str = "mock"
        # Whether the 30-second timeout warning was already sent in this failure cycle.
        self._t32_warn_sent: bool = False
        # Signalled by the UI when the user clicks "Retry Now" or switches modes,
        # so the monitor thread resets its failure-streak start time immediately.
        self._t32_fail_reset = threading.Event()

        # Symbol Discovery queue: list of dicts with all SD parameters
        self._disc_queue: List[Dict[str, Any]] = []

        # Registered C source files (for the C Source Files tab)
        self._c_files: List[Path] = []

        # --- tkinter variables (must live on self so GC keeps them) ---------
        self._mode_var        = tk.StringVar(value="mock")
        self._port_var        = tk.StringVar(value="20000")
        self._auto_launch_var = tk.BooleanVar(value=False)
        self._cmm_var         = tk.StringVar(value="")
        self._verbose_var     = tk.BooleanVar(value=False)
        self._status_var      = tk.StringVar(value="Ready")
        self._anim_idx        = 0

        # Keep _monitor_port in sync whenever the port Entry is edited.
        self._port_var.trace_add("write", self._on_port_var_changed)
        # Keep _monitor_mode in sync whenever the mode radio changes.
        self._mode_var.trace_add("write", self._on_mode_var_changed)

        # Test Creator variables
        self._tc_py_name_var   = tk.StringVar(value="")
        self._tc_json_name_var = tk.StringVar(value="")
        self._tc_py_dir_var    = tk.StringVar(value="")
        self._tc_json_dir_var  = tk.StringVar(value="")

        self._build_ui()
        self._refresh_suite_lists()
        self._load_gui_state()
        self._poll_queue()
        self._start_t32_monitor()

        # Save state when the window is closed
        self.protocol("WM_DELETE_WINDOW", self._on_close)

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
        file_menu.add_command(label="Browse All Reports",   command=lambda: self._nb.select(5))
        file_menu.add_separator()
        file_menu.add_command(label="Save GUI State",       command=self._save_gui_state)
        file_menu.add_separator()
        file_menu.add_command(label="Exit",                 command=self._on_close)
        bar.add_cascade(label="File", menu=file_menu)

        run_menu = tk.Menu(bar, tearoff=0)
        run_menu.add_command(label="Run Selected",  command=self._run_selected)
        run_menu.add_command(label="Stop",          command=self._stop_run)
        run_menu.add_separator()
        run_menu.add_command(label="Open Last Report in Browser", command=self._open_last_report)
        bar.add_cascade(label="Run", menu=run_menu)

        tools_menu = tk.Menu(bar, tearoff=0)
        tools_menu.add_command(label="Test Creator",         command=lambda: self._nb.select(4))
        tools_menu.add_command(label="Symbol Discovery",     command=lambda: self._nb.select(2))
        tools_menu.add_command(label="Configuration",        command=lambda: self._nb.select(3))
        tools_menu.add_command(label="C Source Files",       command=lambda: self._nb.select(6))
        bar.add_cascade(label="Tools", menu=tools_menu)

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

        self._build_py_suite_tab(nb)     # tab 0
        self._build_json_tab(nb)         # tab 1
        self._build_discover_tab(nb)     # tab 2
        self._build_config_tab(nb)       # tab 3
        self._build_test_creator_tab(nb) # tab 4
        self._build_reports_tab(nb)      # tab 5
        self._build_c_files_tab(nb)      # tab 6

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
        ).pack(side=tk.LEFT, padx=(0, 6))
        tk.Button(
            py_btn_frame, text="＋ New Suite", font=("Arial", 9),
            bg=_CLR["btn_new"], fg="#fff", relief="flat", padx=8, pady=4,
            cursor="hand2", command=lambda: self._nb.select(4),
        ).pack(side=tk.LEFT)
        _ToolTip(py_btn_frame,
                 "Edit in IDLE: open the selected .py suite in Python IDLE "
                 "(falls back to the OS default text editor if IDLE is unavailable).\n"
                 "Reload List: re-scan for Python suite files after saving.\n"
                 "New Suite: open the Test Creator tab to create a new Python suite.")

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
        ).pack(side=tk.LEFT, padx=(0, 6))
        tk.Button(
            json_btn_frame, text="＋ New Suite", font=("Arial", 9),
            bg=_CLR["btn_new"], fg="#fff", relief="flat", padx=8, pady=4,
            cursor="hand2", command=lambda: self._nb.select(4),
        ).pack(side=tk.LEFT)
        _ToolTip(json_btn_frame,
                 "Edit in IDLE: open the selected JSON suite in Python IDLE "
                 "(falls back to the OS default text editor if IDLE is unavailable).\n"
                 "Reload List: re-scan for JSON suite files after saving.\n"
                 "New Suite: open the Test Creator tab to create a new JSON suite.")

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
        ).pack(anchor=tk.W, padx=12, pady=(4, 4))

        # ── Symbol Discovery Queue ─────────────────────────────────────────
        sep = ttk.Separator(frame, orient=tk.HORIZONTAL)
        sep.pack(fill=tk.X, padx=12, pady=(4, 6))

        tk.Label(frame, text="Discovery Queue  (save configs and run them as suites)",
                 font=("Arial", 9, "bold"), bg=_CLR["panel"], fg=_CLR["header"],
                 ).pack(anchor=tk.W, padx=12)

        queue_frame = tk.Frame(frame, bg=_CLR["panel"])
        queue_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=(4, 4))

        q_list_frame = tk.Frame(queue_frame, bg=_CLR["panel"])
        q_list_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        q_scrollbar = tk.Scrollbar(q_list_frame)
        q_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self._disc_queue_listbox = tk.Listbox(
            q_list_frame, font=("Courier", 9), selectmode=tk.SINGLE,
            yscrollcommand=q_scrollbar.set, activestyle="dotbox",
            selectbackground="#0056b3", selectforeground="#fff",
            height=5,
        )
        self._disc_queue_listbox.pack(fill=tk.BOTH, expand=True)
        q_scrollbar.config(command=self._disc_queue_listbox.yview)

        q_btn_frame = tk.Frame(queue_frame, bg=_CLR["panel"])
        q_btn_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(8, 0))

        for lbl, cmd, bg in (
            ("＋ Add Current",       self._add_to_disc_queue,   "#28a745"),
            ("✕ Remove Selected",   self._remove_from_disc_queue, "#dc3545"),
            ("🗑 Clear All",          self._clear_disc_queue,    "#6c757d"),
            ("▶ Run as Python",     self._run_queue_as_python,  "#0056b3"),
            ("▶ Run as JSON",       self._run_queue_as_json,    "#17a2b8"),
        ):
            tk.Button(
                q_btn_frame, text=lbl, font=("Arial", 8),
                bg=bg, fg="#fff", relief="flat", padx=6, pady=3,
                cursor="hand2", command=cmd,
                width=18,
            ).pack(anchor=tk.W, pady=2)

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
                  bg=_CLR["btn_new"], fg="#fff", relief="flat", padx=6, pady=2,
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
        bar = tk.Frame(self, bg=_CLR["header"], height=26)
        bar.pack(fill=tk.X, side=tk.BOTTOM)

        # T32 connection LED (left side)
        t32_led_frame = tk.Frame(bar, bg=_CLR["header"])
        t32_led_frame.pack(side=tk.LEFT, padx=(8, 0))
        self._t32_led_canvas = tk.Canvas(
            t32_led_frame, width=14, height=14,
            bg=_CLR["header"], highlightthickness=0,
        )
        self._t32_led_canvas.pack(side=tk.LEFT, pady=6)
        self._t32_led_oval = self._t32_led_canvas.create_oval(
            2, 2, 12, 12, fill="#cc0000", outline="#880000",
        )
        tk.Label(
            t32_led_frame, text=" T32", font=("Arial", 8),
            fg="#ccc", bg=_CLR["header"],
        ).pack(side=tk.LEFT)

        # Test-running LED (second indicator)
        run_led_frame = tk.Frame(bar, bg=_CLR["header"])
        run_led_frame.pack(side=tk.LEFT, padx=(10, 0))
        self._run_led_canvas = tk.Canvas(
            run_led_frame, width=14, height=14,
            bg=_CLR["header"], highlightthickness=0,
        )
        self._run_led_canvas.pack(side=tk.LEFT, pady=6)
        self._run_led_oval = self._run_led_canvas.create_oval(
            2, 2, 12, 12, fill="#555555", outline="#333333",
        )
        tk.Label(
            run_led_frame, text=" Test", font=("Arial", 8),
            fg="#ccc", bg=_CLR["header"],
        ).pack(side=tk.LEFT)

        # Status text
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

    def _on_port_var_changed(self, *_args) -> None:
        """Keep ``_monitor_port`` in sync whenever the port Entry is edited (main thread)."""
        try:
            self._monitor_port = int(self._port_var.get())
        except ValueError:
            pass  # Leave the previous valid port in place while the user is typing

    def _on_mode_var_changed(self, *_args) -> None:
        """Keep ``_monitor_mode`` in sync whenever the mode radio changes (main thread).

        Also signals the monitor thread to restart its 30-second failure-streak
        timer so that switching to live mode starts a fresh detection cycle.
        """
        try:
            self._monitor_mode = self._mode_var.get()
            self._t32_warn_sent = False
            self._t32_fail_reset.set()
        except tk.TclError as exc:
            # Tkinter raises TclError when the underlying Tcl variable is destroyed
            # during shutdown.  Route through the log panel so it is visible.
            self._log_line(
                f"[GUI] Failed to update monitor mode: {exc}\n{traceback.format_exc()}",
                "error",
            )

    def _apply_port(self, port_str: str) -> None:
        """Push the GUI port value into the shared settings singleton."""
        try:
            port_int = int(port_str)
            from GM_VIP_Automation_Framework.config import settings
            settings.rcl_port = port_int
            self._monitor_port = port_int
            self._monitor_packlen = settings.rcl_packlen
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
        """Launch Trace32, or detect an already-running instance.

        Detection order
        ---------------
        1. Probe the configured RCL port.  If Trace32 is already listening,
           log the fact and return – no second instance is started.
        2. If a process launched by this session is still alive (but the port
           hasn't opened yet), skip the launch and just wait for the port.
        3. Otherwise validate the exe path, start the process, then poll the
           port in a background thread so the UI remains responsive.  The log
           panel will show "[GUI] Trace32 ready on port …" when the API
           connection becomes available.
        """
        from GM_VIP_Automation_Framework.config import settings
        from GM_VIP_Automation_Framework.core.connection import T32Connection
        from GM_VIP_Automation_Framework.utils.exceptions import T32LaunchError

        port_str = self._port_var.get()
        try:
            port = int(port_str)
        except ValueError:
            port = settings.rcl_port

        # ── Step 1: check whether T32 is already listening on the RCL port ──
        probe = T32Connection(port=port)
        if probe.try_connect():
            probe.disconnect()
            self._log_line(
                f"[GUI] Trace32 is already running on port {port} – no launch needed.",
                "info",
            )
            return

        # ── Step 2: managed process still starting up? ────────────────────
        proc: Optional[subprocess.Popen] = self._t32_process
        if proc is not None and proc.poll() is None:
            # Avoid spawning a new wait thread if one is already alive.
            if self._t32_wait_thread is not None and self._t32_wait_thread.is_alive():
                self._log_line(
                    f"[GUI] Trace32 (PID={proc.pid}) is still starting up – "
                    f"already waiting for RCL port {port} to open …",
                    "info",
                )
                return
            self._log_line(
                f"[GUI] Trace32 (PID={proc.pid}) is still starting up – "
                f"waiting for RCL port {port} to open …",
                "info",
            )
            self._t32_wait_thread = threading.Thread(
                target=self._wait_for_t32_port,
                args=(port, settings.connect_max_wait_s),
                daemon=True,
            )
            self._t32_wait_thread.start()
            return

        # ── Step 3: validate the exe path ─────────────────────────────────
        exe = settings.t32_exe_path or ""
        if not exe or not Path(exe).is_file():
            messagebox.showerror(
                "Cannot Open T32",
                f"Trace32 executable not found:\n  {exe or '(not set)'}\n\n"
                "Set 't32_exe_path' in the Configuration tab and save config.json first.",
            )
            return

        # ── Step 4: launch T32 ────────────────────────────────────────────
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
            return
        except Exception as exc:
            messagebox.showerror("T32 Launch Error", f"Unexpected error:\n{exc}")
            return

        # ── Step 5: poll the RCL port in a background thread ──────────────
        max_wait = settings.connect_max_wait_s
        self._log_line(
            f"[GUI] Waiting up to {max_wait:.0f}s for Trace32 RCL port {port} to open …",
            "info",
        )
        self._t32_wait_thread = threading.Thread(
            target=self._wait_for_t32_port,
            args=(port, max_wait),
            daemon=True,
        )
        self._t32_wait_thread.start()

    def _wait_for_t32_port(self, port: int, max_wait_s: float) -> None:
        """Poll the RCL port until Trace32 is accepting connections or timeout.

        Runs in a daemon background thread so the UI stays responsive.
        Status messages are posted to the queue and appear in the log panel.
        """
        from GM_VIP_Automation_Framework.core.connection import T32Connection

        deadline = time.monotonic() + max_wait_s
        while time.monotonic() < deadline:
            probe = T32Connection(port=port)
            if probe.try_connect():
                probe.disconnect()
                self._q.put((
                    "log",
                    f"[GUI] ✔ Trace32 ready on port {port}. You can now run tests.",
                    "pass",
                ))
                return
            time.sleep(1.0)

        self._q.put((
            "log",
            (
                f"[GUI] ⚠ Trace32 did not open port {port} within "
                f"{max_wait_s:.0f}s.\n"
                "       Troubleshooting checklist:\n"
                f"       1. Verify config.t32 contains:  RCL=NETASSIST / PORT={port} / PACKLEN={self._monitor_packlen}\n"
                "       2. Confirm Trace32 has permission to bind the network port "
                "(try running as Administrator on Windows).\n"
                "       3. Check that no firewall or antivirus is blocking the RCL port.\n"
                "       4. If Trace32 is already running, click 'Open T32' so the GUI can "
                "attach to the existing instance rather than launching a second one."
            ),
            "warn",
        ))

    def _close_t32(self) -> None:
        """Close Trace32: graceful quit via RCL, then countdown + force-kill if needed."""
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
        """Complete T32 shutdown: countdown-kill managed process or fall back to name-based kill."""
        from GM_VIP_Automation_Framework.core.connection import T32Connection

        port = self._port_var.get()

        # Kill the process we launched (if any) and it is still alive
        proc: Optional[subprocess.Popen] = getattr(self, "_t32_process", None)
        if proc is not None and proc.poll() is None:
            if not graceful_ok:
                self._log_line(
                    f"[GUI] Trace32 (PID={proc.pid}) did not exit; starting countdown …", "warn",
                )
                self._countdown_kill_t32(proc)
            else:
                # Gave it _T32_QUIT_WAIT_S already – if still alive, countdown
                if proc.poll() is None:
                    self._log_line(
                        f"[GUI] Trace32 (PID={proc.pid}) still alive after {_T32_QUIT_WAIT_S}s; "
                        "starting countdown …", "warn",
                    )
                    self._countdown_kill_t32(proc)
                else:
                    self._t32_process = None
                    self._log_line("[GUI] Trace32 exited gracefully.", "info")
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
            self._countdown_kill_t32(None)
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
                elif msg[0] == "t32_status":
                    connected = msg[1]
                    self._update_t32_led(connected)
                elif msg[0] == "t32_timeout_warn":
                    port = msg[1]
                    self._show_t32_timeout_dialog(port)
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
            # Orange LED = test running
            if hasattr(self, "_run_led_canvas"):
                self._run_led_canvas.itemconfig(
                    self._run_led_oval, fill="#ff8c00", outline="#cc6600",
                )
        elif state == "idle":
            self._run_btn.config(state=tk.NORMAL)
            self._stop_btn.config(state=tk.DISABLED)
            self._status_var.set("✅ Done")
            self._enable_report_btn()
            # Grey LED = idle
            if hasattr(self, "_run_led_canvas"):
                self._run_led_canvas.itemconfig(
                    self._run_led_oval, fill="#555555", outline="#333333",
                )

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

    # ── Test Creator tab ────────────────────────────────────────────────────

    def _build_test_creator_tab(self, nb: ttk.Notebook) -> None:
        """Tab for creating new Python and JSON test suites from templates."""
        frame = tk.Frame(nb, bg=_CLR["panel"])
        nb.add(frame, text="  Test Creator  ")

        tk.Label(
            frame,
            text="Create new test suites from built-in templates.",
            font=("Arial", 9), bg=_CLR["panel"], fg="#555",
        ).pack(anchor=tk.W, padx=12, pady=(10, 6))

        # ── Python Suite creator ───────────────────────────────────────────
        py_box = tk.LabelFrame(
            frame, text=" New Python Suite ",
            font=("Arial", 9, "bold"), bg=_CLR["panel"],
            relief="groove", bd=2, padx=10, pady=8,
        )
        py_box.pack(fill=tk.X, padx=12, pady=(0, 8))

        tk.Label(py_box, text="Suite name (no .py):", bg=_CLR["panel"],
                 font=("Arial", 9)).grid(row=0, column=0, sticky=tk.W, pady=2)
        tk.Entry(py_box, textvariable=self._tc_py_name_var, width=30,
                 font=("Courier", 9)).grid(row=0, column=1, sticky=tk.EW, pady=2, padx=(6, 0))

        tk.Label(py_box, text="Destination folder:", bg=_CLR["panel"],
                 font=("Arial", 9)).grid(row=1, column=0, sticky=tk.W, pady=2)
        py_dir_frame = tk.Frame(py_box, bg=_CLR["panel"])
        py_dir_frame.grid(row=1, column=1, sticky=tk.EW, pady=2, padx=(6, 0))
        tk.Entry(py_dir_frame, textvariable=self._tc_py_dir_var, width=24,
                 font=("Courier", 9)).pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Button(py_dir_frame, text="…", padx=3,
                  command=self._browse_tc_py_dir).pack(side=tk.LEFT, padx=2)

        tk.Button(
            py_box, text="＋ Create Python Suite",
            font=("Arial", 9, "bold"),
            bg=_CLR["btn_new"], fg="#fff", relief="flat", padx=10, pady=5,
            cursor="hand2", command=self._create_py_suite,
        ).grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=(6, 0))
        _ToolTip(py_box,
                 "Creates a new unittest-based Python test suite under the tests/ directory\n"
                 "(or a custom folder). Opens in IDLE after creation.")
        py_box.columnconfigure(1, weight=1)

        # ── JSON Suite creator ─────────────────────────────────────────────
        json_box = tk.LabelFrame(
            frame, text=" New JSON Suite ",
            font=("Arial", 9, "bold"), bg=_CLR["panel"],
            relief="groove", bd=2, padx=10, pady=8,
        )
        json_box.pack(fill=tk.X, padx=12, pady=(0, 8))

        tk.Label(json_box, text="Suite name (no _test_cases.json):", bg=_CLR["panel"],
                 font=("Arial", 9)).grid(row=0, column=0, sticky=tk.W, pady=2)
        tk.Entry(json_box, textvariable=self._tc_json_name_var, width=30,
                 font=("Courier", 9)).grid(row=0, column=1, sticky=tk.EW, pady=2, padx=(6, 0))

        tk.Label(json_box, text="Destination folder:", bg=_CLR["panel"],
                 font=("Arial", 9)).grid(row=1, column=0, sticky=tk.W, pady=2)
        json_dir_frame = tk.Frame(json_box, bg=_CLR["panel"])
        json_dir_frame.grid(row=1, column=1, sticky=tk.EW, pady=2, padx=(6, 0))
        tk.Entry(json_dir_frame, textvariable=self._tc_json_dir_var, width=24,
                 font=("Courier", 9)).pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Button(json_dir_frame, text="…", padx=3,
                  command=self._browse_tc_json_dir).pack(side=tk.LEFT, padx=2)

        tk.Button(
            json_box, text="＋ Create JSON Suite",
            font=("Arial", 9, "bold"),
            bg="#17a2b8", fg="#fff", relief="flat", padx=10, pady=5,
            cursor="hand2", command=self._create_json_suite,
        ).grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=(6, 0))
        _ToolTip(json_box,
                 "Creates a new JSON test-case file from the built-in template.\n"
                 "Opens in the default editor after creation.")
        json_box.columnconfigure(1, weight=1)

        # ── Usage note ────────────────────────────────────────────────────
        note = (
            "ℹ️  After creation the new file appears in the Python Suites / JSON Suites tab\n"
            "   after clicking  ↺ Reload List.  Edit the template, then run it from the suites tabs."
        )
        tk.Label(frame, text=note, font=("Arial", 9, "italic"),
                 bg=_CLR["panel"], fg="#777", justify=tk.LEFT,
                 ).pack(anchor=tk.W, padx=12, pady=4)

    # ── Reports Browser tab ────────────────────────────────────────────────

    def _build_reports_tab(self, nb: ttk.Notebook) -> None:
        """Tab for browsing all previously generated HTML reports."""
        frame = tk.Frame(nb, bg=_CLR["panel"])
        nb.add(frame, text="  Reports  ")

        tk.Label(
            frame,
            text="All HTML reports generated by previous test runs.  Double-click to open.",
            font=("Arial", 9), bg=_CLR["panel"], fg="#555",
        ).pack(anchor=tk.W, padx=12, pady=(10, 4))

        # Buttons row
        rep_btn_frame = tk.Frame(frame, bg=_CLR["panel"])
        rep_btn_frame.pack(anchor=tk.W, padx=12, pady=(0, 4))
        tk.Button(rep_btn_frame, text="↺ Refresh", font=("Arial", 9),
                  bg=_CLR["btn_clear"], fg="#fff", relief="flat", padx=8, pady=4,
                  cursor="hand2", command=self._refresh_reports_list).pack(side=tk.LEFT, padx=(0, 6))
        tk.Button(rep_btn_frame, text="🌐 Open Selected", font=("Arial", 9),
                  bg=_CLR["btn_open"], fg="#fff", relief="flat", padx=8, pady=4,
                  cursor="hand2", command=self._open_selected_report).pack(side=tk.LEFT, padx=(0, 6))
        tk.Button(rep_btn_frame, text="📁 Open Folder", font=("Arial", 9),
                  bg=_CLR["btn_new"], fg="#fff", relief="flat", padx=8, pady=4,
                  cursor="hand2", command=self._open_reports_folder).pack(side=tk.LEFT)

        # Reports listbox
        list_frame = tk.Frame(frame, bg=_CLR["panel"])
        list_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=4)

        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self._reports_listbox = tk.Listbox(
            list_frame, font=("Courier", 10), selectmode=tk.SINGLE,
            yscrollcommand=scrollbar.set, activestyle="dotbox",
            selectbackground="#0056b3", selectforeground="#fff",
        )
        self._reports_listbox.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=self._reports_listbox.yview)
        self._reports_listbox.bind("<Double-1>", lambda _e: self._open_selected_report())

        # Internal list to map listbox index → Path
        self._report_paths: List[Path] = []

        # Auto-populate on tab build
        self._refresh_reports_list()

    # ------------------------------------------------------------------ test creator actions

    def _browse_tc_py_dir(self) -> None:
        path = filedialog.askdirectory(
            title="Select destination folder for new Python suite",
            initialdir=str(_FRAMEWORK_DIR / "tests"),
        )
        if path:
            self._tc_py_dir_var.set(path)

    def _browse_tc_json_dir(self) -> None:
        path = filedialog.askdirectory(
            title="Select destination folder for new JSON suite",
            initialdir=str(_FRAMEWORK_DIR),
        )
        if path:
            self._tc_json_dir_var.set(path)

    def _create_py_suite(self) -> None:
        """Create a new Python test suite from template and open in editor."""
        raw = self._tc_py_name_var.get().strip()
        if not raw:
            messagebox.showwarning("Name Required", "Please enter a suite name.")
            return

        # Strip a trailing .py suffix if the user typed it
        if raw.endswith(".py"):
            raw = raw[:-3]

        # Restrict to safe identifier characters only – reject any path separators,
        # dots (which could be used for directory traversal), and special chars.
        name = re.sub(r"[^A-Za-z0-9_]", "_", raw).strip("_")
        if not name:
            messagebox.showerror(
                "Invalid Name",
                "Suite name must contain at least one letter, digit or underscore.\n"
                "Characters like '/', '..', '-' are not allowed.",
            )
            return

        dest_str = self._tc_py_dir_var.get().strip()
        dest = Path(dest_str) if dest_str else (_FRAMEWORK_DIR / "tests")
        dest.mkdir(parents=True, exist_ok=True)
        out_path = dest / f"{name}.py"

        if out_path.exists():
            if not messagebox.askyesno(
                "File Exists",
                f"File already exists:\n{out_path}\n\nOverwrite?",
            ):
                return

        template = self._py_suite_template(name)
        out_path.write_text(template, encoding="utf-8")
        self._log_line(f"[GUI] Created Python suite: {out_path}", "pass")
        self._refresh_suite_lists()
        self._open_in_editor(out_path)

    def _create_json_suite(self) -> None:
        """Create a new JSON test-case file from template and open in editor."""
        raw = self._tc_json_name_var.get().strip()
        if not raw:
            messagebox.showwarning("Name Required", "Please enter a suite name.")
            return

        # Strip trailing suffixes if the user typed them
        for suffix in ("_test_cases.json", ".json"):
            if raw.endswith(suffix):
                raw = raw[: -len(suffix)]

        # Same safe-character restriction as the Python creator
        name = re.sub(r"[^A-Za-z0-9_]", "_", raw).strip("_")
        if not name:
            messagebox.showerror(
                "Invalid Name",
                "Suite name must contain at least one letter, digit or underscore.\n"
                "Characters like '/', '..', '-' are not allowed.",
            )
            return

        dest_str = self._tc_json_dir_var.get().strip()
        dest = Path(dest_str) if dest_str else _FRAMEWORK_DIR
        dest.mkdir(parents=True, exist_ok=True)
        out_path = dest / f"{name}_test_cases.json"

        if out_path.exists():
            if not messagebox.askyesno(
                "File Exists",
                f"File already exists:\n{out_path}\n\nOverwrite?",
            ):
                return

        template = self._json_suite_template(name)
        out_path.write_text(json.dumps(template, indent=2), encoding="utf-8")
        self._log_line(f"[GUI] Created JSON suite: {out_path}", "pass")
        self._refresh_suite_lists()
        self._open_in_editor(out_path)

    @staticmethod
    def _py_suite_template(name: str) -> str:
        """Return a starter Python unittest suite as a string."""
        return (
            '"""\n'
            f'{name} – GM VIP Automation Framework test suite\n'
            f'Generated by GUI Test Creator on {datetime.date.today()}\n'
            '"""\n'
            "from __future__ import annotations\n\n"
            "import sys\n"
            "import unittest\n"
            "from pathlib import Path\n\n"
            "# Bootstrap sys.path so the suite can be run directly\n"
            "_REPO = Path(__file__).resolve().parent.parent.parent\n"
            "if str(_REPO) not in sys.path:\n"
            "    sys.path.insert(0, str(_REPO))\n\n"
            "from GM_VIP_Automation_Framework.core.connection import T32Connection\n\n\n"
            f"class {name.title().replace('_', '')}Tests(unittest.TestCase):\n"
            '    """Auto-generated test suite.  Add test methods below."""\n\n'
            "    @classmethod\n"
            "    def setUpClass(cls) -> None:\n"
            "        # Replace with your connection logic (mock or live).\n"
            "        cls.conn = T32Connection(mock=True)\n"
            "        cls.conn.connect()\n\n"
            "    @classmethod\n"
            "    def tearDownClass(cls) -> None:\n"
            "        cls.conn.disconnect()\n\n"
            "    def test_placeholder(self) -> None:\n"
            '        """Placeholder test – replace with real assertions."""\n'
            "        self.assertTrue(True)\n\n\n"
            'if __name__ == "__main__":\n'
            "    unittest.main(verbosity=2)\n"
        )

    @staticmethod
    def _json_suite_template(name: str) -> dict:
        """Return a starter JSON test-case dict."""
        return {
            "_comment": f"GM VIP Automation Framework – {name} test cases",
            "_generated": str(datetime.date.today()),
            "test_suite": name,
            "test_cases": [
                {
                    "name": "TC_Placeholder_01",
                    "capl_reference": "",
                    "enabled": True,
                    "reset_before": False,
                    "go_before_check": False,
                    "breakpoints": [],
                    "variables_write": {},
                    "variables_check": {},
                    "symbols_inspect": [],
                },
            ],
        }

    # ------------------------------------------------------------------ reports browser

    def _refresh_reports_list(self) -> None:
        """Scan Test_Report/ for HTML files and populate the reports listbox."""
        self._report_paths = []
        if not hasattr(self, "_reports_listbox"):
            return
        self._reports_listbox.delete(0, tk.END)

        report_root = _FRAMEWORK_DIR / "Test_Report"
        if not report_root.exists():
            self._reports_listbox.insert(tk.END, "  (no reports found – run a test suite first)")
            return

        # Precompute (mtime, path) once per file; skip files deleted mid-scan.
        candidates: List[Tuple[float, Path]] = []
        for p in report_root.rglob("*.html"):
            try:
                candidates.append((p.stat().st_mtime, p))
            except OSError:
                pass  # file was removed between rglob and stat

        if not candidates:
            self._reports_listbox.insert(tk.END, "  (no reports found – run a test suite first)")
            return

        candidates.sort(key=lambda t: t[0], reverse=True)
        for mtime_ts, p in candidates:
            mtime = datetime.datetime.fromtimestamp(mtime_ts)
            ts = mtime.strftime("%Y-%m-%d %H:%M")
            try:
                label = f"  {ts}  {p.relative_to(_FRAMEWORK_DIR)}"
            except ValueError:
                label = f"  {ts}  {p}"
            self._reports_listbox.insert(tk.END, label)
            self._report_paths.append(p)

    def _open_selected_report(self) -> None:
        """Open the report selected in the reports listbox."""
        if not hasattr(self, "_reports_listbox"):
            return
        sel = self._reports_listbox.curselection()
        if not sel or sel[0] >= len(self._report_paths):
            messagebox.showwarning("No Selection", "Please select a report to open.")
            return
        path = self._report_paths[sel[0]]
        if path.is_file():
            webbrowser.open(path.as_uri())
        else:
            messagebox.showerror("File Not Found", f"Report not found:\n{path}")

    def _open_reports_folder(self) -> None:
        """Open the Test_Report folder in the OS file manager."""
        folder = _FRAMEWORK_DIR / "Test_Report"
        folder.mkdir(parents=True, exist_ok=True)
        system = platform.system().lower()
        try:
            if system == "windows":
                os.startfile(str(folder))
            elif system == "darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except Exception as exc:
            messagebox.showerror("Cannot Open Folder", str(exc))

    # ------------------------------------------------------------------ SD queue

    def _add_to_disc_queue(self) -> None:
        """Add the current Symbol Discovery configuration to the queue."""
        entry: Dict[str, Any] = {
            "pattern":  self._disc_pattern_var.get() or "*",
            "module":   self._disc_module_var.get(),
            "bp":       self._disc_bp_var.get(),
            "suite":    self._disc_suite_var.get() or "test_symbol_discovery",
            "max_sym":  self._disc_max_sym_var.get(),
            "resolve":  self._disc_resolve_var.get(),
            "verbose":  self._disc_verbose_var.get(),
            "out_dir":  self._disc_output_var.get(),
        }
        self._disc_queue.append(entry)
        self._refresh_disc_queue_list()
        self._log_line(
            f"[GUI] Added to Discovery Queue: pattern={entry['pattern']!r}  "
            f"suite={entry['suite']!r}  ({len(self._disc_queue)} total)", "info",
        )
        self._save_gui_state()

    def _remove_from_disc_queue(self) -> None:
        """Remove the selected entry from the discovery queue."""
        if not hasattr(self, "_disc_queue_listbox"):
            return
        sel = self._disc_queue_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx < len(self._disc_queue):
            removed = self._disc_queue.pop(idx)
            self._log_line(
                f"[GUI] Removed from queue: {removed.get('suite', '?')}", "info",
            )
            self._refresh_disc_queue_list()
            self._save_gui_state()

    def _clear_disc_queue(self) -> None:
        """Clear all entries from the discovery queue."""
        if not self._disc_queue:
            return
        if messagebox.askyesno("Clear Queue", "Remove all entries from the discovery queue?"):
            self._disc_queue.clear()
            self._refresh_disc_queue_list()
            self._save_gui_state()
            self._log_line("[GUI] Discovery queue cleared.", "info")

    def _refresh_disc_queue_list(self) -> None:
        """Repopulate the queue listbox from self._disc_queue."""
        if not hasattr(self, "_disc_queue_listbox"):
            return
        self._disc_queue_listbox.delete(0, tk.END)
        for i, entry in enumerate(self._disc_queue, 1):
            suite   = entry.get("suite", "?")
            pattern = entry.get("pattern", "*")
            module  = entry.get("module", "")
            mod_str = f"  mod={module!r}" if module else ""
            self._disc_queue_listbox.insert(
                tk.END,
                f"  [{i}] {suite:<30}  pattern={pattern!r}{mod_str}",
            )

    def _run_queue_as_python(self) -> None:
        """Run all queued Symbol Discovery configs and generate Python suites."""
        if not self._disc_queue:
            messagebox.showinfo("Empty Queue", "No entries in the discovery queue.")
            return
        if self._runner.running:
            messagebox.showwarning("Busy", "A test is already running.")
            return
        try:
            port = int(self._port_var.get())
        except ValueError:
            from GM_VIP_Automation_Framework.config import settings
            port = settings.rcl_port
        al   = self._auto_launch_var.get()
        cmm  = self._cmm_var.get() or None
        self._apply_port(str(port))
        queue_copy = list(self._disc_queue)
        self._log_line(
            f"[GUI] ── Running {len(queue_copy)} queued discovery config(s) "
            "→ Python suites ──", "info",
        )
        self._runner.run(self._do_run_queue_discover, entries=queue_copy,
                         port=port, al=al, cmm=cmm)

    def _run_queue_as_json(self) -> None:
        """Run all queued Symbol Discovery configs and generate JSON suites."""
        if not self._disc_queue:
            messagebox.showinfo("Empty Queue", "No entries in the discovery queue.")
            return
        if self._runner.running:
            messagebox.showwarning("Busy", "A test is already running.")
            return
        try:
            port = int(self._port_var.get())
        except ValueError:
            from GM_VIP_Automation_Framework.config import settings
            port = settings.rcl_port
        al   = self._auto_launch_var.get()
        cmm  = self._cmm_var.get() or None
        self._apply_port(str(port))
        queue_copy = list(self._disc_queue)
        self._log_line(
            f"[GUI] ── Running {len(queue_copy)} queued discovery config(s) "
            "→ JSON suites ──", "info",
        )
        self._runner.run(self._do_run_queue_discover, entries=queue_copy,
                         port=port, al=al, cmm=cmm)

    @staticmethod
    def _do_run_queue_discover(
        entries: List[Dict[str, Any]],
        port: int,
        al: bool,
        cmm: Optional[str],
        stop_event: threading.Event,
    ) -> None:
        """Worker: run all queued discovery configs sequentially."""
        for entry in entries:
            if stop_event.is_set():
                break
            out_raw = entry.get("out_dir", "")
            out_dir = Path(out_raw) if out_raw else None
            try:
                max_sym = int(entry.get("max_sym", 500))
            except (ValueError, TypeError):
                max_sym = 500
            _run_discover(
                output_dir=out_dir,
                suite_name=entry.get("suite", "test_symbol_discovery"),
                pattern=entry.get("pattern", "*"),
                module_filter=entry.get("module", ""),
                breakpoint_symbol=entry.get("bp", ""),
                port=port,
                auto_launch=al,
                cmm_script=cmm,
                resolve_addresses=bool(entry.get("resolve", True)),
                max_symbols=max_sym,
                verbose=bool(entry.get("verbose", False)),
            )

    # ------------------------------------------------------------------ C Source Files tab

    def _build_c_files_tab(self, nb: ttk.Notebook) -> None:
        """Tab for registering, viewing, and syncing *.c source files with Trace32."""
        frame = tk.Frame(nb, bg=_CLR["panel"])
        nb.add(frame, text="  C Source Files  ")

        tk.Label(
            frame,
            text=(
                "Register *.c source files, extract function and variable names, and\n"
                "sync them with the Symbol Discovery tab to confirm Trace32 is loaded\n"
                "with the latest compiled source."
            ),
            font=("Arial", 9), bg=_CLR["panel"], fg="#555", justify=tk.LEFT,
        ).pack(anchor=tk.W, padx=12, pady=(10, 6))

        # ── Registered files section ───────────────────────────────────────
        file_box = tk.LabelFrame(
            frame, text=" Registered C Files ",
            font=("Arial", 9, "bold"), bg=_CLR["panel"],
            relief="groove", bd=2, padx=8, pady=6,
        )
        file_box.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 6))

        c_btn_frame = tk.Frame(file_box, bg=_CLR["panel"])
        c_btn_frame.pack(anchor=tk.W, pady=(0, 4))

        tk.Button(
            c_btn_frame, text="＋ Add File…", font=("Arial", 9),
            bg=_CLR["btn_run"], fg="#fff", relief="flat", padx=8, pady=4,
            cursor="hand2", command=self._c_add_file,
        ).pack(side=tk.LEFT, padx=(0, 4))
        tk.Button(
            c_btn_frame, text="✕ Remove", font=("Arial", 9),
            bg=_CLR["btn_stop"], fg="#fff", relief="flat", padx=8, pady=4,
            cursor="hand2", command=self._c_remove_file,
        ).pack(side=tk.LEFT, padx=(0, 4))
        tk.Button(
            c_btn_frame, text="✏ Open in Editor", font=("Arial", 9),
            bg="#17a2b8", fg="#fff", relief="flat", padx=8, pady=4,
            cursor="hand2", command=self._c_open_in_editor,
        ).pack(side=tk.LEFT, padx=(0, 4))
        tk.Button(
            c_btn_frame, text="🗑 Clear All", font=("Arial", 9),
            bg=_CLR["btn_clear"], fg="#fff", relief="flat", padx=8, pady=4,
            cursor="hand2", command=self._c_clear_files,
        ).pack(side=tk.LEFT)
        _ToolTip(c_btn_frame,
                 "Add File: browse for one or more *.c source files.\n"
                 "Remove: unregister the selected file (does not delete it from disk).\n"
                 "Open in Editor: open the selected file in IDLE or the OS default editor.\n"
                 "Clear All: unregister every file in the list.")

        # File listbox
        c_list_frame = tk.Frame(file_box, bg=_CLR["panel"])
        c_list_frame.pack(fill=tk.BOTH, expand=True)
        c_scrollbar = tk.Scrollbar(c_list_frame)
        c_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._c_listbox = tk.Listbox(
            c_list_frame, font=("Courier", 9), selectmode=tk.SINGLE,
            yscrollcommand=c_scrollbar.set, activestyle="dotbox",
            selectbackground="#0056b3", selectforeground="#fff",
            height=6,
        )
        self._c_listbox.pack(fill=tk.BOTH, expand=True)
        c_scrollbar.config(command=self._c_listbox.yview)
        self._c_listbox.bind("<Double-1>", lambda _e: self._c_open_in_editor())

        # ── Symbol extraction section ──────────────────────────────────────
        sym_box = tk.LabelFrame(
            frame, text=" Symbol Extraction ",
            font=("Arial", 9, "bold"), bg=_CLR["panel"],
            relief="groove", bd=2, padx=8, pady=6,
        )
        sym_box.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 6))

        sym_btn_frame = tk.Frame(sym_box, bg=_CLR["panel"])
        sym_btn_frame.pack(anchor=tk.W, pady=(0, 4))
        tk.Button(
            sym_btn_frame, text="⚙ Extract Symbols from Selected File",
            font=("Arial", 9), bg=_CLR["btn_new"], fg="#fff",
            relief="flat", padx=8, pady=4, cursor="hand2",
            command=self._c_extract_symbols,
        ).pack(side=tk.LEFT, padx=(0, 4))
        tk.Button(
            sym_btn_frame, text="→ Sync with Symbol Discovery",
            font=("Arial", 9), bg="#17a2b8", fg="#fff",
            relief="flat", padx=8, pady=4, cursor="hand2",
            command=self._c_sync_with_discovery,
        ).pack(side=tk.LEFT)
        _ToolTip(sym_btn_frame,
                 "Extract Symbols: scans the selected .c file for function and variable names.\n"
                 "Sync with Symbol Discovery: auto-fills the Symbol Discovery Module Filter\n"
                 "with the selected file name and switches to that tab.  Run Discovery to\n"
                 "confirm Trace32 has loaded the symbols from the latest compiled source.")

        # Extracted symbol display
        self._c_sym_text = tk.Text(
            sym_box, font=("Courier", 9), height=7, state=tk.DISABLED,
            bg="#fdfdfd", relief="solid", borderwidth=1, wrap=tk.WORD,
        )
        self._c_sym_text.pack(fill=tk.BOTH, expand=True)

        # Internal state for extracted symbols
        self._c_extracted_funcs: List[str] = []
        self._c_extracted_vars: List[str] = []

        # Tip
        tk.Label(
            frame,
            text=(
                "ℹ️  Tip: After extracting symbols, click '→ Sync with Symbol Discovery'\n"
                "   to confirm Trace32 has loaded those symbols from the latest build.\n"
                "   A ✔ prefix means the file exists on disk; ✘ means it was moved or deleted."
            ),
            font=("Arial", 9, "italic"), bg=_CLR["panel"], fg="#777", justify=tk.LEFT,
        ).pack(anchor=tk.W, padx=12, pady=(0, 8))

    # ── C Source Files actions ─────────────────────────────────────────────

    def _c_add_file(self) -> None:
        """Open a file dialog to add one or more *.c files to the registry."""
        paths = filedialog.askopenfilenames(
            title="Select C source file(s)",
            filetypes=[("C source files", "*.c"), ("All files", "*.*")],
        )
        added = 0
        for p_str in paths:
            p = Path(p_str)
            if p not in self._c_files:
                self._c_files.append(p)
                added += 1
        if added:
            self._c_refresh_listbox()
            self._log_line(
                f"[GUI] Added {added} C file(s) to the registry.", "info",
            )
            self._save_gui_state()

    def _c_remove_file(self) -> None:
        """Remove the selected C file from the registry (does not delete on disk)."""
        if not hasattr(self, "_c_listbox"):
            return
        sel = self._c_listbox.curselection()
        if not sel:
            messagebox.showwarning("No Selection", "Please select a file to remove.")
            return
        idx = sel[0]
        if idx < len(self._c_files):
            removed = self._c_files.pop(idx)
            self._log_line(f"[GUI] Removed from registry: {removed.name}", "info")
            self._c_refresh_listbox()
            self._save_gui_state()

    def _c_clear_files(self) -> None:
        """Clear all registered C files."""
        if not self._c_files:
            return
        if messagebox.askyesno("Clear Files", "Remove all registered C source files?"):
            self._c_files.clear()
            self._c_refresh_listbox()
            self._log_line("[GUI] C file registry cleared.", "info")
            self._save_gui_state()

    def _c_open_in_editor(self) -> None:
        """Open the selected C file in IDLE or the OS default editor."""
        if not hasattr(self, "_c_listbox"):
            return
        sel = self._c_listbox.curselection()
        if not sel:
            messagebox.showwarning("No Selection", "Please select a file to open.")
            return
        idx = sel[0]
        if idx < len(self._c_files):
            path = self._c_files[idx]
            if not path.is_file():
                messagebox.showerror("File Not Found", f"File not found:\n{path}")
                return
            self._open_in_editor(path)

    def _c_refresh_listbox(self) -> None:
        """Repopulate the C files listbox from self._c_files."""
        if not hasattr(self, "_c_listbox"):
            return
        self._c_listbox.delete(0, tk.END)
        for p in self._c_files:
            exists_mark = "✔" if p.is_file() else "✘"
            self._c_listbox.insert(tk.END, f"  {exists_mark}  {p}")

    def _c_extract_symbols(self) -> None:
        """Parse the selected C file and display extracted function/variable names."""
        if not hasattr(self, "_c_listbox"):
            return
        sel = self._c_listbox.curselection()
        if not sel:
            messagebox.showwarning(
                "No Selection",
                "Please select a C file from the list first.",
            )
            return
        idx = sel[0]
        if idx >= len(self._c_files):
            return
        path = self._c_files[idx]
        if not path.is_file():
            messagebox.showerror("File Not Found", f"File not found:\n{path}")
            return
        try:
            funcs, vars_ = self._parse_c_file(path)
        except Exception as exc:
            messagebox.showerror(
                "Parse Error",
                f"Could not parse {path.name}:\n{exc}",
            )
            return

        self._c_extracted_funcs = funcs
        self._c_extracted_vars  = vars_

        # Display results in the text widget
        self._c_sym_text.config(state=tk.NORMAL)
        self._c_sym_text.delete("1.0", tk.END)
        self._c_sym_text.insert(tk.END, f"File: {path}\n\n")
        if funcs:
            self._c_sym_text.insert(tk.END, f"Functions ({len(funcs)}):\n")
            preview = funcs[:60]
            self._c_sym_text.insert(tk.END, "  " + ",  ".join(preview) + "\n")
            if len(funcs) > 60:
                self._c_sym_text.insert(tk.END, f"  … and {len(funcs) - 60} more\n")
        else:
            self._c_sym_text.insert(tk.END, "Functions: (none found)\n")
        self._c_sym_text.insert(tk.END, "\n")
        if vars_:
            self._c_sym_text.insert(tk.END, f"Global Variables ({len(vars_)}):\n")
            preview_v = vars_[:60]
            self._c_sym_text.insert(tk.END, "  " + ",  ".join(preview_v) + "\n")
            if len(vars_) > 60:
                self._c_sym_text.insert(tk.END, f"  … and {len(vars_) - 60} more\n")
        else:
            self._c_sym_text.insert(tk.END, "Global Variables: (none found)\n")
        self._c_sym_text.config(state=tk.DISABLED)

        self._log_line(
            f"[GUI] Extracted {len(funcs)} function(s) and {len(vars_)} variable(s) "
            f"from {path.name}.",
            "info",
        )

    @staticmethod
    def _parse_c_file(path: Path) -> Tuple[List[str], List[str]]:
        """Extract function and variable names from a C file using simple heuristics.

        Returns a tuple of ``(function_names, variable_names)``.  Both lists
        contain unique identifiers in order of first appearance.
        """
        text = path.read_text(encoding="utf-8", errors="ignore")

        # Remove block comments
        text = re.sub(r'/\*.*?\*/', ' ', text, flags=re.DOTALL)
        # Remove line comments
        text = re.sub(r'//[^\n]*', '', text)
        # Remove preprocessor directives (keep newlines so line offsets hold)
        text = re.sub(r'^\s*#[^\n]*', '', text, flags=re.MULTILINE)
        # Replace string literals with placeholders (avoid false identifier matches)
        text = re.sub(r'"(?:[^"\\]|\\.)*"', '""', text)

        # Function definitions: lines starting at column 0, then an identifier
        # immediately followed by '(' (with optional spaces).
        func_re = re.compile(
            r'^(?:[\w\s*]+\s+)?([A-Za-z_]\w*)\s*\(',
            re.MULTILINE,
        )
        funcs: List[str] = []
        seen_f: set = set()
        for m in func_re.finditer(text):
            name = m.group(1)
            if name and name not in _C_KEYWORDS and name not in seen_f:
                seen_f.add(name)
                funcs.append(name)

        # Global variable declarations: non-indented lines ending with ';'
        # that do NOT contain '(' (to exclude function prototypes / calls).
        var_re = re.compile(
            r'^(?![ \t])(?:[\w\s*]+\s+)([A-Za-z_]\w*)\s*(?:=\s*[^;(]+)?;',
            re.MULTILINE,
        )
        vars_: List[str] = []
        seen_v: set = set()
        for m in var_re.finditer(text):
            name = m.group(1)
            if (
                name
                and name not in _C_KEYWORDS
                and name not in seen_f   # don't repeat function names
                and name not in seen_v
            ):
                seen_v.add(name)
                vars_.append(name)

        return funcs, vars_

    def _c_sync_with_discovery(self) -> None:
        """Auto-fill the Symbol Discovery tab with the selected C file's name and switch to it.

        Sets the *Module Filter* to the C file's base name so that T32 symbol
        discovery only returns symbols whose source path contains that name.
        This is the most reliable way to verify that Trace32 is in sync with
        the latest compiled source file.
        """
        if not hasattr(self, "_c_listbox"):
            return
        sel = self._c_listbox.curselection()
        filename = ""
        if sel and sel[0] < len(self._c_files):
            # Preferred: use the file the user has selected in the listbox.
            filename = self._c_files[sel[0]].name
        elif not self._c_files:
            messagebox.showwarning(
                "No Files",
                "No C files are registered yet.\nAdd a file using '＋ Add File…' first.",
            )
            return
        else:
            # No listbox selection – require the user to extract symbols first so
            # we at least know which file they are working with.
            if not self._c_extracted_funcs and not self._c_extracted_vars:
                messagebox.showwarning(
                    "No Selection",
                    "Please select a C file in the list above, or run '⚙ Extract Symbols' first.",
                )
                return
            # filename stays "" – we will sync without a module filter;
            # the user can set it manually in the Discovery tab.

        # Populate Symbol Discovery: use '*' pattern and filter by source file name
        self._disc_pattern_var.set("*")
        if filename:
            self._disc_module_var.set(filename)

        self._nb.select(2)  # Symbol Discovery tab

        module_info = f"module='{filename}'" if filename else "module=<not set – select a file>"
        tip = (
            f"[GUI] Symbol Discovery pre-filled: pattern='*'  {module_info}.  "
            "Click '▶ Run Discovery' to list all T32 symbols from that source file "
            "and confirm they are in sync with the latest compiled code."
        )
        self._log_line(tip, "info")

    # ------------------------------------------------------------------ T32 monitor

    def _start_t32_monitor(self) -> None:
        """Start the background thread that monitors T32 connection status."""
        # Initialise _monitor_packlen from settings so checklist messages show the
        # configured value even before the first _apply_port() call.
        try:
            from GM_VIP_Automation_Framework.config import settings
            self._monitor_packlen = settings.rcl_packlen
        except Exception:
            pass  # leave the default 1024 in place
        self._t32_monitor_stop.clear()
        self._t32_monitor_thread = threading.Thread(
            target=self._t32_monitor_loop,
            daemon=True,
            name="T32Monitor",
        )
        self._t32_monitor_thread.start()

    def _t32_monitor_loop(self) -> None:
        """Probe T32 RCL port every _T32_MONITOR_INTERVAL_S seconds.

        Intentionally avoids touching any Tkinter variables (not thread-safe).
        Uses the plain ``_monitor_port`` and ``_monitor_mode`` int/str attributes,
        which are kept in sync by ``_on_port_var_changed`` /
        ``_on_mode_var_changed`` on the main thread.

        After ``_T32_DETECT_WARN_S`` seconds of continuous failed probes while in
        *live* mode the monitor posts a ``t32_timeout_warn`` message so the main
        thread can offer the user a retry / reconfigure dialog.

        The failure-streak timer is only started/maintained when in *live* mode.
        ``_t32_fail_reset`` can be set from the main thread at any time to
        immediately restart the 30-second cycle (used by Retry Now and mode switch).
        """
        from GM_VIP_Automation_Framework.core.connection import T32Connection

        last_state: Optional[bool] = None
        fail_start: Optional[float] = None   # monotonic time when failure streak began

        while not self._t32_monitor_stop.is_set():
            # Check for an external reset request (Retry Now / mode switch).
            if self._t32_fail_reset.is_set():
                self._t32_fail_reset.clear()
                fail_start = None

            try:
                port = self._monitor_port
                probe = T32Connection(port=port)
                connected = probe.try_connect()
                if connected:
                    probe.disconnect()
            except Exception:
                connected = False

            if connected:
                # Successful connection – reset failure tracking.
                fail_start = None
                self._t32_warn_sent = False
            elif self._monitor_mode == "live":
                # Only track and warn about failures when in live mode.
                now = time.monotonic()
                if fail_start is None:
                    fail_start = now
                elif (
                    not self._t32_warn_sent
                    and (now - fail_start) >= _T32_DETECT_WARN_S
                ):
                    # First occurrence of a 30-second detection timeout in live mode.
                    self._t32_warn_sent = True
                    self._q.put(("t32_timeout_warn", port))
            else:
                # In mock mode: clear the streak so switching to live starts fresh.
                fail_start = None

            if connected != last_state:
                last_state = connected
                self._q.put(("t32_status", connected))

            self._t32_monitor_stop.wait(_T32_MONITOR_INTERVAL_S)

    def _update_t32_led(self, connected: bool) -> None:
        """Update the T32 LED color in the status bar (main thread only)."""
        self._t32_connected = connected
        if not hasattr(self, "_t32_led_canvas"):
            return
        if connected:
            self._t32_led_canvas.itemconfig(
                self._t32_led_oval, fill="#00cc44", outline="#008822",
            )
        else:
            self._t32_led_canvas.itemconfig(
                self._t32_led_oval, fill="#cc0000", outline="#880000",
            )

    def _show_t32_timeout_dialog(self, port: int) -> None:
        """Show a dialog after 30 s of failed T32 detection in live mode.

        Offers three actions:
        * Retry now  – resets the warning flag so another 30-second cycle begins.
        * Reconfigure – opens the Configuration tab so the user can update port / RCL settings.
        * Dismiss     – suppresses further dialogs until T32 connects then disconnects again.
        """
        dlg = tk.Toplevel(self)
        dlg.title("Trace32 Detection Timeout")
        dlg.resizable(False, False)
        dlg.grab_set()
        dlg.configure(bg="#fff3cd")

        # Icon + heading
        tk.Label(
            dlg,
            text="⚠  Trace32 Not Detected",
            font=("Arial", 12, "bold"), fg="#856404", bg="#fff3cd",
            padx=16, pady=(12, 0),
        ).pack(anchor=tk.W)

        body = (
            f"Trace32 has not responded on RCL port {port} for the last\n"
            f"{_T32_DETECT_WARN_S} seconds.\n\n"
            "Common causes:\n"
            f"  • config.t32 is missing:  RCL=NETASSIST / PORT={port} / PACKLEN={self._monitor_packlen}\n"
            "  • Trace32 does not have permission to open the network port\n"
            "    (try running Trace32 as Administrator on Windows).\n"
            "  • A firewall or antivirus is blocking the RCL port.\n"
            "  • The port number in the GUI does not match the one in config.t32.\n"
            "  • Trace32 is not running – click 'Open T32' to launch it first."
        )
        tk.Label(
            dlg, text=body,
            font=("Arial", 9), bg="#fff3cd", fg="#333",
            justify=tk.LEFT, padx=16, pady=8,
        ).pack(anchor=tk.W)

        ttk.Separator(dlg, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=12, pady=(4, 8))

        btn_frame = tk.Frame(dlg, bg="#fff3cd")
        btn_frame.pack(padx=16, pady=(0, 12))

        def _retry() -> None:
            dlg.destroy()
            # Signal the monitor thread to reset its failure-streak start time so
            # the next 30-second cycle begins from now, not from the original fail.
            self._t32_warn_sent = False
            self._t32_fail_reset.set()
            self._log_line(
                f"[GUI] Retry requested – T32 detection timer reset on port {port} …",
                "info",
            )

        def _reconfigure() -> None:
            dlg.destroy()
            self._nb.select(3)  # Configuration tab
            self._log_line(
                "[GUI] Opened Configuration tab.  Update port/RCL settings, save "
                "config.json, then click 'Open T32' to retry.", "info",
            )

        def _dismiss() -> None:
            dlg.destroy()
            self._log_line(
                "[GUI] T32 timeout warning dismissed.  "
                "Warning will reappear after the next successful connection is lost.",
                "debug",
            )

        tk.Button(
            btn_frame, text="↺ Retry Now",
            font=("Arial", 9, "bold"), bg="#28a745", fg="#fff",
            relief="flat", padx=10, pady=5, cursor="hand2",
            command=_retry,
        ).pack(side=tk.LEFT, padx=(0, 6))
        tk.Button(
            btn_frame, text="⚙ Reconfigure",
            font=("Arial", 9), bg="#0056b3", fg="#fff",
            relief="flat", padx=10, pady=5, cursor="hand2",
            command=_reconfigure,
        ).pack(side=tk.LEFT, padx=(0, 6))
        tk.Button(
            btn_frame, text="✕ Dismiss",
            font=("Arial", 9), bg=_CLR["btn_clear"], fg="#fff",
            relief="flat", padx=10, pady=5, cursor="hand2",
            command=_dismiss,
        ).pack(side=tk.LEFT)

        # Centre the dialog over the main window
        self.update_idletasks()
        w, h = 560, 320
        x = self.winfo_x() + (self.winfo_width() - w) // 2
        y = self.winfo_y() + (self.winfo_height() - h) // 2
        dlg.geometry(f"{w}x{h}+{x}+{y}")

        # Log a summary in the output panel too.
        self._log_line(
            f"[GUI] ⚠ T32 not detected on port {port} for {_T32_DETECT_WARN_S}s "
            "– retry dialog opened.  Check config.t32 RCL settings and permissions.",
            "warn",
        )

    # ------------------------------------------------------------------ GUI state persistence

    def _load_gui_state(self) -> None:
        """Load persisted GUI state from gui_state.json (best-effort)."""
        if not _GUI_STATE_PATH.is_file():
            return
        try:
            data: Dict[str, Any] = json.loads(
                _GUI_STATE_PATH.read_text(encoding="utf-8")
            )
        except Exception:
            return

        def _set(var: tk.Variable, key: str) -> None:
            if key in data:
                try:
                    var.set(data[key])
                except Exception:
                    pass

        _set(self._mode_var,        "mode")
        _set(self._port_var,        "port")
        _set(self._auto_launch_var, "auto_launch")
        _set(self._cmm_var,         "cmm")
        _set(self._verbose_var,     "verbose")

        # Sync the thread-safe port copy after restoring the Tkinter variable.
        self._on_port_var_changed()
        _set(self._disc_pattern_var,  "disc_pattern")
        _set(self._disc_module_var,   "disc_module")
        _set(self._disc_bp_var,       "disc_bp")
        _set(self._disc_suite_var,    "disc_suite")
        _set(self._disc_max_sym_var,  "disc_max_sym")
        _set(self._disc_resolve_var,  "disc_resolve")
        _set(self._disc_verbose_var,  "disc_verbose")
        _set(self._disc_output_var,   "disc_out_dir")
        _set(self._tc_py_name_var,    "tc_py_name")
        _set(self._tc_py_dir_var,     "tc_py_dir")
        _set(self._tc_json_name_var,  "tc_json_name")
        _set(self._tc_json_dir_var,   "tc_json_dir")

        # Restore discovery queue
        raw_queue = data.get("disc_queue", [])
        if isinstance(raw_queue, list):
            self._disc_queue = [e for e in raw_queue if isinstance(e, dict)]
            self._refresh_disc_queue_list()

        # Restore C source files registry
        raw_c_files = data.get("c_files", [])
        if isinstance(raw_c_files, list):
            self._c_files = [
                Path(p) for p in raw_c_files if isinstance(p, str)
            ]
            self._c_refresh_listbox()

        self._log_line("[GUI] GUI state restored from gui_state.json", "debug")

    def _save_gui_state(self) -> None:
        """Persist current GUI field values to gui_state.json."""
        data: Dict[str, Any] = {
            "mode":         self._mode_var.get(),
            "port":         self._port_var.get(),
            "auto_launch":  self._auto_launch_var.get(),
            "cmm":          self._cmm_var.get(),
            "verbose":      self._verbose_var.get(),
            "disc_pattern": self._disc_pattern_var.get(),
            "disc_module":  self._disc_module_var.get(),
            "disc_bp":      self._disc_bp_var.get(),
            "disc_suite":   self._disc_suite_var.get(),
            "disc_max_sym": self._disc_max_sym_var.get(),
            "disc_resolve": self._disc_resolve_var.get(),
            "disc_verbose": self._disc_verbose_var.get(),
            "disc_out_dir": self._disc_output_var.get(),
            "tc_py_name":   self._tc_py_name_var.get(),
            "tc_py_dir":    self._tc_py_dir_var.get(),
            "tc_json_name": self._tc_json_name_var.get(),
            "tc_json_dir":  self._tc_json_dir_var.get(),
            "disc_queue":   self._disc_queue,
            "c_files":      [str(p) for p in self._c_files],
        }
        try:
            _GUI_STATE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
            self._log_line(f"[GUI] GUI state saved to {_GUI_STATE_PATH}", "debug")
        except Exception as exc:
            self._log_line(f"[GUI] Could not save GUI state: {exc}", "warn")

    def _on_close(self) -> None:
        """Save GUI state and stop background threads before closing."""
        self._t32_monitor_stop.set()
        self._save_gui_state()
        self.destroy()

    # ------------------------------------------------------------------ countdown kill

    def _countdown_kill_t32(self, proc: Optional[subprocess.Popen]) -> None:
        """Show a 5-second countdown popup, then force-kill Trace32."""
        dlg = tk.Toplevel(self)
        dlg.title("Stopping Trace32 …")
        dlg.resizable(False, False)
        dlg.grab_set()
        dlg.configure(bg="#fff3cd")

        tk.Label(
            dlg,
            text="Trace32 did not exit gracefully.\nForce-killing in:",
            font=("Arial", 11), bg="#fff3cd", pady=10, padx=20,
        ).pack()

        count_var = tk.StringVar(value="5")
        count_lbl = tk.Label(
            dlg, textvariable=count_var,
            font=("Arial", 36, "bold"), fg="#c0392b", bg="#fff3cd",
        )
        count_lbl.pack(pady=(0, 10))

        cancelled = threading.Event()

        def _cancel() -> None:
            cancelled.set()
            dlg.destroy()

        tk.Button(
            dlg, text="Cancel (T32 already closed)",
            font=("Arial", 9), bg=_CLR["btn_clear"], fg="#fff",
            relief="flat", padx=10, pady=4,
            command=_cancel,
        ).pack(pady=(0, 12))

        # Centre the dialog over the main window
        self.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 300) // 2
        y = self.winfo_y() + (self.winfo_height() - 180) // 2
        dlg.geometry(f"300x180+{x}+{y}")

        remaining = [5]

        def _tick() -> None:
            if cancelled.is_set():
                return
            remaining[0] -= 1
            count_var.set(str(remaining[0]))
            if remaining[0] <= 0:
                dlg.destroy()
                self._force_kill_t32_now(proc)
            else:
                dlg.after(1000, _tick)

        dlg.after(1000, _tick)
        self.wait_window(dlg)

    def _force_kill_t32_now(self, proc: Optional[subprocess.Popen]) -> None:
        """Immediately kill Trace32 (managed process or by name)."""
        if proc is not None and proc.poll() is None:
            try:
                proc.kill()
                proc.wait(timeout=3)
            except Exception as exc:
                self._log_line(f"[GUI] Force-kill failed: {exc}", "error")
            finally:
                self._t32_process = None
            self._log_line("[GUI] Trace32 force-killed (PID kill).", "warn")
            return

        killed = self._kill_t32_by_name()
        if killed:
            self._log_line("[GUI] Trace32 force-killed (by name).", "warn")
        else:
            self._log_line("[GUI] No Trace32 process found to kill.", "info")
        self._t32_process = None

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
            "  • Symbol Discovery Queue (save & batch-run configs)\n"
            "  • Test Creator (new Python and JSON suites from templates)\n"
            "  • Reports Browser (view all historical HTML reports)\n"
            "  • C Source Files (register *.c files, extract symbols, sync with T32)\n"
            "  • T32 status LED (green=connected / red=disconnected)\n"
            "  • 30-second T32 detection timeout with retry / reconfigure dialog\n"
            "  • Test running LED (orange=running)\n"
            "  • Persistent GUI state (restored on next launch)\n"
            "  • Edit config.json settings\n"
            "  • Real-time colour-coded output log\n"
            "  • Stop long-running tests at any time\n"
            "  • Force-kill T32 with 5-second countdown\n"
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
