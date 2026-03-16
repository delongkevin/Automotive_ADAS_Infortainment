# Makefile details specific for {{TARGET}}

{#
TODO:
  - Fix the move_lst_files
  - Utilize the gnu_util shift to optimize the move_lst_files and maybe the top level makefile

LDFLAGS not included from CMake Build
  -@O=build.txt
  -Xpreprocess-lecl
  -mapfile $(TESTAPP_EXE:.elf=.map)
#}

# ----------------------------
# Phony targets
# ----------------------------
.PHONY: {{TARGET_lower}} Magna_test{{TARGET_lower}} clean_{{TARGET_lower}} clean_test{{TARGET_lower}} move_lst_files

# ----------------------------
# Common Makefile inclusion
# ----------------------------
{%- set include_path = "../HWIODeliverable/common.mk" if lib_only else "../common.mk" %}
include {{ include_path }}

# ----------------------------
# Project Specific Flag Updates
# ----------------------------
BASE_MACROS += -DAPP_SW=GM_VIP_{{TARGET_short}}

TARGET_SPECIFIC_CFLAGS = \
{%- if TARGET == 'HWIOAPPL' %}
    -DAdc_Config=Adc_Config_EcucPartition \
    -DBUILD_AURIX \
    -DCALCULATE_SUPERVISORMODE_EXECUTION_TIME \
    -DDISABLE_IFX_CFG_SSW_BMHD_APPL \
    -DDma_Config=Dma_Config_EcucPartition \
    -DENABLE_FIE_TRAP \
    -DENABLE_GLUELAYER \
    -DENABLE_IE_TRAP_HOOK \
    -DENABLE_NMI_TRAP_HOOK_APP \
    -DENABLE_PLATFORM_BIST_RESULT=1 \
    -DENABLE_PRINT_SDLADAPTOR \
    -DENABLE_REGISTER_PROTECTION \
    -DENABLE_SDL_FAULT_REPORTING \
    -DERRORMGR_ACTIVE \
    -DHARDWARE_CRC_ENABLE=1 \
    -DLIBMAGNA_EYEQ_ACTIVE \
    -DMAGNABASESW_USE_MCAL \
    -DOS_TASK_MODE=USER_MODE \
    -DROUNDING_MODE_TO_ZERO \
    -DRTE_APPLICATION_HEADER_FILE \
    -DSIGNALMGR_ASIL_RATING_B \
    -DSIGNALMGR_ASIL_RATING_QM \
    -DSTACK_PATTERN_INITIALIZATION \
    -DUART_DRIVER_USE_ILLD=0 \
    -DUART_RXBUFF_20K=1 \
    -DhssTPS2H160 \
{%- elif TARGET == 'HWIOBOOT' %}
    -DBUILD_AURIX \
    -DDma_Config=Dma_Config_EcucPartition \
    -DENABLE_ASSERT_TRAP_HOOK \
    -DENABLE_BE_TRAP_HOOK \
    -DENABLE_CME_TRAP_HOOK \
    -DENABLE_IE_TRAP_BOOT_HOOK \
    -DENABLE_IPE_TRAP_HOOK \
    -DENABLE_NMI_TRAP_HOOK \
    -DENABLE_SYSCALL_CPU0_TRAP_HOOK \
    -DHARDWARE_CRC_ENABLE=0 \
    -DIFX_CFG_SSW_DISABLE_RESET_READ_CLEAR \
    -DIFX_CFG_SSW_ENABLE_LBIST=1 \
    -DIFX_CFG_SSW_ENABLE_MBIST=1 \
    -DIFX_CFG_SSW_ENABLE_MBIST_DSPRS_DMARAM=1 \
    -DIFX_CFG_SSW_ENABLE_SAFETY_LIBRARY_TESTS=1 \
    -DIFX_MEM_STAND_ALONE \
    -DOS_TASK_MODE=SUPERVISOR_MODE \
    -DRTE_APPLICATION_HEADER_FILE \
{%- elif TARGET == 'HWIORPGM' %}
    -DDISABLE_IFX_CFG_SSW_BMHD_APPL \
    -DENABLE_ASSERT_TRAP_HOOK \
    -DENABLE_BE_TRAP_HOOK \
    -DENABLE_CME_TRAP_HOOK \
    -DENABLE_IE_TRAP_BOOT_HOOK \
    -DENABLE_IPE_TRAP_HOOK \
    -DENABLE_NMI_TRAP_HOOK \
    -DENABLE_SYSCALL_CPU0_TRAP_HOOK \
    -DHARDWARE_CRC_ENABLE=0 \
    -DIFX_MEM_STAND_ALONE \
{%- endif %}



TARGET_LDFLAGS = \
    {{TARGET}}.lsl \
{%- if TARGET == 'HWIOAPPL' %}
    -Xremove-unused-sections \
{%- elif TARGET == 'HWIOBOOT' %}
    -Xremove-unused-sections \
{%- elif TARGET == 'HWIORPGM' %}
{%- endif %}

# ----------------------------
# Sources & Includes
# ----------------------------
{{INCLUDES}}

{{HWIO_SRCS}}

{{TEST_INCLUDES}}

{{TEST_SRCS}}

EXTERNAL_LIBS = {{ './Source/app/asr/Os/Implementation/RTAOS.a' if TARGET == 'HWIOAPPL' else '' }} {{libs}}

# ----------------------------
# Names & Directories
# ----------------------------
OBJDIR = {{ './Object' if lib_only == False else './Object_' + TARGET_short }}
PRODUCTS_DIR = {{ './Products' if lib_only == False else './../HWIODeliverable/'+TARGET+'/Products' }}

# Static library name
TARGET_LIB_BASE = $(PRODUCTS_DIR)/{{lib_name}}.a

{%- if lib_only == False %}
# Executable name
TESTAPP_EXE = $(PRODUCTS_DIR)/Magna_Test{{TARGET_short_lower}}.elf
{%- endif %}

# ----------------------------
# Build mode flags aggregation
# ----------------------------
Magna_test{{TARGET_lower}}: INCLUDES += $(TEST_INCLUDES)
Magna_test{{TARGET_lower}}: MAGNA_CFLAGS = $(BASE_MACROS) $(MAGNA_TESTMACRO_CFLAGS_0) $(MAGNA_WDG_MACRO) $(MAGNA_TESTMACRO_CFLAGS_1) $(MAGNA_TESTMACRO_CFLAGS_2) $(MAGNA_TESTMACRO_CFLAGS_3)
{{TARGET_lower}}: MAGNA_CFLAGS = $(BASE_MACROS)

CFLAGS = $(MAGNA_CFLAGS) $(BASE_CFLAGS) $(TARGET_SPECIFIC_CFLAGS)

# ----------------------------
# Object lists
# ----------------------------
OBJS = $(HWIO_SRCS:$(SRCDIR)%=$(OBJDIR)%)
OBJS := $(OBJS:.c=.o)
OBJS := $(OBJS:.s=.o)

TESTOBJS = $(TEST_SRCS:$(TEST_SRCDIR)%=$(TEST_OBJDIR)%)
TESTOBJS := $(TESTOBJS:.c=.o)

# ----------------------------
# Helpers
# ----------------------------
{%- if lib_only == False %}
move_lst_files:
	@mkdir -p $(LISTDIR)
	@find $(OBJDIR) -name '*.lst' | while read file; do \
		file=$$(echo $$file | tr -d '\r'); \
		dest_dir=$(LISTDIR)/$${file#$(OBJDIR)/}; \
		dest_dir=$${dest_dir%/*}; \
		mkdir -p $$dest_dir; \
		mv $$file $$dest_dir; \
	done
{%- endif %}

# Ensure directories exist
$(OBJDIR):
	mkdir -p $(OBJDIR)

$(TEST_OBJDIR):
	mkdir -p $(TEST_OBJDIR)

# ----------------------------
# Compilation rules
# ----------------------------
$(OBJDIR)/%.o: $(SRCDIR)/%.s | $(OBJDIR)
	@echo "Compiling $< to $@"
	@mkdir -p $(dir $@)
	$(CC) $(CFLAGS) $(INCLUDES) -c $< -o $@

# Rule to compile .c files to .o files and generate .lst files
$(OBJDIR)/%.o: $(SRCDIR)/%.c | $(OBJDIR)
	@echo "Compiling $< to $@"
	@mkdir -p $(dir $@)
	$(CC) $(CFLAGS) $(INCLUDES) -c $< -o $@

# Rule to compile .c files to .o files and generate .lst files
$(TEST_OBJDIR)/%.o: $(TEST_SRCDIR)/%.c | $(TEST_OBJDIR)
	@echo "Compiling $< to $@"
	@mkdir -p $(dir $@)
	@mkdir -p $(dir $(patsubst $(TEST_OBJDIR)/%, $(TEST_LSTDIR)/%, $@))
	$(CC) $(CFLAGS) $(INCLUDES) -c $< -o $@

# ----------------------------
# Libraries & Linking
# ----------------------------
# Rule to create the static library
{{TARGET_lower}}_build: $(OBJS)
	@echo "Creating static library $@"
	@mkdir -p $(PRODUCTS_DIR)
	$(AR) qc $(TARGET_LIB_BASE) $(OBJS)
{%- if lib_only == False %}
	$(MAKE) move_lst_files
{%- endif %}

# Link the executable from objects + (lib or objs-by-target)
Magna_test{{TARGET_lower}}: $(TESTOBJS) {{TARGET_lower}}_build
	@echo "Linking to create executable $@"
{%- if lib_only == False %}
	$(MAKE) move_lst_files
	@mkdir -p $(PRODUCTS_DIR)
	$(LD) $(LDFLAGS) $(TARGET_LDFLAGS) -o $(TESTAPP_EXE) $(TESTOBJS) $({{ 'OBJS' if TARGET == 'HWIORPGM' else 'TARGET_LIB_BASE' }}) $(EXTERNAL_LIBS)
	@rm -f $(PRODUCTS_DIR)/{{TARGET}}.a  # The static library w/ TestApp flags is not delivered.
	@objcopy -O srec $(TESTAPP_EXE) $(TESTAPP_EXE:.elf=.s19)
	@objcopy -O ihex $(TESTAPP_EXE) $(TESTAPP_EXE:.elf=.hex)
	{%- if TARGET == 'HWIORPGM' %}
	@rm -f $(TESTAPP_EXE)
    {%- endif %}
{%- endif %}

# ----------------------------
# High-level targets
# ----------------------------
## clean and build ... in parallel.
#{{TARGET_lower}}: clean_{{TARGET_lower}} {{TARGET_lower}}_build

# clean and build
{{TARGET_lower}}: {{TARGET_lower}}_build

# Clean before each build
{{TARGET_lower}}_build: clean_{{TARGET_lower}}

# ----------------------------
# Cleaning
# ----------------------------
clean_{{TARGET_lower}}:
	rm -rf $(OBJDIR) $(LISTDIR) $(TEST_OBJDIR) $(TARGET_LIB_BASE) | true

clean_test{{TARGET_lower}}: clean_{{TARGET_lower}}
	@echo "Cleaning Test Application files"
{%- if lib_only == False %}
	rm -rf $(TESTAPP_EXE) $(TESTAPP_EXE:.elf=.map) $(TESTAPP_EXE:.elf=.hex) $(TESTAPP_EXE:.elf=.s19)
{%- endif %}

# ----------------------------
# Dependencies
# ----------------------------
-include $(OBJS:.o=.d)
{%- if TARGET != 'HWIORPGM' %}
-include $(TESTOBJS:.o=.d)
{%- endif %}

# Parsing Details
## Items within cmake build that are intentionally left out of Makefile
### -Xasm-debug-on
