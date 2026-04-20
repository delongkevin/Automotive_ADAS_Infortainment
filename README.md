# Automotive ADAS + Infotainment Repository Layout

This repository is consolidated for a consistent OEM flow across GM and Stellantis automotive software programs.

## Consolidated hierarchy

```text
Automotive_ADAS_Infortainment/
├── OEM/
│   ├── GM/
│   │   └── GM_VIP_Automation/          # GM center-stack radio automation assets
│   └── Stellantis/
│       └── STLA_SWTest/                # Stellantis ADAS/CVADAS test assets
├── GM_VIP_Automation_Framework/        # Shared Python Trace32 automation framework
├── .github/workflows/                  # CI/CD workflows updated to OEM paths
└── setup.py                            # Framework packaging entry
```

## Program mapping

- **GM (Infotainment / Radio):** `OEM/GM/GM_VIP_Automation`
- **Stellantis (ADAS / CVADAS):** `OEM/Stellantis/STLA_SWTest`
- **Shared automation framework:** `GM_VIP_Automation_Framework`

## Notes

- CI/CD workflows in `.github/workflows` now reference the consolidated OEM paths.
- Existing framework package/module naming (`GM_VIP_Automation_Framework`) is preserved for compatibility.
