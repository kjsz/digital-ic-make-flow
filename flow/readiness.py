"""仅检查重要配置与输入存在性；不执行 Tcl，不审核电源和约束数值。"""
from state import identifier
PNR = ('init', 'floorplan', 'powerplan', 'placement', 'cts', 'route', 'chipfinish')
CHECK_STAGES = ('sim', 'cov', 'dc', 'formal', 'postsim', 'postsim_sdf', 'innovus', 'hcell', 'merge', 'lvs-input', 'rc', 'pt', 'drc', 'lvs')


def script_issues(path):
    if not path.is_file():
        return ['未配置：'+str(path)]
    text = path.read_text(encoding='utf-8-sig', errors='replace')
    return [] if any(s.strip() and not s.lstrip().startswith('#') for s in text.splitlines()) else ['未配置：'+str(path)]


def configuration_issues(flow, stage):
    issues = []
    for key in ('PROJECT_NAME', 'TOP_MODULE'):
        if not flow.cfg[key].strip():
            issues.append('未配置：'+key)
    for key in ('DESIGN_NAME', 'TECH'):
        try:
            identifier(flow.cfg[key], key)
        except ValueError:
            issues.append('未配置：'+key+'（需要有效名称）')
    if stage == 'dc' or stage in PNR:
        for key in ('CLOCK_NAME', 'CLOCK_PORT'):
            if not flow.cfg[key].strip():
                issues.append('未配置：'+key)
    if stage == 'floorplan':
        if flow.cfg['FLOORPLAN_MODE'] == 'rectangle':
            for key in ('CORE_WIDTH', 'CORE_HEIGHT', 'CORE_MARGIN'):
                if not flow.cfg[key].strip():
                    issues.append('未配置形状：'+key)
        elif flow.cfg['FLOORPLAN_MODE'] != 'custom':
            issues.append('未配置形状：config.mk 中的 FLOORPLAN_MODE')
        path = flow.root/'scripts/innovus/floorplan.tcl'
        if path.is_file():
            text = path.read_text(encoding='utf-8-sig')
            block = text.split('# BEGIN PIN_ASSIGNMENTS')[-1].split('# END PIN_ASSIGNMENTS')[0]
            if not any(s.strip() and not s.lstrip().startswith('#') for s in block.splitlines()):
                issues.append('未配置 pin 分配：scripts/innovus/floorplan.tcl')
            if flow.cfg['FLOORPLAN_MODE'] == 'custom':
                shape = text.split('# BEGIN CUSTOM_SHAPE')[-1].split('# END CUSTOM_SHAPE')[0]
                if '# BEGIN CUSTOM_SHAPE' in text and not any(s.strip() and not s.lstrip().startswith('#') for s in shape.splitlines()):
                    issues.append('未配置自定义形状：scripts/innovus/floorplan.tcl')
    return issues


def check(flow):
    requested = flow.env.get('STAGE', '').strip()
    if requested in PNR or requested == 'pnr':
        requested = 'innovus'
    if requested and requested not in CHECK_STAGES + ('eco',):
        raise ValueError('未知检查阶段：'+requested)
    failed = False
    for target in ([requested] if requested else CHECK_STAGES):
        stages = PNR if target == 'innovus' else (target,)
        issues = []
        for stage in stages:
            try:
                issues.extend(flow.preflight(stage, upstream=False, tools=False))
            except (ValueError, OSError, TypeError, KeyError) as exc:
                issues.append(str(exc))
        issues = sorted(set(issues))
        print('[{}] {}'.format(target, '待配置/缺少输入' if issues else 'READY'))
        for issue in issues:
            print('  '+issue.replace('Not configured:', '未配置：').replace('Missing/empty:', '缺少文件或文件为空：'))
        failed |= bool(issues)
    print('READY 只表示必要配置和输入存在；不检查 Tcl 正确性、电源方案或执行结果。')
    print('执行完成情况请查看 make summary；修改脚本后如需重跑，请指定 FORCE_STAGE。')
    return int(failed)