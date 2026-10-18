# 目录结构与每个文件的作用

以下是公开源码目录。项目只加载 tech/current 一套工艺，TECH 是结果标签；并非多工艺选择开关。

```text
.
├── Makefile                         所有用户目标、阶段依赖与工具调用入口
├── config.mk                        设计名/顶层/时钟、filelist、形状、CTS 等参数
├── README.md                        功能介绍、快速开始与文档导航
├── LICENSE                          框架与自写示例的 MIT 许可证
├── CONTRIBUTING.md                  提交规范、测试方法、私有资料边界
├── CHANGELOG.md                     公开版本变更记录
├── .gitignore                       生成物、私有工艺资料、本机配置忽略规则
├── .gitattributes                   文本文件与 Linux 脚本换行约定
├── .github/
│   └── workflows/tests.yml          无 EDA 回归的 GitHub Actions 配置
├── scripts/                         用户可直接查看、修改的工具流程
│   ├── dc.tcl                       读库/RTL、单元禁用、时钟/I/O 约束、综合及导出
│   ├── formal.tcl                   RTL 与综合网表等价验证、SVF 与结果报告
│   ├── pt.tcl                       读最终网表/SDC/SPEF、corner derate、附加约束与 STA
│   └── innovus/
│       ├── init.tcl                 LEF、综合网表和 MMMC 初始化
│       ├── floorplan.tcl            禁用单元、形状、pin、endcap、welltap
│       ├── powerplan.tcl            电源连接/via，启用两层及注释的单层/三层参考
│       ├── placement.tcl            OCV/SI、路径组、布局优化、tie 单元与布局检查
│       ├── cts.tcl                  时钟单元、NDR、route type、CTS 与 postCTS 优化
│       ├── route.tcl                层范围、天线策略、布线、RC/时序优化、一次 DRC 修复
│       └── chipfinish.tcl           decap/filler、连通性、几何检查、最终导出与 LEF
├── flow/                            框架内部，不是主要设计编辑入口
│   ├── settings.mk                  工具命令/默认运行参数及 Make→Python 变量导出
│   ├── flow.py                      CLI、阶段执行、preflight、config/MMMC 快照和 summary
│   ├── state.py                     工作区边界、文件指纹、JSON、锁与安全清理
│   ├── readiness.py                 check 的重要配置/存在性检查及 Innovus 合并显示
│   ├── reports.py                   日志错误/警告、Innovus/PT 时序摘要解析和打印
│   ├── report_store.py              报告归集、历史归档及安全解压
│   ├── eco_versions.py              独立 Git 仓库、成对快照、接受/历史/回退与缓存恢复
│   ├── deliver.py                   output 当前版交付文件夹、ZIP、清单及 SHA-256
│   ├── common.tcl                   读取 config 与少量公共 Tcl 函数/路径组
│   ├── pnr.tcl                      恢复上游、执行阶段脚本、报告并保存检查点
│   ├── route_drc.tcl                几何检查计数、最多一次修复及剩余违例提示
│   ├── eco.tcl                      GUI 中的 eco_save、eco_export；finish 后恢复 editable
│   ├── hcell.tcl                    从所选检查点生成 hcell 的兼容入口
│   ├── write_hcell.tcl              查询逻辑实例所用单元、去重，输出 layout/source 两列
│   └── resume_route.tcl             已手工修好 route 的只检查/提取/报告/保存入口
├── tech/current/
│   ├── README.md                    工艺接入和规则模板要求
│   ├── tech.mk                      DB、LEF、GDS、模型、CDL 和默认 corner 的占位路径
│   ├── corners.json                 每个 corner 的库、RC 文件、温度、缩放及 derate
│   ├── rc/options.cmd               StarRC 通用配置参考
│   ├── private/                     私有库目录骨架（每目录 README.md + .gitkeep）
│   │   ├── README.md                私有资料总说明
│   │   ├── db/                      综合与 STA DB
│   │   ├── lib/                     Liberty 时序库
│   │   ├── lef/                     技术与单元 LEF
│   │   ├── gds/                     标准单元/宏 GDS
│   │   ├── layermap/                streamOut 层映射
│   │   ├── verilog/                 仿真模型与 primitive/UDP
│   │   ├── cdl/                     LVS 单元网表
│   │   ├── captbl/                  Innovus 电容表
│   │   └── rc/                      RC 提取网格与映射
│   ├── drc/                         DRC 入口/deck 放置目录，只有说明与占位文件
│   └── lvs/                         LVS 入口/deck 放置目录，只有说明与占位文件
├── rtl/files.f                      用户 RTL 清单，每行一个相对工程根目录的源码路径
├── tb/files.f                       用户 testbench 清单，格式同上
├── examples/counter/
│   ├── config.mk                    复制后可用的 RTL 仿真示例配置
│   ├── counter.sv                   自写 4 位计数器
│   ├── tb_counter.sv                自检激励和 VCD 波形输出
│   ├── rtl.f                        示例 RTL 清单
│   └── tb.f                         示例 testbench 清单
├── tests/
│   ├── test_calibre_overlay.py      工具数据库链接保留、写入目标链接拒绝
│   ├── test_refactor.py             语法、报告、DRC 策略、ECO 日志、Git 回退/恢复、check
│   └── test_output.py               缺项跳过、重复打包和 ZIP 内容
└── docs/
    ├── structure.md                 本目录说明
    ├── commands.md                  Make 目标与参数的完整参考
    ├── workflow.md                  包含 ECO 的典型流程
    ├── release.md                   开源前检查与验证状态
    ├── publication-audit.md         当前源码与归档的公开内容检查记录
    └── assets/flow-preview.svg       README 功能效果示意图（非真实设计结果）
```

