

# 1 Build Information

## 1.a. Dependencies
Please refer to [progman.docx](progman.md) for the tools used to build the software.

Environment variables:
- WindRiver: Per the WindRiver documentation, both `WINDRIVER_TRICORE_TOOLCHAIN_PATH` and `WIND_HOME` need to be defined.
- PATH:
  - If `objcopy` is not available, you may find it in the WindRiver utilities bin folder (such as `\WindRiver\utilities\x86-linux2\bin`) or by installing `binutils` .
  - Required tools such as `make` should be callable, added to PATH.

## 1.b. Make File Options
To build the software, please consider the following one of the following arguments to use with `make <arg>`. Or consider `make all` to build all targets in both modes.

| Target | Clean HWIO lib   | Build HWIO lib | Clean Magna-Test     | Build Magna-Test     |
|--------|------------------|----------------|----------------------|----------------------|
| APPL   | `clean_hwioappl` | `hwioappl`     | `clean_testhwioappl` | `Magna_testhwioappl` |
| BOOT   | `clean_hwioboot` | `hwioboot`     | `clean_testhwioboot` | `Magna_testhwioboot` |
| RPGM   | `clean_hwiorpgm` | `hwiorpgm`     | `clean_testhwiorpgm` | `Magna_testhwiorpgm` |

Please note that these args may change in the future.

[//]: # (# 2 Release Information)
[//]: # (- change log referencing all applicable Product Change Evaluations &#40;PCEs&#41; and Problem Resolution Tracking System &#40;PRTS&#41; resolved; also reference any internal tracking numbers)
[//]: # (- hardware compatibility)
[//]: # (- list of new or changed software interfaces provided to or expected from GM)
[//]: # (- list of unresolved anomalies)
[//]: # (- explanation of unimplemented code and resulting stubs)


