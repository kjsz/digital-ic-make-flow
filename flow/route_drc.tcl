# Innovus 18.10 geometry gate. Calibre signoff checks remain a separate step.
proc flow_drc_count {report_file} {
    file mkdir [file dirname $report_file]
    # Replace old markers with a fresh full-design check, including PG shapes.
    clearDrc
    set_verify_drc_mode -reset
    set_verify_drc_mode -exclude_pg_net false
    verify_drc -check_only all -limit 100000 -report $report_file
    set count 0
    foreach marker [dbGet -e top.markers] {
        if {$marker eq "0x0" || $marker eq ""} {continue}
        if {![regexp {^0x[0-9a-fA-F]+$} $marker]} {
            error "Unexpected DRC marker query result: $marker"
        }
        incr count
    }
    return $count
}
proc flow_drc_failure_snapshot {} {
    if {[catch {saveDesign drc_failed.enc} message]} {
        puts stderr "FLOW_ERROR: Could not save DRC failure checkpoint: $message"
    }
}
proc flow_route_drc_gate {} {
    set summary [open reports/route_drc_summary.rpt w]
    set count [flow_drc_count reports/route_drc_pass0.rpt]
    puts $summary "pass=0 violations=$count"
    flush $summary
    set passes 0
    while {$count > 0 && $passes < 1} {
        incr passes
        puts "DRC_GATE: $count violations; incremental repair $passes/1"
        # Keep the fresh markers: ecoRoute -fix_drc requires these markers.
        if {[catch {ecoRoute -fix_drc} message options]} {
            close $summary
            flow_drc_failure_snapshot
            return -options $options $message
        }
        set count [flow_drc_count [format {reports/route_drc_pass%d.rpt} $passes]]
        puts $summary "pass=$passes violations=$count"
        flush $summary
    }
    close $summary
    if {$count > 0} {
        flow_drc_failure_snapshot
        puts "FLOW_DRC_WARNING: 布线仍有 $count 条违例（修复 $passes 次），继续收尾，请运行 Calibre 并手工 ECO。"
    }
    puts "DRC 检查结束：修复 $passes 次，剩余 $count 条。"
    return $passes
}
proc flow_chipfinish_drc_gate {} {
    set count [flow_drc_count reports/chipfinish_drc.rpt]
    set f [open reports/chipfinish_drc_summary.rpt w]
    puts $f "violations=$count"
    close $f
    if {$count > 0} {
        flow_drc_failure_snapshot
        puts "FLOW_DRC_WARNING: 收尾后仍有 $count 条违例；继续导出，请检查 Calibre。"
    }
}
