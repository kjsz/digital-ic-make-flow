"""Read only reports belonging to a completed/attempted stage, never glob old runs."""
import gzip
import math
import re
from pathlib import Path

NUMBER = r'[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?'
ERROR = re.compile(r'^\s*(?:Error(?:\s*[-:]|\s+\[)|Fatal(?:\s*[-:]|\s+\[)|\*\*\s*(?:ERROR|FATAL)|FLOW_ERROR:)', re.I)
WARNING = re.compile(r'^\s*(?:Warning(?:\s*[-:]|\s+\[)|\*\*\s*WARN|FLOW_DRC_WARNING:)', re.I)

def read(path):
    path = Path(path)
    if not path.is_file():
        return ''
    if path.suffix == '.gz':
        with gzip.open(path, 'rt', errors='replace') as f:
            return f.read()
    return path.read_text(errors='replace')

def messages(paths):
    errors, warnings = [], []
    for path in paths:
        for number, line in enumerate(read(path).splitlines(), 1):
            item = '{}:{}: {}'.format(path, number, line.strip())
            if ERROR.search(line) or re.search(r'^(?:invalid command name|can.t read .*: no such variable)', line):
                errors.append(item)
            elif WARNING.search(line):
                warnings.append(item)
    return {'errors': errors, 'warnings': warnings}

def unit_ns(text):
    # Synopsys versions use either "Time : 1ns" or "Time unit : 1e-09 Second".
    match = re.search(r'(?im)^\s*Time(?:[ _]+unit)?\s*[:=]\s*('+NUMBER+r')\s*(fs|ps|ns|us|ms|s|second)\b', text)
    if not match:
        return None
    return float(match[1]) * {'fs': 1e-6, 'ps': .001, 'ns': 1, 'us': 1e3, 'ms': 1e6, 's': 1e9, 'second': 1e9}[match[2].lower()]

def pt_slack(text, scale=1.0):
    values = [float(v) for v in re.findall(r'slack\s*\((?:MET|VIOLATED)\)\s*('+NUMBER+r')', text, re.I)]
    return min(values) * scale if values and scale is not None else None

def innovus(text):
    result = {'slack_ns': None, 'tns_ns': None, 'violations': None, 'paths': None}
    # Select the "all" column explicitly, not the minimum of per-group values.
    header = next((line for line in text.splitlines() if re.search(r'\|\s*(?:Setup|Hold) mode', line, re.I)), '')
    if not header:
        return result
    columns = [x.strip().lower() for x in header.split('|')[1:-1]]
    if 'all' not in columns:
        return result
    index = columns.index('all')
    for label, key in [('WNS (ns)', 'slack_ns'), ('TNS (ns)', 'tns_ns'), ('Violating Paths', 'violations'), ('All Paths', 'paths')]:
        line = next((x for x in text.splitlines() if label in x), '')
        cells = [x.strip() for x in line.split('|')[1:-1]]
        if len(cells) > index and re.fullmatch(NUMBER, cells[index]):
            value = float(cells[index])
            if math.isfinite(value):
                result[key] = int(value) if key in ('paths', 'violations') else value
    if result['paths'] == 0:
        result['slack_ns'] = None
    return result

def collect(stage, directory, corner=None):
    directory = Path(directory)
    paths = list(directory.glob('*.log')) + list((directory/'reports').glob('*.rpt'))
    result = dict(stage=stage, corner=corner, **messages(paths))
    if stage == 'pt':
        scale = unit_ns(read(directory/'reports/units.rpt'))
        result['setup'] = {'slack_ns': pt_slack(read(directory/'reports/setup.rpt'), scale)}
        result['hold'] = {'slack_ns': pt_slack(read(directory/'reports/hold.rpt'), scale)}
        result['unit_verified'] = scale is not None
        result['review_notes'] = []
        for name in ('check_timing', 'parasitics', 'coverage'):
            path = directory/'reports'/(name+'.rpt')
            if not path.is_file() or not path.stat().st_size:
                result['review_notes'].append('Missing integrity report: '+str(path))
            else:
                for line in read(path).splitlines():
                    if re.search(r'unconstrained|unannotated|not annotated|no_clock|untested|no_input_delay|no_output_delay', line, re.I):
                        result['review_notes'].append(name+': '+line.strip())
        result['integrity_status'] = 'REVIEW' if result['review_notes'] else 'NO_FLAGS_DETECTED'
    else:
        for mode in ('setup', 'hold'):
            candidates = [directory/'reports'/name for name in (
                mode+'.summary.gz', mode+'_hold.summary.gz', mode+'.summary', mode+'_hold.summary')]
            path = next((p for p in candidates if p.is_file()), None)
            result[mode] = innovus(read(path)) if path else {'slack_ns': None}
            if path:
                result[mode]['source'] = str(path)
    modes = ('setup',) if stage == 'placement' else ('setup', 'hold')
    if stage in ('pt','placement','cts','route','chipfinish'):
        missing = [m for m in modes if result[m]['slack_ns'] is None]
        result['timing_status'] = ('INCOMPLETE' if missing else 'VIOLATED' if any(result[m]['slack_ns'] < 0 for m in modes) else 'MET')
    else:
        result['timing_status'] = 'N/A'
    return result

def display(result):
    print('[{}{}] run={} timing={}'.format(result['stage'], '/'+result['corner'] if result.get('corner') else '', result.get('status', 'UNKNOWN'), result.get('timing_status', 'N/A')))
    for mode in ('setup', 'hold'):
        data = result.get(mode, {})
        value = data.get('slack_ns')
        if value is not None:
            extra = ', TNS={:.4f} ns, violations={}'.format(data['tns_ns'], data.get('violations')) if data.get('tns_ns') is not None else ''
            print('  {} worst slack: {:.4f} ns{}'.format(mode, value, extra))
        elif result.get('timing_status') != 'N/A':
            print('  {} worst slack: N/A (not analyzed, no paths, missing report or unknown unit)'.format(mode))
    print('  errors={}, warnings={}'.format(len(result.get('errors', [])), len(result.get('warnings', []))))
    if result.get('review_notes'):
        print('  Constraint/parasitic coverage requires review:')
        for note in result['review_notes'][:5]: print('  '+note)
    for kind in ('errors', 'warnings'):
        for line in result.get(kind, [])[:4]:
            print('  '+line)
