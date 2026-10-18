# 名称与时钟：新设计必须填写。TECH 为当前工艺标识，不用于多工艺切换。
PROJECT_NAME :=
DESIGN_NAME :=
TOP_MODULE :=
TECH := gf180mcu
CLOCK_NAME :=
CLOCK_PORT = $(CLOCK_NAME)
RTL_LIST := rtl/files.f
INCLUDE_DIRS := rtl
TB_LIST := tb/files.f
TB_TOP :=
DUT_INSTANCE :=
TIMESCALE := 1ns/1ps
GATE_STAGE := dc
RTL_MODELS :=
# 形状必须明确；pin 请填写 scripts/innovus/floorplan.tcl。
FLOORPLAN_MODE :=
CORE_WIDTH :=
CORE_HEIGHT :=
CORE_MARGIN :=
# 示例：rectangle，200，6400，1.12 1.12 1.12 1.12
# custom 时直接编辑 floorplan.tcl 内自定义形状区域。
POWER_NET := VDD
GROUND_NET := VSS
# 电源方案与尺寸直接编辑 powerplan.tcl，不由 check 审核。
CTS_MAX_TRANSITION := 0.7
CTS_TARGET_SKEW := 0.1
CTS_MAX_FANOUT := 15
# DC 完整脚本：scripts/dc.tcl；Innovus：scripts/innovus/*.tcl。
# 可选波形配置：VERDI := verdi -sswr $(abspath debug/signal.rc)