# 形状、pin 与物理边界单元集中在本文件；换设计时重点检查。
set SITE GF018hv5v_mcu_sc7
set PIN_LAYER Metal4
set PIN_WIDTH 0.28
set PIN_DEPTH 0.52
foreach pattern {BUF_X1_7T5P0 BUF_X2_7T5P0 BUF_X20_7T5P0 BUF_X16_7T5P0
    BUFZ_X1_7T5P0 BUFZ_X2_7T5P0 BUFZ_X20_7T5P0 INV_X1_7T5P0 INV_X2_7T5P0
    INV_X16_7T5P0 INV_X20_7T5P0 INVZ_X1_7T5P0 INVZ_X2_7T5P0 INVZ_X20_7T5P0
    ANTENNA_7T5P0 DLY* HOLD* CLK* TIE* ENDCAP* FILL* FILLCAP*} {
    foreach cell [dbGet head.libCells.name $pattern] {
        if {$cell ne "0x0"} {setDontUse $cell true}
    }
}
if {$FLOORPLAN_MODE eq "rectangle"} {
    floorPlan -site $SITE -s [concat [list $CORE_WIDTH $CORE_HEIGHT] $CORE_MARGIN]
} else {
    # BEGIN CUSTOM_SHAPE
    # 自定义形状请直接在此处写命令。
    # floorPlan -site $SITE -s {200 6400 1.12 1.12 1.12 1.12}
    # END CUSTOM_SHAPE
}
# BEGIN PIN_ASSIGNMENTS
# 在此填写 editPin 命令；只检查是否有有效配置，不检查位置正确性。
# editPin -pin YOUR_PIN -assign {0 10} -layer Metal4 -pinWidth 0.28 -pinDepth 0.52
# END PIN_ASSIGNMENTS
setDontUse ENDCAP_7T5P0 false
setDontUse FILL_X1_7T5P0 false
setEndCapMode -reset
setEndCapMode -leftEdge ENDCAP_7T5P0 -rightEdge ENDCAP_7T5P0 -topEdge {ENDCAP_7T5P0 FILL_X1_7T5P0} -bottomEdge {ENDCAP_7T5P0 FILL_X1_7T5P0} -prefix ENDCAP
addEndCap
setDontUse ENDCAP_7T5P0 true
setDontUse FILL_X1_7T5P0 true
setDontUse FILLTIE_7T5P0 false
set_well_tap_mode -rule 30 -bottom_tap_cell FILLTIE_7T5P0 -top_tap_cell FILLTIE_7T5P0
addWellTap -cell FILLTIE_7T5P0 -cellInterval 60 -prefix WELLTAP -checkerBoard
setDontUse FILLTIE_7T5P0 true
