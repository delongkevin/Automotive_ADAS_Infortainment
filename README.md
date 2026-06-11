# Automotive ADAS + Infotainment Repository Layout

This repository is consolidated for a consistent flow across multiple OEM automotive software programs.

## Consolidated hierarchy

```text
Automotive_ADAS_Infortainment/
├── OEM/
│   ├── OEM_A/
│   │   └── Infotainment_Automation/          # Infotainment automation assets
│   └── OEM_B/
│       └── ADAS_SWTest/                # ADAS/CVADAS test assets
├── Automation_Framework/        # Shared Python Trace32 automation framework
├── .github/workflows/                  # CI/CD workflows updated to OEM paths
└── setup.py                            # Framework packaging entry
```

## Program mapping

- **OEM A (Infotainment / Radio):** `OEM/OEM_A/Infotainment_Automation`
- **OEM B (ADAS / CVADAS):** `OEM/OEM_B/ADAS_SWTest`
- **Shared automation framework:** `Automation_Framework`

## Notes

- CI/CD workflows in `.github/workflows` now reference the consolidated OEM paths.
- Existing framework package/module naming (`Automation_Framework`) is preserved for compatibility.
