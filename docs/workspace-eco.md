# 工作区 ECO 与文件提交（格式 2）

新流程：**在工作区修复 → 直接验证 → 提交**。直接改 LVS 网表也可形成新节点，不必启动 Innovus 或先生成 exported.json。

## 首次启用

```bash
make test
make eco-init
```

eco-init 不运行 EDA。旧框架只取当前选中版本的 final/editable 作为新版基线，不迁移/改写旧父提交链；原 chipfinish 与指针保存到 versions-v2/migration-backup/。旧 versions/ 和缓存保留，可用 `make eco-history LEGACY=1` 查看。旧缓存缺失则停止，不强行兼容。

没有旧版本时用已有 route/chipfinish 建立基线。请在修改前初始化；未初始化就 accept 只能保存当前状态为首个基线，不能凭空重建修改前内容。

## 工作位置

```text
work/<设计>/<工艺>/
  chipfinish/                   当前最终网表、SDC/SDF/DEF/LEF/GDS、hcell、design.enc/.dat
  eco/editable.enc              finish 前可编辑数据库
  eco/editable.enc.dat/
  eco/gui.log                   当前 GUI 日志
  eco/draft-pending             数据库草稿尚未导出（不能验证旧 final）
  versions-v2/repository.git/    新历史对象，不作为当前工具输入
  versions-v2/state.json        当前提交、基线和工作区指纹
  versions-v2/observed.json     最终文件内容与缓存检测
  versions-v2/migration-backup/ 初始化前工作区备份
  versions-v2/restore-backup/   回退前工作区备份
  versions/                     旧历史原样保留
```

DRC/LVS/PT/output 均使用当前 chipfinish，包含未提交修改。Tcl 源脚本仍编辑项目 scripts/；生成的 config.tcl 等是运行输入快照。提交保存源脚本参考副本，回退恢复工作区输出与 editable，不改源码仓库的 scripts/。

## 直接修改 LVS 网表

```bash
# 编辑 work/<设计>/<工艺>/chipfinish/<设计>_lvs.v
make lvs
# 在 GUI 中实际运行并核对检查结果
make eco-accept MSG="清理未使用的层级端口"
make eco-history
```

只要求必要交付文件及检查点完整，不要求每次导出。无内容变化不重复提交。Git 提交不是正确性/签核审核；没有验证也可以保存版本，但不能称为 PASS。

文本修改不会回写 Innovus 数据库。删除未使用层级端口仍需 LVS/导入检查确认用途；修改实际逻辑连接则需同步维护数据库和其它交付物。

## Innovus ECO

```bash
make eco
```

```tcl
# 修复、检查连通性后
eco_export {补齐 via}
exit
```

export 保存 editable、执行同一 chipfinish、将结果直接写 chipfinish，然后恢复 editable。退出后先验证、再提交：

```bash
make drc
make lvs
make pt
make eco-accept MSG="补齐 via 并完成检查"
```

make eco 不再带 chipfinish 前置，避免失败导出触发自动重跑、覆盖工作区。eco_save 只保存草稿；未导出草稿会阻止拿旧 final 验证。导出失败保持未完成/待导出，不沿用旧完成标记。

**再次 eco_export 会重新生成网表，覆盖对应手工文本修改。** 需保留的修改请先提交/另存，或在最后一次版图导出后再清理文本。提交成功不代表数据库自动同步。

## 缓存规则

只针对 chipfinish 的最终交付内容做 SHA-256 检测，不使用 mtime、不恢复全工程脚本过期检查：

| 文件内容变化 | 更新的下游 |
|---|---|
| `_lvs.v` | lvs-input、lvs |
| `.gds` | merge、drc、lvs-input、lvs |
| `.def` | rc、pt |
| `.v` | pt、postsim_sdf；GATE_STAGE=chipfinish 时也更新 postsim |
| `.sdc` | pt |
| `.sdf` | postsim_sdf |
| hcell_list | hcell、lvs-input、lvs |
| add_pg_text.tcl | lvs-input、lvs |
| `.lef` | 仅交付快照，本框架没有以它为输入的验证阶段 |

运行前检查内容，定向失效旧缓存。touch 不失效；accept 本身不改内容，不让刚完成的验证失效。记录保存检查使用的工作区指纹；Calibre GUI 仍需用户实际运行与审核，不伪造 PASS。

## 回退与历史

```bash
make eco-history
make eco-rollback
make eco-rollback REV=<新版提交编号>
make eco-use-original
```

分别查看新版历史、恢复父版本、恢复指定新版提交、恢复新版基线；恢复位置仍是工作区。旧链不强行映射为新提交号，使用 LEGACY=1 单独查看。

有未提交修改时默认拒绝覆盖；确认放弃可用：

```bash
make eco-rollback DISCARD=1
```

恢复先完整解包，旧文件保留备份；中断时尽力恢复原工作区。回退后下游重新验证，其它分支保留。完整 make clean 会删除新旧历史、迁移/恢复备份与报告。