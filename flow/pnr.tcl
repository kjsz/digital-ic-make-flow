# 流程入口仅负责恢复、执行阶段脚本和保存；实现命令在 scripts/innovus。
source [file join [file dirname [info script]] common.tcl]
source [file join $FLOW_DIR route_drc.tcl]
setMultiCpuUsage -localCpu $CPU
if {$STAGE ne "init"} {
    source $CHECKPOINT_IN
    set_interactive_constraint_modes [all_constraint_modes -active]
    set_analysis_view -setup view_$SETUP_CORNER -hold view_$HOLD_CORNER
    source derates.tcl
}
source [file join $ROOT scripts innovus ${STAGE}.tcl]
if {$STAGE in {placement cts route chipfinish}} {
    set mode [expr {$STAGE eq "placement" ? "-preCTS" : $STAGE eq "cts" ? "-postCTS" : "-postRoute"}]
    timeDesign $mode -pathReports -drvReports -slackReports -numPaths 50 -prefix setup -outDir reports
    if {$STAGE ne "placement"} {timeDesign $mode -hold -pathReports -slackReports -numPaths 50 -prefix hold -outDir reports}
}
saveDesign $CHECKPOINT_OUT