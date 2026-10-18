# editable 始终是不含本轮 filler/decap 的版本；finish 后自动恢复它供继续编辑。
proc eco_save {} {
    global ECO_DIR
    file delete -force [file join $ECO_DIR exported.json]
    saveDesign [file join $ECO_DIR editable.enc]
    puts "已保存可编辑草稿；要生成下游版本请执行 eco_export {备注}。"
}
proc eco_export {{message "手工 ECO"}} {
    global ECO_DIR ECO_TOKEN FLOW_DIR ROOT CHECKPOINT_OUT NETLIST_OUT DESIGN_NAME TOP_MODULE SDC_OUT SDF_OUT GDS_MAP LVS_PHYSICAL_CELLS POWER_NET GROUND_NET lefDefoutVersion
    eco_save
    set previous [pwd]
    cd $ECO_DIR
    set failed [catch {
        source [file join $FLOW_DIR route_drc.tcl]
        # 清除上一轮报告，避免压缩与未压缩旧文本混用。
        foreach path [glob -nocomplain reports/setup* reports/hold*] {file delete -force $path}
        source [file join $ROOT scripts innovus chipfinish.tcl]
        timeDesign -postRoute -pathReports -drvReports -slackReports -numPaths 50 -prefix setup -outDir reports
        timeDesign -postRoute -hold -pathReports -slackReports -numPaths 50 -prefix hold -outDir reports
        saveDesign $CHECKPOINT_OUT
        set f [open message.txt w]
        fconfigure $f -encoding utf-8
        puts $f $message
        close $f
    } reason options]
    # 即使收尾失败，也恢复 finish 前数据库，下一次不会重复填充。
    set restore_failed [catch {source [file join $ECO_DIR editable.enc]} restore_reason]
    cd $previous
    if {$restore_failed} {error "无法恢复可编辑数据库，请退出后重新 make eco：$restore_reason"}
    if {$failed} {puts stderr "FLOW_ERROR: ECO 导出失败：$reason"; return -options $options $reason}
    set f [open [file join $ECO_DIR exported.json] w]
    puts $f [format {"%s"} $ECO_TOKEN]
    close $f
    puts "收尾与导出完成，已恢复 finish 前编辑状态。退出后 make eco-accept 自动提交 Git 版本。"
    puts "若继续修改，请重新 eco_export；eco_save 会撤销本次待接受标记。"
}
puts "ECO：eco_save 保存草稿；eco_export {备注} 保存、收尾和导出；退出后 make eco-accept。"