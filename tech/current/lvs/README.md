# LVS 私有规则入口

放置用户提供的 rules.cal、design.cal.in 和全部 LVS 规则 include 文件。

本目录不提供工艺规则。README.md、.gitkeep 和框架自写的 case-sensitive.cal.example 可以公开；实际规则默认被 Git 忽略。

## 大小写设置

将 case-sensitive.cal.example 中的三个设置合并到自己的 design.cal.in，替换已有同名设置：

```svrf
LAYOUT CASE YES
SOURCE CASE YES
LVS COMPARE CASE NAMES
```

例如外部端口 SEL 与内部网络 sel 是两个不同的信号。保留输入大小写还不够，比较时也应区分名称大小写。NAMES 只指定网络、实例和端口名称的大小写比较，不等同于 YES 对其它类别也启用区分大小写。具体规则仍须与所用工艺和工具核对。

本示例只提供名称设置，不能替代完整的 design.cal.in 或供应商规则，也不会被框架自动加载；需合并到实际源模板。

## 修改位置与验证

修改 tech/current/lvs/design.cal.in，不要只修改 work 下的 sample_design_inc.cal：每次 make lvs 会从源模板重新生成后者。规则入口 rules.cal 须正确 INCLUDE 生成的 sample_design_inc.cal。

重新运行 LVS 后，在实际工作目录检查：

```bash
grep 'LVS COMPARE CASE' work/<设计名>/<工艺标签>/lvs/lvs.rep
```

应显示 NAMES。以报告中的生效值为准，不以编辑器内容推断。若配置未生效，检查是否保存到源模板、是否重新生成输入、是否存在其它覆盖设置，以及是否查看了最新报告。

有 hcell 通过、无 hcell 失败时，应检查实际比较参数和差异。hcell 提供层次对应关系，不等于黑盒；是否完成内部检查应查看单元比较报告。不要通过删除有用网络或忽略错误来消除报错。
