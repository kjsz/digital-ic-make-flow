# 变更记录

## LVS 大小写配置说明 — 2026-10-19

- 新增不含工艺资料的名称配置示例：保留大小写并使用 LVS COMPARE CASE NAMES。
- 明确源模板与生成文件的区别，说明如何通过实际 LVS 报告确认配置生效。
- 示例需合并到私有 design.cal.in，不自动修改供应商规则。

## 工作区版本管理 — 2026-10-19

- 新增 eco-init、MSG、DISCARD、LEGACY；旧 versions/ 保留，新链放 versions-v2/。
- 当前最终文件固定在 chipfinish，支持直接改网表、先验证后 accept。
- eco_export 写原工作区；accept 不重复使刚完成的验证失效。
- 最终交付内容按指纹定向检测；touch 不失效，不恢复全工程时间戳检查。
- 回退恢复工作区，默认保护未提交修改；新增用户执行的工作区回归测试。


## 开源准备版 — 2026-10-18

- Make 管理阶段依赖，Python 管理输入、状态、工具调用和报告。
- 集中 DC/PT/Formality 与各 Innovus 阶段 Tcl。
- 分阶段 summary、存在性 check、选择性重跑。
- editable/finished 成对 ECO 检查点，独立 Git 历史、父版本回退和指定版本切换。
- 报告归集、gzip/归档解压、无依赖 output 交付快照。
- 移除私有工艺库、规则、真实报告及实战设计记录，改用空白模板与自写 counter 示例。
- 加入许可证、贡献说明、无 EDA 测试及 GitHub Actions 配置。
- README 添加带示意数据标识的功能效果图和 ECO 版本关系图。
- 保留工艺库/规则分类目录，使用 README.md 和 .gitkeep 提示放置位置；只忽略实际私有资料。

本次公开模板的新增整理尚未由助手运行测试或 EDA；先前实战验证不等于所有工艺和工具版本均支持。