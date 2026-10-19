# 接入一套当前工艺

本仓库只有配置占位符与参考命令，不含工艺库、供应商规则、模型或许可证。先合法取得本地资料，再按当前工具版本调整。TECH 只是结果标签；所有实际工艺配置固定从 tech/current 加载。

## 库路径

编辑 tech.mk；路径相对于本目录：

| 变量 | 内容 |
|---|---|
| SYN_LIBS | DC/Formality 的 .db |
| LEFS | 技术 LEF、标准单元/宏 LEF |
| GDS_FILES | 合并所需的标准单元/宏 GDS |
| GDS_MAP | Innovus streamOut 层映射 |
| SIM_LIBS | 门级仿真模型，必要时包含 UDP/primitive 文件 |
| LVS_LIBS | V2LVS 需要的 Verilog 库声明 |
| CDL_FILES | LVS SPICE/CDL 单元网表 |
| RTL_DEFINES | 仅 RTL sim/cov 使用的宏，如库确需 FUNCTIONAL 可设置 |
| CORNERS | 用空格分隔的分析角名称 |
| SETUP_CORNER/HOLD_CORNER | Innovus 使用的 setup/hold 角 |

库目录已按 db/lib/lef/gds/layermap/verilog/cdl/captbl/rc 保留，每个目录有 README.md 和 .gitkeep。库文件放 private/ 对应子目录，内容默认忽略；说明与占位文件可提交。不要提交合法取得但无权公开的文件。Git ignore 只是预防，不会清除已经提交过的历史资料。

## corners.json

每个 corner 配置 db/lib 列表、captable、nxtgrd、mapping、temperature、rc_scale。PNR 使用 Liberty 与 captable，RC 使用 nxtgrd/mapping，PT 使用 DB。

pnr_derate 与 pt_derate 是可选字典；键形如 early_clock、late_clock、late_data，值为对应倍率。公开模板为空，不能当成签核 derate。温度、PVT、setup/hold 角与提取角须成套一致。

rc/options.cmd 是框架自写的通用参数示例。实际 StarRC 命令/版本差异与工艺要求由用户配置。

## DRC/LVS 私有规则入口

目录骨架已经保留；将合法规则放入对应真实目录（规则内容默认被 .gitignore 忽略）：

```text
tech/current/drc/
  rules.cal.in              DRC 入口模板及所需 foundry include 文件
tech/current/lvs/
  rules.cal                 LVS 规则入口及 include 文件
  design.cal.in             LVS 当前设计输入模板
```

框架复制这些目录到工作目录，在 DRC 的 rules.cal.in 与 LVS 的 design.cal.in 中替换：

- `@LAYOUT@`：本次版图路径。
- `@TOP@`：顶层名称。
- `@SOURCE@`：LVS 源 SPICE 路径。

DRC 替换后的入口为 work/.../drc/rules.cal；LVS 设计输入生成 sample_design_inc.cal，规则入口须正确 INCLUDE 它。规则相对 include 应完整，check 会检查可解析的 include 路径。不要依赖旧项目中的绝对服务器路径。

用户提供规则的完整性、选用金属堆叠/厚度、天线组、器件选项、端口/电源/虚连接策略必须自行审核。框架不会提供可替代 foundry deck 的简化检查。

## 阶段脚本适配

scripts/dc.tcl 中禁用单元和约束，与 scripts/innovus 内的 site、单元名、层名、层方向、NDR、电源、via、tap/endcap/filler/decap 均需核对。随附 GF180 名称只作可读参考，并不是公开 PDK 的交付。

powerplan 默认两层；单层和三层是整组注释示例。启用另一方案前注释旧组；最高电源层改变时同步检查 sroute、chipfinish 的电源标签与 LEF pin 导出。普通信号默认 M2～M5；CTS 主干 M4/M5 2 倍线宽/间距，leaf M3/M4 默认宽度/2 倍间距，需要实测验证。

可选 Calibre 集成在 config.mk 设置 `CALIBRE_INNOVUS_TCL := /your/local/cal_enc.tcl`，留空时 ECO GUI 跳过该集成。更换工艺应使用不同 TECH 标签并清理/隔离旧结果，不能混用旧 ECO 历史。
LVS 名称比较建议使用保留大小写并区分名称的配置，参见 [LVS 配置示例与排错](lvs/README.md)。修改源模板后须从实际报告确认生效，工作目录的生成文件会在下次 make lvs 时覆盖。
