# Make 命令与参数

在工程根目录执行，或使用 `make -C /path/to/project <目标>`。没有指定目标时显示 help。当前 Makefile 禁止阶段并行执行，框架以工作区锁避免同设计写冲突。

## 检查、状态和维护

| 命令 | 功能与行为 |
|---|---|
| `make help` | 列出常用目标；不启动 EDA |
| `make check` | 检查重要名称、必要输入/工艺文件及形状/pin 配置；整个 Innovus 合并为一项 |
| `make check STAGE=innovus` | 只检查 Innovus；`pnr` 或其细分阶段名也归并到 Innovus 检查 |
| `make check STAGE=dc` | 只检查指定项；其它值可用 sim/cov/formal/postsim/postsim_sdf/hcell/merge/lvs-input/rc/pt/drc/lvs/eco |
| `make summary` | 显示细分执行状态、最近阶段、时序/DRC 提示、当前 ECO Git 版本 |
| `make reports` | 从现有工作结果刷新统一报告目录，不运行 EDA；解压报告并归档旧副本 |
| `make test` | unittest 回归，临时文件/Git/Tcl 桩，不启动 EDA |
| `make clean-preview` | 显示本设计/工艺的清理目标；会短暂创建工作区锁，不删除结果 |
| `make clean-preview STAGE=route` | 只预览一个阶段 |
| `make clean STAGE=route` | 删除指定阶段工作目录，保留其它文件；后续依赖完整性会相应变化 |
| `make clean` | 删除当前命名空间全部阶段、ECO Git 版本历史、统一报告及版本指针；保留 output 交付包 |

check 不执行 Tcl、不检查电源方案、不逐条审核约束，也不检查工具许可证是否可用。脚本框架自带，执行时若缺失会明确失败。初始模板名称、形状、pin 和库均未配置，check 不通过是正常的。

summary：绿色 OK 表示记录成功、必要前置和结果存在；灰色 PENDING 表示未完成/缺输入结果或已显式失效；FAILED 表示失败；RUNNING 是记录的运行状态，不保证进程仍存活。没有按源码修改时间自动判定结果过期；修改后应主动指定重跑。

## 仿真、覆盖率与综合

| 命令 | Make 前置目标 | 说明 |
|---|---|---|
| `make sim` | 无 | RTL 与 testbench 编译/运行；按配置导出 FSDB 或 TB 自行导出的 VCD |
| `make verdi` | sim | 用 RTL 与 sim 波形打开 Verdi |
| `make cov` | 无 | 独立覆盖率编译/运行；GUI=1 时自动打开覆盖率查看器 |
| `make dc` | 无 | 执行 scripts/dc.tcl，导出网表、SDC、SDF、SVF 和报告 |
| `make formal` | dc | 执行 scripts/formal.tcl，对 RTL 和综合网表做等价验证 |
| `make postsim` | dc 或 chipfinish | GATE_STAGE=dc 使用综合网表；chipfinish 使用当前最终版；不回标 SDF |
| `make postverdi` | postsim | 查看对应门级功能仿真波形 |
| `make postsim_sdf` | chipfinish | 使用当前最终版网表与 SDF，按 DUT_INSTANCE 做 max 回标 |
| `make postverdi_sdf` | postsim_sdf | 查看 SDF 仿真的网表和波形；不增加独立 summary 阶段 |

覆盖率是否含 FSM 取决于设计是否被工具识别出 FSM，不能保证每个指标都有数据。RTL_DEFINES 只用于 RTL sim/cov，不自动传给门级仿真；普通 gate model 可能仍包含 specify 延迟。Verdi 波形设置可通过 `VERDI := verdi -sswr /path/to/signal.rc` 配置；覆盖率查看器单独使用 VERDI_COV。

## Innovus