## 已保留的工艺目录骨架

- `tech/current/private/{db,lib,lef,gds,layermap,verilog,cdl,captbl,rc}/`：目录内 README.md 说明用途，.gitkeep 保证 Git 保留目录；用户自行放入的工艺资料不分发。
- `tech/current/drc/`：用户提供的 DRC deck 与 `rules.cal.in` 入口，默认 Git 忽略。
- `tech/current/lvs/`：用户提供的 LVS deck、`rules.cal`、`design.cal.in`，默认 Git 忽略。

不要将这些目录换成指向外部目录的符号链接作为 copy_overlay 目标；框架对要写入的路径有链接检查。

## 运行生成目录（不进 Git）

```text
work/<设计>/<工艺>/
├── dc/、formal/、sim/、cov/          各工具运行目录、日志、输出和 result.json
├── init/…/chipfinish/                Innovus 细分阶段与 design.enc/.enc.dat
├── eco/sessions/<会话>/              editable.enc、导出、会话标记；草稿不是已接受版本
├── versions/
│   ├── repository.git/              独立 Git 对象库，不是源码 Git 仓库
│   ├── revisions/<标识>/            editable、final 与脚本快照缓存
│   └── baseline.json                原始 route/chipfinish 基线提交
├── merge/、hcell/、lvs-input/         配套版图合并、hcell 和 LVS 输入
├── drc/、lvs/                        GUI 检查运行目录及数据库
├── rc/<corner>/、pt/<corner>/        寄生与 STA
├── active-final.json                 当前最终来源和 Git 版本指针
├── latest.json                       最近尝试阶段
└── .lock                             运行期间互斥锁，非长期状态文件

reports/<设计>/<工艺>/
├── dc/、formal/…                     归集报告；各目录含 来源.json
├── innovus/<阶段>/                   细分阶段报告
├── pt/<corner>/                      分角报告
├── eco/<版本或草稿>/                 对应版本报告
└── history/                          重复归集前的旧报告

output/<设计>/<工艺>/
├── <时间-唯一标识>/                  当前存在的交付文件与 manifest.json
└── <时间-唯一标识>.zip               同内容压缩包
```

`config.tcl`、`mmmc.tcl`、`derates.tcl`、`run.tcl` 等是运行目录中的输入快照/包装；修改设计请回到 scripts、config.mk、tech/current，不要只改生成副本。