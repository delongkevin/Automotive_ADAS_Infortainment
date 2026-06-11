"""
Minimal setup.py for Automation_Framework.

Install as an editable (development) package so that test_sanity.py and
other scripts can import the framework from any working directory:

    pip install -e .

After installation you can run the sanity tests from anywhere:

    python /path/to/Automation_Framework/tests/test_sanity.py
    pytest Automation_Framework/tests/test_sanity.py

No hardware or Lauterbach library is required to run the tests; the
lauterbach.trace32.rcl dependency is mocked inside the test file.

GUI application
---------------
After installation, launch the graphical user interface with::

    automation-framework-gui

or via the main entry point::

    python Automation_Framework/main.py --gui

The GUI requires tkinter, which ships with every standard CPython
distribution.  On Debian/Ubuntu it can be installed with::

    sudo apt-get install python3-tk
"""

from setuptools import find_packages, setup

setup(
    name="Automation-Framework",
    version="0.1.0",
    description="Python Trace32 API framework for Automation test environments",
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
            # CLI entry point (same as: python Automation_Framework/main.py)
            "automation-framework=Automation_Framework.main:main",
            # GUI entry point (same as: python Automation_Framework/gui.py)
            "automation-framework-gui=Automation_Framework.gui:main",
        ],
    },
)
