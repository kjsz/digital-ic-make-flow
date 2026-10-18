# Generated config is an input snapshot in the stage work directory.
source config.tcl
proc flow_require_file {path} {
    if {![file isfile $path] || [file size $path] == 0} {error "Missing/empty input: $path"}
}
proc flow_groups {} {
    set reg [filter_collection [all_registers] {is_integrated_clock_gating_cell != true}]
    set gate [filter_collection [all_registers] {is_integrated_clock_gating_cell == true}]
    reset_path_group -all
    group_path -name reg2reg -from $reg -to $reg
    group_path -name in2reg -from [all_inputs]
    group_path -name reg2out -to [all_outputs]
    group_path -name feedthr -from [all_inputs] -to [all_outputs]
    group_path -name reg2cg -from $reg -to $gate
}
proc flow_done {} {
    set f [open tool.done w]
    puts $f "FLOW_DONE"
    close $f
}
