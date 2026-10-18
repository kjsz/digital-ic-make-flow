source [file join [file dirname [info script]] common.tcl]
source [file join $FLOW_DIR route_drc.tcl]
setMultiCpuUsage -localCpu $CPU
# 已保存检查点包含工艺信息。
source $CHECKPOINT_IN
set_interactive_constraint_modes [all_constraint_modes -active]
set_analysis_view -setup view_$SETUP_CORNER -hold view_$HOLD_CORNER
source derates.tcl
# The user has already repaired this snapshot: never reroute or optimize it here.
set count [flow_drc_count reports/manual_route_drc.rpt]
if {$count > 0} {
    flow_drc_failure_snapshot
    error "MANUAL_ROUTE_DRC_UNRESOLVED: $count violations; manual repair not accepted"
}
setExtractRCMode -engine postRoute
reset_parasitics
extractRC
# Restored checkpoints may contain old report destinations; use this attempt only.
timeDesign -postRoute -pathReports -slackReports -numPaths 50 -prefix setup -outDir reports
timeDesign -postRoute -hold -pathReports -slackReports -numPaths 50 -prefix hold -outDir reports
saveDesign $CHECKPOINT_OUT
