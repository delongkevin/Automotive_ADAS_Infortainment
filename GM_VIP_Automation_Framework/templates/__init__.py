"""
GM VIP Automation Framework – Templates
========================================
The ``templates`` sub-package ships ready-to-copy Python source files that
demonstrate common test-bench patterns.

Templates
---------
- :mod:`.connect_t32_running` – Connect to a Trace32 instance that is already
  running; all settings are read from ``config.json``.
- :mod:`.connect_t32_launch` – Launch a new Trace32 process from paths defined
  in ``config.json``, then connect.
- :mod:`.capl_test_case_template` – Map a CAPL test case to Python, recording
  breakpoints, variable reads/writes, and symbol states for a test report.
"""
