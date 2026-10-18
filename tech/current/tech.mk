# 单一工艺配置；路径相对于 tech/current，不含工艺库。
SYN_LIBS := private/db/tt.db
LEFS := private/lef/technology.lef private/lef/cells.lef
GDS_FILES := private/gds/cells.gds
GDS_MAP := private/layermap/streamout.map
SIM_LIBS := private/verilog/cells.v private/verilog/primitives.v
LVS_LIBS := $(SIM_LIBS)
CDL_FILES := private/cdl/cells.cdl
# 仅对 RTL sim/cov 生效的可选模型宏。
RTL_DEFINES :=
CORNERS := tt bc
SETUP_CORNER := tt
HOLD_CORNER := bc