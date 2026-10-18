# Tool commands are overridable; framework/work paths are fixed.
PYTHON ?= python3
VCS ?= vcs
VERDI ?= verdi
# Coverage viewer has its own command; waveform -sswr options do not apply.
VERDI_COV ?= verdi
# Technology-specific RTL model switches; gate timing stages do not use them.
RTL_DEFINES ?=
VERDI_HOME ?= $(NOVAS_HOME)
DC_SHELL ?= dc_shell
FM_SHELL ?= fm_shell
INNOVUS ?= innovus
CALIBREDRV ?= calibredrv
V2LVS ?= v2lvs
STARXTRACT ?= StarXtract
PT_SHELL ?= pt_shell
CPU ?= 8
GUI ?= 1
FORCE ?= 0
STAGE ?=
# Fallback for older project configs; current config.mk defines this alias.
CLOCK_PORT ?= $(CLOCK_NAME)
export CTS_MAX_TRANSITION CTS_TARGET_SKEW CTS_MAX_FANOUT
export PROJECT_NAME DESIGN_NAME TOP_MODULE TECH RTL_LIST TB_LIST TB_TOP DUT_INSTANCE CLOCK_NAME CLOCK_PORT INCLUDE_DIRS
export FLOORPLAN_MODE CORE_WIDTH CORE_HEIGHT CORE_MARGIN
export POWER_NET GROUND_NET RTL_MODELS GATE_STAGE TIMESCALE
export SYN_LIBS LEFS GDS_FILES GDS_MAP SIM_LIBS LVS_LIBS CDL_FILES CORNERS SETUP_CORNER HOLD_CORNER
export PYTHON VCS VERDI VERDI_COV RTL_DEFINES VERDI_HOME DC_SHELL FM_SHELL INNOVUS CALIBREDRV V2LVS STARXTRACT PT_SHELL CPU GUI FORCE STAGE
export FLOW_GOALS := $(MAKECMDGOALS)

# Optional project-maintained layout/source cell-name mapping.
HCELL_FILE ?=
export HCELL_FILE

# Rerun only these visited stages; FORCE=1 still reruns all visited stages.
FORCE_STAGE ?=
export FORCE_STAGE

# 指定回退提交编号；留空回到父版本。
REV ?=
export REV

# 可选 Calibre/Innovus 集成入口，留空跳过。
CALIBRE_INNOVUS_TCL ?=
export CALIBRE_INNOVUS_TCL
