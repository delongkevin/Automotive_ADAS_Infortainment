"""
conftest.py – inject lauterbach.trace32.rcl stubs before any test imports.
This allows the framework to be imported in CI without the Lauterbach library
installed.
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