| 命令 | 直接 Make 前置 | 用户主要编辑位置 |
|---|---|---|
| `make init` | dc | scripts/innovus/init.tcl |
| `make floorplan` | init | floorplan.tcl：形状、pin、禁用/物理单元 |
| `make powerplan` | floorplan | powerplan.tcl：层、方向、宽度、间距、via 与连接 |
| `make placement` | powerplan | placement.tcl |
| `make cts` | placement | cts.tcl：时钟单元、NDR 与优化 |
| `make route` | cts | route.tcl：层范围、布线和优化 |
| `make chipfinish` | route | chipfinish.tcl：填充与导出 |
| `make pnr` | chipfinish | 执行整个后端链 |
| `make open` | 无 | 打开当前最终版；无完整 chipfinish 时选择已完成的最近后端阶段 |
| `make open STAGE=route` | 无 | 打开指定已完成检查点，可指定任一 Innovus 阶段或 eco |
| `make route-resume` | 无 | 读取 route/manual_fixed.enc，要求 CTS 完成；验证清零、提取并保存接续结果，不再次布线 |

GUI=1 时，直接请求的后端阶段完成后打开对应 GUI；`GUI=0` 批处理到阶段完成。`make open`、`make eco` 本身就是交互 GUI 命令，需要 DISPLAY 和终端，GUI=0 不能将它们变成批处理。

route 在最终优化后检查几何 DRC，必要时只修复一次；剩余违例警告后继续，chipfinish 再检查并记录。不把工具命令失败、检查无法完成当作普通 DRC 放行。原始 DRC 仍需 Calibre 检查。

## Signoff 输入和检查

| 命令 | 前置 | 行为 |
|---|---|---|
| `make merge` | chipfinish | 当前最终 GDS 与配置的标准单元 GDS 合并 |
| `make hcell` | chipfinish | 使用 HCELL_FILE，或当前最终导出的 hcell_list；必要时恢复数据库查询 |
| `make drc` | merge | 准备 deck/GDS 并打开 Calibre GUI，实际检查由用户运行 |
| `make lvs` | merge、hcell | 生成带电源标签版图、V2LVS 源网表与 lvs.runset，打开 GUI |
| `make rc` | chipfinish | 当前最终 DEF 按 corner 提取 SPEF |
| `make pt` | rc | 使用配套网表、SDC、各角 SPEF 执行 scripts/pt.tcl |

`lvs-input` 是内部阶段，由 `make lvs` 调用，不能直接假设存在同名 Make 目标。加载 GUI 中生成的 lvs.runset，核对 Layout、Source、hcell，避免旧 runset 覆盖新输入。DRC 输出名称也可能被 GUI runset 改写；请查看实际运行配置与时间。

DRC/LVS 实际检查完成不自动记入 summary 成功格；GUI 打开和归集报告不代表签核通过。RC/PT 和这些输入的选源会跟随已接受 ECO 版本。

## ECO 工作区版本管理

详见 [工作区 ECO 与迁移](workspace-eco.md)。工具当前输入固定是 chipfinish 工作区，不是 Git 历史目录。

| 命令 | 行为 |
|---|---|
| `make eco-init` | 无依赖、不运行 EDA，当前成套结果建立新版基线；旧链保留 |
| `make eco` | 无 Make 前置，打开 eco/editable；首次需要已有完整结果 |
| `make eco-accept MSG="备注"` | 无依赖，提交当前工作区文件；支持直接改 `_lvs.v`，无需每次 eco_export |
| `make eco-history` | 当前新版 Git 历史和 dirty 状态 |
| `make eco-history LEGACY=1` | 单独查看旧 versions/ 历史 |
| `make eco-rollback` | 恢复父版本到工作区，保留其它分支 |
| `make eco-rollback REV=abcdef1234` | 恢复指定新版提交，至少 7 位十六进制 |
| `make eco-use-original` | 恢复格式 2 基线 |
| `make eco-rollback DISCARD=1` | 明确放弃未提交修改；默认 dirty 时拒绝覆盖 |

GUI 中 eco_save 只保存草稿；eco_export {备注} 更新 chipfinish 并恢复 editable。退出 GUI 后先 make drc/lvs/pt，再 accept。直接改文件时可跳过 GUI 和 export。

提交不是正确性审核，不同步数据库；再次 export 会覆盖对应文本导出。未导出的数据库草稿不能拿旧 final 验证。交付内容变化按依赖更新缓存，touch 不触发；accept 不让刚完成的验证失效。已有基线时不能强制重跑 DC/PNR 覆盖工作区，需继续 ECO 或完整 clean。

## output 交付

```bash
make output
```

此目标**没有 Make 前置依赖**，不要求阶段 READY/OK，不触发仿真、综合或检查。只读取当前工作区 chipfinish 中的：

