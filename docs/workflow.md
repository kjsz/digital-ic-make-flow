# 典型使用流程：从 RTL 到 ECO 与交付

下列命令由用户在已配置的 Linux EDA 环境执行。先理解每步输入和结果，再继续；框架不会替你判断物理方案或签核覆盖是否充分。

## 1. 配置和验证框架

1. 在 config.mk 填入设计/顶层/时钟名称、filelist、testbench 层级和形状。
2. 在 scripts/dc.tcl 配置时钟周期、uncertainty、I/O delay 和综合策略。
3. 在 scripts/innovus/floorplan.tcl 配 pin，检查 site、单元禁用和物理单元。
4. 编辑 powerplan/cts/route/chipfinish，匹配实际电源、走线层、NDR、单元及导出层。
5. 按 tech/current/README.md 接入合法库、RC、DRC/LVS 规则，配置 PT 附加约束。

```bash
make test
make check
make check STAGE=innovus
```

Make 读取 config.mk、tech.mk 和 settings.mk 并导出环境变量；Python 执行检查或启动工具。生成的 config.tcl/MMMC 是该次运行输入快照。检查通过只证明存在必要输入。

## 2. 前端闭环

```bash
make sim
make verdi
make cov
make dc
make formal
make postsim
make postverdi
make summary
```

sim 用 RTL 验证激励；dc 输出门级网表/SVF/SDC；formal 比较 RTL 与综合网表；默认 postsim 使用 DC 网表做门级仿真。coverage 不替代自检激励。留意未驱动单元、未约束路径、高扇出和库端口警告，不统一屏蔽未知警告。

## 3. 自动后端

可逐步运行以理解输入变化：

```bash
make init GUI=0
make floorplan GUI=0
make powerplan GUI=0
make placement GUI=0
make cts GUI=0
make route GUI=0
make chipfinish GUI=0
make open STAGE=chipfinish
```

也可直接 `make chipfinish GUI=0`，Make 会依序访问必要阶段，Python 跳过已有完整结果。route 最多修复一次几何 DRC；残留违例记录后继续收尾，以便将 Calibre 的额外问题合并处理。

检查 CTS 时对照配置目标、工具采用的目标和实际 skew，不把设置值当作实现值。检查电源、pin、层方向及布线范围。脚本改动不会自动让结果过期；尚未建立 ECO 基线时可用 `make chipfinish FORCE_STAGE=cts GUI=0` 从 CTS 显式重跑其下游。

## 4. 物理与时序检查

```bash
make drc
make lvs
make pt
make reports
```

在 Calibre GUI 中实际运行检查。LVS 加载本次生成的 lvs.runset，核对当前版 Layout/Source 和 hcell；DRC 检查正确 foundry 选项和实际结果文件名。合并结果、源网表、RC/PT 必须来自同一最终版本。

查看 DRC/LVS 错误和 setup/hold、未约束路径、寄生标注覆盖等。hcell 是单元对应表，不等于跳过单元验证。不能用虚连接或忽略端口选项掩盖真实断线；模板或私有规则中的这些策略由用户审核。

## 5. 手工 ECO

```bash
make eco
```

首次自动把 route 的 finish 前数据库和 chipfinish 的最终结果保存成 Git 基线，然后打开可编辑数据库。修复 via、跳线、局部布线等问题；进行连通性与局部几何检查。

Innovus 中：

```tcl
verifyConnectivity -type all -error 1000 -warning 50
eco_save
eco_export {修复某网络缺失 via 与局部间距}
exit
```

export 先保存 editable，再执行同一 chipfinish，导出并保存 finished，最后恢复 editable。它不重复自动 place/route；需要的手工 ECO 收尾由用户先完成。信号 opens 应修好后再接受；dangling wire 和供电风险仍需实际审核。

```bash
make eco-accept
make eco-history
make summary
```

accept 核验导出标记、结果完整性、最近导出范围中的错误和时序报告，提交独立 Git 仓库后切换当前版。导出前的拼写/undo 错误不应污染导出检查。接受不证明 DRC/LVS 或时序收敛。

## 6. 检查新版本或回退

```bash
make drc
make lvs
make pt
```

结果不理想时：

```bash
make eco-history
make eco-rollback                  # 回到父版本
# 或 make eco-rollback REV=<版本号>
# 或 make eco-use-original         # 回到自动实现基线
make eco                          # 从所选版本 editable 继续
```

每个版本保存父关系。假设从 2.0 做出 3.0，默认回退到 2.0；从基线另做 3.0，默认回退到基线。回退不会删除其它分支。再次导出/接受后，下游重新检查。

## 7. 最终仿真与交付

```bash
make postsim_sdf
make postverdi_sdf
make reports
make output
```

确认最终 DRC、LVS、RC/PT 与 SDF 仿真都对应最后接受的同一版，并审核工艺规则和约束覆盖。output 仅复制已有交付物，缺失项不会触发重跑；请检查 manifest.json 中的 skipped 项。

保存版本号、交付 ZIP、所需签核报告与环境说明。交付文件夹不是完整 EDA 可恢复环境，PDK、库、SPEF/数据库及许可证不默认包含。需要继续追溯 ECO 时保留完整 work/<设计>/<工艺>/versions/。

最后需要清理时先执行 `make clean-preview`。不带 STAGE 的 clean 会删除 ECO Git 历史；output 交付包独立保留。