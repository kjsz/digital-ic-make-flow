source config.tcl
set link_path [concat [list *] $CORNER_DB]
set link_create_black_boxes false
set si_enable_analysis true
set timing_remove_clock_reconvergence_pessimism true
set report_default_significant_digits 6
read_verilog $NETLIST_IN
current_design $TOP_MODULE
if {![link_design $TOP_MODULE]} {error "PrimeTime link failed: $TOP_MODULE"}
# Innovus writes a design-selection command that read_sdc rejects in PT 2018.
# The design was already selected and linked above. Preserve the source SDC.
set sdc_stream [open $SDC_IN r]
set sdc_text [read $sdc_stream]
close $sdc_stream
set pt_sdc_text ""
foreach sdc_line [split $sdc_text "\n"] {
    set sdc_command [string trim $sdc_line]
    if {[regexp {^current_design\s+} $sdc_command]} {
        if {[llength $sdc_command] != 2 || [lindex $sdc_command 1] ne $TOP_MODULE} {
            error "Unexpected current_design command in $SDC_IN: $sdc_line"
        }
        append pt_sdc_text "# Design selection handled by PT entry: $sdc_line\n"
    } else {
        # PT has no get_designs; translate only an exact top-design selection.
        while {[regexp {\[get_designs\s+([^\]]+)\]} $sdc_line selection design_args]} {
            if {[llength $design_args] != 1 || [lindex $design_args 0] ne $TOP_MODULE} {
                error "Unsupported get_designs target in $SDC_IN: $sdc_line"
            }
            set sdc_line [string map [list $selection {[current_design]}] $sdc_line]
        }
        append pt_sdc_text "$sdc_line\n"
    }
}
set pt_sdc_file [file join [pwd] constraints.pt.sdc]
set sdc_stream [open $pt_sdc_file w]
puts -nonewline $sdc_stream $pt_sdc_text
close $sdc_stream
if {![read_sdc $pt_sdc_file]} {
    error "PrimeTime could not completely read $pt_sdc_file; timing analysis aborted"
}
read_parasitics -keep_capacitive_coupling -format spef $SPEF_IN
foreach {kind value} $PT_DERATE {
    lassign [split $kind _] when what
    set_timing_derate -$when -$what $value
}
set_propagated_clock [all_clocks]
# BEGIN PT_POLICY
# 附加约束集中于此；读取成套 SDC 后执行，可按分析角调整。
# Extra PT constraints after reading the paired final SDC.
# Uncomment/edit the needed references, or replace the policy.
# set_clock_uncertainty -setup 1.0 [get_clocks $CLOCK_NAME]
# set_clock_uncertainty -hold 0.5 [get_clocks $CLOCK_NAME]
# Example: use per-CORNER conditions if the chosen timing plan requires them.

# END PT_POLICY
update_timing -full
report_units > reports/units.rpt
check_timing -verbose > reports/check_timing.rpt
report_annotated_parasitics -check > reports/parasitics.rpt
report_analysis_coverage > reports/coverage.rpt
report_disable_timing > reports/disabled.rpt
report_constraint -all_violators -nosplit > reports/constraints.rpt
report_timing -delay_type max -max_paths 1 -nosplit -significant_digits 6 > reports/setup.rpt
report_timing -delay_type min -max_paths 1 -nosplit -significant_digits 6 > reports/hold.rpt
save_session session