- `<设计名>.v`：最终逻辑网表；`<设计名>_lvs.v`：LVS 物理网表。
- `<设计名>.sdc`、`.sdf`、`.def`、`.lef`、`.gds`。
- `hcell_list`。

缺失/不可读项逐个跳过，不回退到其它版本凑文件。每次新建 `output/<设计>/<工艺>/<时间-标识>/` 与同名 ZIP；manifest.json 记录当前版本、来源、复制/跳过状态、大小与 SHA-256。全部缺失也可生成仅含清单的包。目录创建/压缩本身失败仍会报错，不把磁盘故障伪装成成功。

output 不替代 signoff；请在当前版本静止、所有 GUI 保存退出后打包。它不默认包含库文件、SPEF、数据库、签核报告或全部工艺资料，需要其它交付物时自行扩展清单。

## 参数参考

| 参数 | 默认/取值 | 作用与例子 |
|---|---|---|
| STAGE | 空 | check/open/clean/clean-preview 的阶段选择，如 `make open STAGE=cts`；不是所有目标通用的“执行到”参数 |
| FORCE_STAGE | 空，空格分隔阶段 | 重跑 Make 已访问到的指定阶段，如 `make chipfinish FORCE_STAGE='route chipfinish' GUI=0`；不直接增加依赖目标 |
| FORCE | 0/1 | 1 会重跑本次依赖链访问到的所有阶段，代价通常较大；有 ECO 基线时受上述保护限制 |
| GUI | 默认 1 | cov 自动打开查看器、直接请求的 PNR 阶段完成后打开 GUI；0 抑制这些自动打开 |
| REV | 空或提交编号 | 只用于 eco-rollback；空回到父版本 |
| MSG | 空或备注 | eco-accept 提交说明 |
| DISCARD | 0/1 | 1 允许回退覆盖未提交修改 |
| LEGACY | 0/1 | eco-history 查看旧历史 |
| CPU | 8 | DC/Innovus/RC 等运行线程设置；具体工具仍受许可证与自身行为限制 |
| GATE_STAGE | dc/chipfinish | postsim/postverdi 的网表来源；SDF 仿真固定当前最终版 |
| HCELL_FILE | 空 | 自定义两列单元映射，路径相对工程根目录；变化后主动更新 hcell/LVS 输入 |
| PYTHON | python3 | Python 解释器 |
| VCS/VERDI/VERDI_COV | vcs/verdi/verdi | 工具命令可带固定选项，覆盖率查看器独立于波形查看器 |
| DC_SHELL/FM_SHELL/INNOVUS | dc_shell/fm_shell/innovus | 对应工具命令 |
| CALIBREDRV/V2LVS/STARXTRACT/PT_SHELL | calibredrv/v2lvs/StarXtract/pt_shell | 合并/转换/寄生/STA 工具命令 |
| VERDI_HOME | NOVAS_HOME | 非空时加载 VCS FSDB PLI，需对应 novas.tab 和 pli.a |
| CALIBRE_INNOVUS_TCL | 空 | 可选 Calibre 集成脚本完整路径，仅 ECO GUI 加载，留空跳过 |
| RTL_DEFINES | tech.mk 配置 | RTL sim/cov 编译宏，空格分隔，不应用于门级 |

NO_COLOR 是环境变量，设置后 summary 不输出 ANSI 颜色。TERM=dumb 或输出非终端时也禁用颜色。

示例：

```bash
make cov GUI=0
make postverdi_sdf FORCE_STAGE=postsim_sdf
make placement CPU=4 GUI=0
make clean STAGE=postsim
make eco-rollback REV=0123456789ab
```

设计参数如 PROJECT_NAME、DESIGN_NAME、TOP_MODULE、CLOCK_NAME/CLOCK_PORT、RTL_LIST、TB_LIST、TB_TOP、DUT_INSTANCE、INCLUDE_DIRS、TIMESCALE、FLOORPLAN_MODE、CORE_WIDTH/HEIGHT/MARGIN、POWER_NET/GROUND_NET、CTS_MAX_TRANSITION/TARGET_SKEW/MAX_FANOUT 在 config.mk 中设置。filelist 每行一个源码路径，不支持嵌套 filelist 或编译选项。工艺库和 corner 参数见 tech/current/README.md。