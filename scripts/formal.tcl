source config.tcl
set search_path [concat $search_path $INCLUDE_DIRS]
set_app_var synopsys_auto_setup true
set_svf $SVF_IN
foreach lib $SYN_LIBS {read_db -technology_library $lib}
read_sverilog -r $RTL_FILES
set_top r:/WORK/$TOP_MODULE
read_verilog -i $NETLIST_IN
set_top i:/WORK/$TOP_MODULE
match
report_unmatched_points > reports/unmatched.rpt
if {![verify]} {
    report_failing_points > reports/failing.rpt
    report_aborted > reports/aborted.rpt
    save_session -replace session
    error "Formality verification failed"
}
save_session -replace session
set f [open reports/verification.rpt w]
puts $f "VERIFICATION PASSED"
close $f
