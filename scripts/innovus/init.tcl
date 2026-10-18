# 初始化：工艺库与分析角由 config.mk、tech 配置传入。
set init_lef_file $LEFS
set init_mmmc_file [file normalize mmmc.tcl]
set init_pwr_net $POWER_NET
set init_gnd_net $GROUND_NET
set init_top_cell $TOP_MODULE
set init_verilog $NETLIST_IN
init_design
checkDesign -netlist