# Common makefile for different target build flags and variables.

# ----------------------------
# Toolchain
# ----------------------------
CC = dcc
AR = dar
LD = dld

# ----------------------------
# Flags
# ----------------------------
BASE_CFLAGS = -g3 -tTC4DxAMF:cross -W:as:,-l -Xalign-functions=4 -Xdebug-dwarf2 -Xdebug-local-cie -Xdialect-c99 -Xenum-is-short -Xforce-declarations -Xforce-prototypes -Xfp-fast -Xlicense-wait -Xmismatch-warning=2 -Xno-common -XO -Xoptimized-debug-on -Xparse-size=16000 -Xpass-source -Xsection-split=1 -Xshow-configuration=1 -Xtc-fdiv-exc-hook
BASE_MACROS = -DBOARD_CFG=2 -DGM_VIP_A0=0 -DGM_VIP_A2=2 -DDISABLE_TRICORE0_DCACHE -DDISABLE_TRICORE1_DCACHE -DDISABLE_TRICORE2_DCACHE -DDISABLE_TRICORE3_DCACHE -DDISABLE_TRICORE4_DCACHE -DDISABLE_TRICORE5_DCACHE -DMcu_Config=Mcu_Config_EcucPartition -DOSTYPE=RTA_OS -DPmic_Config=Pmic_Config_EcucPartition -DPort_Config=Port_Config_EcucPartition -DSmu_Config=Smu_Config_EcucPartition -DSpi_Config=Spi_Config_EcucPartition -DWdg_17_Wtu_Config=Wdg_17_Wtu_Config_EcucPartition -DWdg_17_Pmic_Config=Wdg_17_Pmic_Config_EcucPartition -DLOG_LEVEL=LOG_NONE -DVERSION_HANDLING=0 -DVERSION_INFO_PRINT=0 -DSUPERVISOR_MODE=0 -DUSER_MODE=1 -DSUPERVISOR_MODE=0 -DUSER_MODE=1 -DSOC_TI=1 -DSOC_INFINEON=2 -DBASE_SOC=2 -DDIETEMP_DISABLE=0 -DDIETEMP_ENABLE=1 -DDIETEMP_USE_HW_WARNING_STATUS=DIETEMP_DISABLE -DVERSION_HANDLING=1

MAGNA_TESTMACRO_CFLAGS_0   = -DGM_APPL_DUMMY_IMPL -DTEST_APP_ENABLE -DTEST_BOOT -DTEST_TIMER_EN -DLOG_LEVEL=LOG_DEBUG -DLOG_USE_COLOR
MAGNA_TESTMACRO_CFLAGS_1   = -DCONFIG_REGISTER_TESTING -DTEST_BATTCONNSTATUS_LLSI -DTEST_CONFIGREGTEST_LLSI -DTEST_DIO_HWIO_LLSI -DTEST_INTERNAL_BUS_STATUS_LLSI -DTEST_POWER_DOWN_LLSI -DTEST_POWER_UP_LLSI
MAGNA_TESTMACRO_CFLAGS_2   = -DTEST_ADC_LLSI -DTEST_BINVDM_LLSI -DTEST_CAN_ENABLE -DTEST_CLKSTATUS_LLSI -DTEST_DMA_LLSI -DTEST_EXTWDT_LLSI -DTEST_HWCRC_LLSI -DTEST_INSTRUMENTATION_LLSI -DTEST_LOCK_STEP_LLSI -DTEST_WAKEUP_LLSI -DTEST_BIST_LLSI
# MAGNA_TESTMACRO_CFLAGS_3 for failure test cases - to not be enabled by default.
# MAGNA_TESTMACRO_CFLAGS_3 = -DTEST_ADDRMATCHTOOL_LLSI -DTEST_ECC_RAM_LLSI -DTEST_ECC_ROM_LLSI -DTEST_ERRORMGR -DTEST_ERRMGRWRAPPER

# To enable/disable External watchdog, utilize the below flag
MAGNA_WDG_MACRO = -DPMIC_EXT_WDG_ENABLE

# Linker flags
LDFLAGS = -m26 -tTC4DxAMF:cross -Xcheck-overlapping -Xstop-on-redeclaration=0 -Xstack-usage=0xF -Xsection-align=4 -Xextern-in-place -Xelf -lc $(LDFLAG_ARGS)

# ----------------------------
# Names & Directories
# ----------------------------
SRCDIR       = ./Source
TEST_SRCDIR  = ./Test
TEST_OBJDIR  = ./Object/Test
LISTDIR      = ./List

