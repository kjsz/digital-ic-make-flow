# 工作区 ECO：editable 留在 eco/，最终导出直接写 chipfinish/；验证后再提交。
proc eco_save {} {
    global ECO_DIR
    file delete -force [file join $ECO_DIR exported.json]
    set f [open [file join $ECO_DIR draft-pending] w]
    puts $f "尚未导出当前数据库草稿"
    close $f
    saveDesign [file join $ECO_DIR editable.enc]
    puts "已保存 editable 草稿；请 eco_export 后验证工作区。"
}
proc eco_export {{message "手工 ECO"}} {
    global ECO_DIR ECO_TOKEN FINAL_DIR FLOW_DIR ROOT CHECKPOINT_OUT NETLIST_OUT DESIGN_NAME TOP_MODULE SDC_OUT SDF_OUT GDS_MAP LVS_PHYSICAL_CELLS POWER_NET GROUND_NET lefDefoutVersion
    eco_save
    set previous [pwd]
    file mkdir [file join $FINAL_DIR reports]
    cd $FINAL_DIR
    # 导出失败不得继续用上一版完成标记验证半成品。
    set f [open result.json w]
    puts $f {{"stage":"chipfinish","status":"RUNNING","reason":"ECO export in progress"}}
    close $f
    puts "重新生成工作区网表/版图；直接文本修改若需保留，请事先提交或另存。"
    set failed [catch {
        source [file join $FLOW_DIR route_drc.tcl]
        foreach path [glob -nocomplain reports/setup* reports/hold*] {file delete -force $path}
        source [file join $ROOT scripts innovus chipfinish.tcl]
        timeDesign -postRoute -pathReports -drvReports -slackReports -numPaths 50 -prefix setup -outDir reports
        timeDesign -postRoute -hold -pathReports -slackReports -numPaths 50 -prefix hold -outDir reports
        saveDesign $CHECKPOINT_OUT
        set f [open [file join $ECO_DIR message.txt] w]
        fconfigure $f -encoding utf-8
        puts $f $message
        close $f
    } reason options]
    set restore_failed [catch {source [file join $ECO_DIR editable.enc]} restore_reason]
    cd $previous
    if {$restore_failed} {error "恢复 editable 失败，请退出后重新 make eco：$restore_reason"}
    if {$failed} {puts stderr "FLOW_ERROR: ECO 导出失败：$reason"; return -options $options $reason}
    set f [open [file join $ECO_DIR exported.json] w]
    puts $f [format {"%s"} $ECO_TOKEN]
    close $f
    # GUI 退出后由 Python 核验成功再清除待导出标记。
    puts "chipfinish 工作区导出完成。退出 GUI 后直接 make drc/lvs/pt；验证后 make eco-accept。"
}
puts "eco_save 保存草稿；eco_export {备注} 写入 chipfinish；验证后再提交。"