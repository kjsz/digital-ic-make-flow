source config.tcl
set search_path [concat $search_path [list $TECH_DIR] $INCLUDE_DIRS]
set target_library $SYN_LIBS
set link_library [concat [list *] $SYN_LIBS]
set_host_options -max_cores $CPU
define_design_lib WORK -path ./hdl
set_svf design.svf
analyze -format sverilog $RTL_FILES
elaborate $TOP_MODULE
current_design $TOP_MODULE
if {![link] || ![check_design]} {error "Synthesis link/check_design failed"}
# 单元禁用与库相关；更换工艺时在此统一调整。
foreach pattern {BUF_X1_7T5P0 BUF_X2_7T5P0 BUF_X16_7T5P0 BUF_X20_7T5P0
    FILL* FILLCAP* BUFZ_X1_7T5P0 BUFZ_X2_7T5P0 BUFZ_X16_7T5P0
    ANTENNA_7T5P0 CLK* ENDCAP* INV_X1_7T5P0 INV_X2_7T5P0 INV_X16_7T5P0
    INV_X20_7T5P0 TIE* INVZ_X1_7T5P0 INVZ_X2_7T5P0 INVZ_X16_7T5P0 DLY* HOLD*} {
    set cells [get_lib_cells -quiet */$pattern]
    if {[sizeof_collection $cells]} {set_dont_use $cells}
}

# 时钟、I/O 约束和综合策略集中在下方。
# BEGIN DESIGN_CONSTRAINTS
# 下方为设计约束参考，按实际设计取消注释并修改。
# 可以直接替换为自己的约束，不逐条审核数值。
# 不需要的参考命令可以删除。
# TOP_MODULE、DESIGN_NAME、CLOCK_NAME、CLOCK_PORT 来自 config.mk。

# create_clock -name $CLOCK_NAME -period 24 [get_ports $CLOCK_PORT]
# set_clock_uncertainty -setup 1.0 [get_clocks $CLOCK_NAME]
# set_clock_uncertainty -hold 0.5 [get_clocks $CLOCK_NAME]
# set_clock_transition 0.7 [get_clocks $CLOCK_NAME]
# set_input_delay 7.2 -clock $CLOCK_NAME [remove_from_collection [all_inputs] [get_ports $CLOCK_PORT]]
# set_output_delay 7.2 -clock $CLOCK_NAME [all_outputs]
# set_max_fanout 24 [current_design]
# set_max_transition 1.5 [current_design]
# set_max_area 0
# set_isolate_ports -type buffer [all_outputs]
# set_fix_multiple_port_nets -all -buffer_constants

# END DESIGN_CONSTRAINTS
set_app_var bus_naming_style {%s[%d]}
compile
change_names -rules verilog -hierarchy
set_svf -off
write -format verilog -hierarchy -output $NETLIST_OUT
write_sdc $SDC_OUT
write_sdf $SDF_OUT
report_timing > reports/setup.rpt
report_area > reports/area.rpt
report_constraint -all_violators > reports/constraints.rpt
check_timing > reports/check_timing.rpt
