"""
Minimal setup.py for GM_VIP_Automation_Framework.

Install as an editable (development) package so that test_sanity.py and
other scripts can import the framework from any working directory:

    pip install -e .

After installation you can run the sanity tests from anywhere:

    python /path/to/GM_VIP_Automation_Framework/tests/test_sanity.py
    pytest GM_VIP_Automation_Framework/tests/test_sanity.py

No hardware or Lauterbach library is required to run the tests; the
lauterbach.trace32.rcl dependency is mocked inside the test file.

GUI application
---------------
After installation, launch the graphical user interface with::

    gm-vip-gui

or via the main entry point::

    python GM_VIP_Automation_Framework/main.py --gui

The GUI requires tkinter, which ships with every standard CPython
distribution.  On Debian/Ubuntu it can be installed with::

    sudo apt-get install python3-tk
"""

from setuptools import find_packages, setup

setup(
    name="GM-VIP-Automation-Framework",
    version="0.1.0",
    description="Python Trace32 API framework for GM VIP Automation test environments",
    packages=find_packages(exclude=["tests", "*.tests", "*.tests.*"]),
    python_requires=">=3.9",
    install_requires=[
        # The official Lauterbach Python library.
        # Only needed when connecting to real Trace32 hardware.
        # The test suite mocks this dependency so no install is required
        # to run tests in CI or on a development machine without hardware.
        "lauterbach.trace32.rcl>=1.0.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0",
        ],
    },
    entry_points={
        "console_scripts": [
            # CLI entry point (same as: python GM_VIP_Automation_Framework/main.py)
            "gm-vip=GM_VIP_Automation_Framework.main:main",
            # GUI entry point (same as: python GM_VIP_Automation_Framework/gui.py)
            "gm-vip-gui=GM_VIP_Automation_Framework.gui:main",
        ],
    },
)
