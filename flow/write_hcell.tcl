set cells [dbGet [dbGet top.insts.isPhysOnly 0 -p].cell.name]
set cells [lsort -unique $cells]
set f [open hcell_list w]
foreach cell $cells {
    if {$cell ne "" && $cell ne "0x0"} {puts $f "$cell $cell"}
}
close $f
