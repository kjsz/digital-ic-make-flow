# 布局与普通信号层范围。
setAnalysisMode -analysisType onchipVariation -cppr both
setDelayCalMode -engine default -siAware true
flow_groups
# 本设计优化策略；换设计后自行修改约束与路径组权重。
set_clock_uncertainty -setup 1.0 [all_clocks]
set_clock_uncertainty -hold 1.0 [all_clocks]
set_max_transition 1.2 [current_design]
set_max_transition 0.7 -clock [all_clocks]
set_max_fanout 15 [current_design]
setPathGroupOptions reg2reg -effortLevel high -weight 20
setPathGroupOptions reg2cg -effortLevel high -weight 10
foreach group {in2reg reg2out feedthr} {setPathGroupOptions $group -effortLevel low -weight 0}
setOptMode -ignorePathGroupsForHold {in2reg reg2out feedthr}
setPlaceMode -reset
setPlaceMode -place_global_ignore_scan true -place_global_reorder_scan false -place_global_place_io_pins false
setPlaceMode -place_detail_use_check_drc true -place_detail_legalization_inst_gap 2
setDesignMode -process 180
setRouteMode -earlyGlobalMinRouteLayer 2 -earlyGlobalMaxRouteLayer 5

report_path_groups > reports/path_groups.rpt
place_opt_design
foreach cell {TIEH_7T5P0 TIEL_7T5P0} {setDontUse $cell false}
setTieHiLoMode -prefix Tie -maxFanout 8 -Cell {TIEH_7T5P0 TIEL_7T5P0}
addTieHiLo
foreach cell {TIEH_7T5P0 TIEL_7T5P0} {setDontUse $cell true}

checkFPlan -reportUtil
