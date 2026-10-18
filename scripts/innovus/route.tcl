# 普通信号 M2～M5，默认采用 LEF 线宽；不占用 MetalTop。
setDontUse ANTENNA_7T5P0 false
setNanoRouteMode -routeBottomRoutingLayer 2 -routeTopRoutingLayer 5
setNanoRouteMode -drouteUseMultiCutViaEffort medium -drouteFixAntenna true -routeInsertAntennaDiode true -routeAntennaCellName ANTENNA_7T5P0
setNanoRouteMode -routewithTimingDriven true -routewithsiDriven true -drouteEndIteration 70
setNanoRouteMode -drouteMinslackForWireOptimization 0.1
# 按工具版本和 pin 接入需求选择，默认不启用：
# setNanoRouteMode -routeAutoTuneOptionsForAdvancedDesign true
# setNanoRouteMode -routeWithViaOnlyForstandardcellPin 1:1 -routeWithViaInPin 1:1
setAnalysisMode -analysisType onchipVariation -cppr both
setDelayCalMode -siAware true
routeDesign -globalDetail
setExtractRCMode -engine postRoute
reset_parasitics
extractRC
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
timeDesign -postRoute -drvReports -slackReports -prefix before_opt -outDir reports
setOptMode -fixCap true -fixTran true -fixFanoutLoad true
optDesign -postRoute
optDesign -postRoute -drv
optDesign -postRoute -incr
optDesign -postRoute -hold
optDesign -postRoute -hold -incr
set drc_repair_passes [flow_route_drc_gate]
setDontUse ANTENNA_7T5P0 true
if {$drc_repair_passes > 0} {reset_parasitics; extractRC}