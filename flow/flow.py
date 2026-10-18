#!/usr/bin/env python3
"""Make owns the graph; this helper validates and executes one stage at a time."""
import gzip
import hashlib
import math
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import time
import uuid

import reports
import readiness
import report_store
from eco_versions import Versions
from state import Workspace, STAGES, identifier, files_hash, read_json, write_json, no_links

ROOT = Path(__file__).resolve().parents[1]
PNR = ('init', 'floorplan', 'powerplan', 'placement', 'cts', 'route', 'chipfinish')
KEYS = '''PROJECT_NAME DESIGN_NAME TOP_MODULE TECH RTL_LIST TB_LIST TB_TOP DUT_INSTANCE CLOCK_NAME CLOCK_PORT INCLUDE_DIRS
FLOORPLAN_MODE CORE_WIDTH CORE_HEIGHT CORE_MARGIN
POWER_NET GROUND_NET RTL_MODELS GATE_STAGE TIMESCALE
SYN_LIBS LEFS GDS_FILES GDS_MAP SIM_LIBS LVS_LIBS CDL_FILES CORNERS SETUP_CORNER HOLD_CORNER
HCELL_FILE CTS_MAX_TRANSITION CTS_TARGET_SKEW CTS_MAX_FANOUT RTL_DEFINES CPU CALIBRE_INNOVUS_TCL VCS VERDI VERDI_COV VERDI_HOME DC_SHELL FM_SHELL INNOVUS CALIBREDRV V2LVS STARXTRACT PT_SHELL'''.split()

def tcl(value):
    if isinstance(value, (list, tuple)):
        return '[list ' + ' '.join(tcl(v) for v in value) + ']'
    value = str(value).replace('\\', '/') if isinstance(value, Path) else str(value)
    return '"' + ''.join('\\' + c if c in '\\"$[]' else '\\n' if c == '\n' else c for c in value) + '"'

def put(path, text):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text, encoding='utf-8')

def copy_overlay(source, destination):
    """Check only paths being copied; leave unrelated tool database links alone."""
    source, destination = no_links(source), no_links(destination)
    destination.mkdir(parents=True, exist_ok=True)
    for child in source.iterdir():
        no_links(child)
        target = no_links(destination/child.name)
        if child.is_dir():
            copy_overlay(child, target)
        else:
            shutil.copy2(str(child), str(target))

def include_refs(text, env):
    """Follow literal includes; honor environment-gated optional foundry sections."""
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.S)
    stack = []
    for line in text.splitlines():
        line = line.split('//', 1)[0].strip()
        match = re.match(r'#(IFDEF|IFNDEF)\s+(\S+)(?:\s+(\S+))?', line, re.I)
        if match:
            kind, name, value = match.groups()
            active = None
            if name.startswith('$'):
                active = env.get(name[1:]) == value if value else bool(env.get(name[1:]))
                if kind.upper() == 'IFNDEF': active = not active
            stack.append(active)
        elif line.startswith('#ELSE') and stack:
            if stack[-1] is not None: stack[-1] = not stack[-1]
        elif line.startswith('#ENDIF') and stack:
            stack.pop()
        elif False not in stack:
            match = re.match(r'INCLUDE\s+"?([^"\s]+)', line, re.I)
            if match: yield match[1]

class Flow:
    def __init__(self, root=ROOT, env=None):
        self.root = Path(root).resolve()
        self.env = dict(os.environ if env is None else env)
        self.cfg = {key: self.env.get(key, '') for key in KEYS}
        if self.cfg['GATE_STAGE'] not in ('dc', 'chipfinish'):
            # Cleaning is independent of nonessential simulation configuration.
            self.cfg['GATE_STAGE'] = '__INVALID_GATE_STAGE__'
        self.ws = None
        self.workspace_error = ''
        try:
            self.ws = Workspace(self.root, self.cfg['DESIGN_NAME'], self.cfg['TECH'])
        except ValueError as exc:
            self.workspace_error = str(exc)
        try:
            technology = identifier(self.cfg['TECH'], 'TECH')
        except ValueError:
            technology = '__UNCONFIGURED__'
        self.tech = self.root / 'tech' / 'current'
        # 单一工艺固定在 tech/current；TECH 仅用于标识结果。
        self.corners = read_json(self.tech / 'corners.json')
        self.memo = {}

    def require_workspace(self):
        if self.ws is None:
            raise ValueError(self.workspace_error + '; fill config.mk, then run make check')
        return self.ws

    def words(self, key):
        return shlex.split(self.cfg.get(key, ''))

    def path(self, key):
        value = self.cfg.get(key, '')
        return self.root / value if value else self.root / '__MISSING_' / key

    def libs(self, key):
        return [self.tech / p for p in self.words(key)]

    def sources(self, key):
        path = self.path(key)
        if not path.is_file():
            return [path]
        result = []
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            line = line.strip()
            if not line or line.startswith(('#', '//')):
                continue
            if line.startswith(('-', '+')):
                raise ValueError('{}: only source paths are supported; no nested filelists/options'.format(path))
            result.append(self.root / line)
        if not result:
            raise ValueError('Empty source list: ' + str(path))
        return result

    def deps(self, stage):
        if stage in PNR:
            i = PNR.index(stage)
            return [PNR[i-1] if i else 'dc']
        dependencies = {'eco': ['chipfinish'], 'hcell': ['chipfinish'], 'formal': ['dc'],
                'postsim': [self.cfg['GATE_STAGE']] if self.cfg['GATE_STAGE'] in ('dc','chipfinish') else [],
                'postsim_sdf': ['chipfinish'], 'merge': ['chipfinish'],
                'lvs-input': ['merge', 'chipfinish', 'hcell'], 'rc': ['chipfinish'],
                'pt': ['rc', 'chipfinish'], 'drc': ['merge'], 'lvs': ['lvs-input']}.get(stage, [])
        return [self.final_stage() if name == 'chipfinish' else name for name in dependencies] if stage != 'eco' else dependencies

    def final_stage(self):
        if self.ws is None:
            return 'chipfinish'
        path = self.ws.base/'active-final.json'
        if not path.exists():
            return 'chipfinish'
        selection = read_json(path)
        stage = selection.get('stage') if isinstance(selection, dict) else None
        if stage not in ('chipfinish', 'eco'):
            raise ValueError('Invalid active final stage: ' + str(stage))
        return stage

    def final_directory(self):
        selection = read_json(self.require_workspace().base/'active-final.json')
        if selection.get('git_version'):
            return Versions(self).directory(selection['revision'])/'final'
        return self.require_workspace().stage(self.final_stage())

    def record(self, stage):
        if stage not in STAGES:
            raise ValueError('Unknown stage: ' + stage)
        if self.ws is None:
            return {}
        if stage == 'eco' and read_json(self.ws.base/'active-final.json').get('git_version'):
            return read_json(self.final_directory()/'result.json')
        return read_json(self.ws.stage(stage)/'result.json')

    def checkpoint(self, stage):
        directory = self.final_directory() if stage == 'eco' else self.require_workspace().stage(stage)
        relative = self.record(stage).get('checkpoint_rel', 'design.enc')
        if relative != 'design.enc' and not re.fullmatch(r'manual-resume/[0-9a-f]{32}/design\.enc', relative):
            raise ValueError('Invalid checkpoint path in stage record: ' + str(relative))
        return directory/relative

    def valid(self, stage):
        if self.ws is None:
            return False
        if stage in self.memo:
            return self.memo[stage]
        try:
            record = self.record(stage)
            valid = (record.get('status') == 'OK' and
                     all(self.valid(d) for d in self.deps(stage)))
            if valid:
                expected = record.get('artifacts', {})
                # Completion only: do not compare inputs, timestamps or content hashes.
                # Some checkpoint sidecars were legitimately empty when saved.
                empty_hash = hashlib.sha256(b'').hexdigest()
                valid = bool(expected) and all(
                    (self.ws.stage(stage)/path).is_file() and
                    ((self.ws.stage(stage)/path).stat().st_size > 0 or saved_hash == empty_hash)
                    for path, saved_hash in expected.items())
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            valid = False
        self.memo[stage] = valid
        return valid

    def preflight(self, stage, upstream=True, tools=True):
        if stage not in STAGES:
            raise ValueError('Unknown stage: ' + stage)
        if stage == 'eco':
            return [] if self.valid('eco') else ['Not configured: export and accept the manual ECO first']
        issues = readiness.configuration_issues(self, stage)
        if self.workspace_error:
            issues.append('Not configured: ' + self.workspace_error)
        def required_sources(key):
            try:
                return self.sources(key)
            except ValueError as exc:
                issues.append('Not configured: ' + str(exc))
                return [self.path(key)]
        for key in ('TOP_MODULE', 'TB_TOP'):
            if self.cfg[key] and not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_$]*', self.cfg[key]):
                issues.append('Not configured: invalid HDL identifier: ' + key)
        required = []
        if stage in ('dc','formal','sim','cov'):
            required += required_sources('RTL_LIST')
        if stage in ('sim','cov','postsim','postsim_sdf'):
            required += required_sources('TB_LIST')
            if not self.cfg['TB_TOP']: issues.append('Not configured: TB_TOP is blank')
        if stage in ('sim','cov'):
            required += [self.root/p for p in self.words('RTL_MODELS')]
        if stage in ('dc','formal','sim','cov','postsim','postsim_sdf'):
            for path in (self.root/p for p in self.words('INCLUDE_DIRS')):
                if not path.is_dir(): issues.append('Missing include directory: '+str(path))
        if stage in ('dc','formal'):
            required += self.libs('SYN_LIBS')
            if not self.words('SYN_LIBS'): issues.append('Missing SYN_LIBS')

        if stage in ('postsim','postsim_sdf'):
            required += self.libs('SIM_LIBS')
            if not self.words('SIM_LIBS'): issues.append('Missing SIM_LIBS for gate simulation')
            if self.cfg['GATE_STAGE'] not in ('dc','chipfinish'): issues.append('Not configured: GATE_STAGE must be dc or chipfinish')
        if stage in PNR or stage in ('dc','rc'):
            if not self.cfg['CPU'].isdigit() or int(self.cfg['CPU'])<1: issues.append('Not configured: CPU must be a positive integer')
        if stage == 'postsim_sdf' and not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.$]*', self.cfg['DUT_INSTANCE']):
            issues.append('Not configured: missing/invalid DUT_INSTANCE for SDF')
        if stage in PNR:
            required += self.libs('LEFS')
            if not self.words('LEFS'): issues.append('缺少 LEFS 工艺库配置')
        if stage == 'chipfinish': required += self.libs('GDS_MAP')
        if stage in PNR or stage in ('rc','pt'):
            selected = self.words('CORNERS')
            if not selected: issues.append('Missing CORNERS')
            for name in selected:
                identifier(name, 'corner')
                c = self.corners.get(name)
                if not isinstance(c, dict):
                    issues.append('Missing corner: ' + name); continue
                if stage in PNR or stage=='rc':
                    try:
                        if not math.isfinite(float(c['temperature'])): raise ValueError()
                    except (KeyError,TypeError,ValueError): issues.append('Missing/invalid corner temperature: '+name)
                keys = ('lib','captable') if stage in PNR else ('nxtgrd','mapping') if stage == 'rc' else ('db',)
                for key in keys:
                    value = c.get(key, [])
                    values = value if isinstance(value,list) else [value]
                    if not values or not all(values): issues.append('Missing corner {} {}'.format(name,key))
                    required += [self.tech/p for p in values]
            if stage in PNR and any(self.cfg[k] not in selected for k in ('SETUP_CORNER','HOLD_CORNER')):
                issues.append('SETUP_CORNER and HOLD_CORNER must belong to CORNERS')

        if stage == 'hcell':
            required += [self.path('HCELL_FILE')] if self.cfg['HCELL_FILE'] else []
        if stage == 'merge':
            required += self.libs('GDS_FILES')
            if not self.words('GDS_FILES'): issues.append('Missing GDS_FILES')
        if stage == 'lvs-input':
            required += self.libs('CDL_FILES') + self.libs('LVS_LIBS')
            for k in ('CDL_FILES','LVS_LIBS'):
                if not self.words(k): issues.append('Missing ' + k)
        if stage in ('drc','lvs'):
            if tools and not self.env.get('DISPLAY') and sys.platform!='win32': issues.append('DISPLAY missing for GUI')
            rule_dir = self.tech/stage
            required += [rule_dir/('rules.cal.in' if stage == 'drc' else 'rules.cal')]
            # Check literal include references in all bundled decks, including optional branches.
            for deck in rule_dir.rglob('*'):
                if deck.is_file():
                    for ref in include_refs(deck.read_text(errors='replace'), self.env):
                        if '$' not in ref and not ref.startswith('__'):
                            required.append(rule_dir/('design.cal.in' if stage=='lvs' and ref=='./sample_design_inc.cal' else ref))
        if stage == 'rc': required += [self.tech/'rc/options.cmd'] + self.libs('LEFS')
        if stage in ('sim','cov','postsim','postsim_sdf') and self.cfg['VERDI_HOME']:
            required += [Path(self.cfg['VERDI_HOME'])/'share/PLI/VCS/LINUX64'/p for p in ('novas.tab','pli.a')]
        for path in required:
            if not path.is_file() or path.stat().st_size == 0: issues.append('Missing/empty: ' + str(path))
        if upstream:
            for dep in self.deps(stage):
                if not self.valid(dep): issues.append('Upstream incomplete: ' + dep + ' (run make '+stage+')')
        if tools and not (stage == 'hcell' and self.cfg['HCELL_FILE']):
            tool = {'dc':'DC_SHELL','formal':'FM_SHELL','merge':'CALIBREDRV','lvs-input':'V2LVS',
                    'hcell':'INNOVUS','rc':'STARXTRACT','pt':'PT_SHELL','drc':'CALIBREDRV','lvs':'CALIBREDRV'}.get(stage, 'INNOVUS' if stage in PNR else 'VCS')
            command = shlex.split(self.cfg.get(tool, ''))
            if not command or not shutil.which(command[0]): issues.append('Tool unavailable: ' + tool)
            if stage == 'cov' and self.env.get('GUI','0') == '1':
                viewer = shlex.split(self.cfg['VERDI_COV'])
                if not viewer or not shutil.which(viewer[0]): issues.append('Tool unavailable: VERDI_COV')
                if not self.env.get('DISPLAY') and sys.platform != 'win32': issues.append('DISPLAY missing for coverage GUI')
        return sorted(set(issues))

    def config_tcl(self, directory, stage, corner=None):
        values = dict(self.cfg)
        for key in ('SYN_LIBS','LEFS','GDS_FILES','GDS_MAP'):
            values[key] = self.libs(key) if key != 'GDS_MAP' else (self.tech/self.cfg[key])
        values.update(ROOT=self.root, FLOW_DIR=self.root/'flow', TECH_DIR=self.tech,
                      INCLUDE_DIRS=[self.root/p for p in self.words('INCLUDE_DIRS')],
                      STAGE=stage, RTL_FILES=self.sources('RTL_LIST'),
                      NETLIST_OUT=directory/(self.cfg['DESIGN_NAME']+'.v'),
                      SDC_OUT=directory/(self.cfg['DESIGN_NAME']+'.sdc'),
                      SDF_OUT=directory/(self.cfg['DESIGN_NAME']+'.sdf'),
                      NETLIST_IN=self.ws.stage('dc')/(self.cfg['DESIGN_NAME']+'.v'),
                      SDC_IN=self.ws.stage('dc')/(self.cfg['DESIGN_NAME']+'.sdc'),
                      SVF_IN=self.ws.stage('dc')/'design.svf', CHECKPOINT_OUT=directory/'design.enc')
        if stage in PNR and stage != 'init': values['CHECKPOINT_IN']=self.checkpoint(self.deps(stage)[0])
        if corner:
            c = self.corners[corner]
            values.update(CORNER=corner, CORNER_DB=[self.tech/p for p in c['db']],
                          PT_DERATE=[v for pair in c.get('pt_derate',{}).items() for v in pair],
                          NETLIST_IN=self.final_directory()/(self.cfg['DESIGN_NAME']+'.v'),
                          SDC_IN=self.final_directory()/(self.cfg['DESIGN_NAME']+'.sdc'),
                          SPEF_IN=self.ws.stage('rc')/corner/(self.cfg['DESIGN_NAME']+'.spef'))
        put(directory/'config.tcl', ''.join('set {} {}\n'.format(k,tcl(v)) for k,v in values.items()))

    def command(self, tool, args, directory, logfile='tool.log', interactive=False):
        command = shlex.split(self.cfg[tool]) + list(map(str,args))
        print('Running {} in {}'.format(tool, directory), flush=True)
        if interactive:
            # Readline needs real terminal input AND output; native -log records GUI sessions.
            if not sys.stdin.isatty() or not sys.stdout.isatty():
                raise ValueError('Interactive Innovus needs a terminal; launch this Make command from a desktop terminal')
            terminal, attributes = None, None
            if os.name == 'posix':
                import termios
                terminal = sys.stdin.fileno()
                attributes = termios.tcgetattr(terminal)
            try:
                code = subprocess.call(command, cwd=directory)
            finally:
                if attributes is not None:
                    termios.tcsetattr(terminal, termios.TCSADRAIN, attributes)
            if code:
                raise RuntimeError('{} exited {}'.format(tool, code))
            return
        with (directory/logfile).open('w', encoding='utf-8') as log:
            proc = subprocess.Popen(command, cwd=directory, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, errors='replace')
            with proc.stdout:
                try:
                    for line in proc.stdout:
                        log.write(line); log.flush(); print(line, end='', flush=True)
                    code = proc.wait()
                except BaseException:
                    proc.terminate(); proc.wait(); raise
        if code: raise RuntimeError('{} exited {}'.format(tool,code))

    def script(self, tool, directory, script, innovus=False):
        put(directory/'run.tcl', 'if {[catch {\nsource '+tcl(script)+'\n} msg opts]} {\nputs stderr "FLOW_ERROR: $msg"\nputs stderr [dict get $opts -errorinfo]\nexit 1\n}\nset f [open tool.done w]\nputs $f FLOW_DONE\nclose $f\nexit 0\n')
        args = ['-no_gui','-files','run.tcl'] if innovus else ['-f','run.tcl']
        self.command(tool,args,directory)
        if not (directory/'tool.done').is_file(): raise RuntimeError('Tool did not complete run.tcl')

    def mmmc(self, directory):
        lines = ['create_constraint_mode -name func -sdc_files [list $SDC_IN]']
        for name in self.words('CORNERS'):
            c = self.corners[name]; scale=c.get('rc_scale',1)
            lines += ['create_library_set -name lib_'+name+' -timing '+tcl([self.tech/p for p in c['lib']]),
                      'create_rc_corner -name rc_'+name+' -cap_table '+tcl(self.tech/c['captable'])+' -T '+str(c['temperature'])+' '+ ' '.join('-'+k+' '+str(scale) for k in ('preRoute_res','preRoute_cap','preRoute_clkres','preRoute_clkcap','postRoute_res','postRoute_cap','postRoute_xcap','postRoute_clkres','postRoute_clkcap')),
                      'create_delay_corner -name delay_'+name+' -library_set lib_'+name+' -rc_corner rc_'+name,
                      'create_analysis_view -name view_'+name+' -constraint_mode func -delay_corner delay_'+name]
        lines += ['set_analysis_view -setup view_$SETUP_CORNER -hold view_$HOLD_CORNER']
        put(directory/'mmmc.tcl','\n'.join(lines)+'\n')
        derates=[]
        for name in self.words('CORNERS'):
            for key,value in self.corners[name].get('pnr_derate',{}).items():
                when,what=key.split('_')
                derates.append('set_timing_derate -delay_corner delay_{} -{} -{} {}'.format(name,when,what,value))
        put(directory/'derates.tcl','\n'.join(derates)+'\n')

    def execute(self, stage, directory):
        name=self.cfg['DESIGN_NAME']; final=self.final_directory()
        if stage in ('dc','formal'):
            self.config_tcl(directory,stage)
            self.script('DC_SHELL' if stage=='dc' else 'FM_SHELL',directory,self.root/('scripts/dc.tcl' if stage=='dc' else 'scripts/formal.tcl'))
        elif stage in PNR:
            self.config_tcl(directory,stage); self.mmmc(directory)
            self.script('INNOVUS',directory,self.root/'flow/pnr.tcl',True)
        elif stage in ('sim','cov','postsim','postsim_sdf'):
            sources = self.sources('RTL_LIST') + [self.root/p for p in self.words('RTL_MODELS')] if stage in ('sim','cov') else [(self.final_directory() if stage=='postsim_sdf' or self.cfg['GATE_STAGE']=='chipfinish' else self.ws.stage('dc'))/(name+'.v')] + self.libs('SIM_LIBS')
            args=['-full64','-sverilog','-debug_access+all','-timescale='+self.cfg['TIMESCALE'],'-top',self.cfg['TB_TOP'],'-o','simv']
            args += ['+incdir+'+str(self.root/p) for p in self.words('INCLUDE_DIRS')]
            if stage in ('sim','cov'):
                args += ['+define+'+define for define in self.words('RTL_DEFINES')]
            if self.cfg['VERDI_HOME']:
                args += ['+define+DUMP_FSDB','-P',str(Path(self.cfg['VERDI_HOME'])/'share/PLI/VCS/LINUX64/novas.tab'),str(Path(self.cfg['VERDI_HOME'])/'share/PLI/VCS/LINUX64/pli.a')]
            if stage=='cov': args += ['-cm','line+cond+fsm+tgl+branch','-cm_dir','coverage.vdb']
            if stage=='postsim_sdf': args += ['-sdf','max:'+self.cfg['DUT_INSTANCE']+':'+str(final/(name+'.sdf'))]
            self.command('VCS',args+list(map(str,sources+self.sources('TB_LIST'))),directory,'compile.log')
            # Run the generated executable without a shell or user-interpolated command.
            old=self.cfg['VCS']; self.cfg['VCS']=shlex.quote(str(directory/'simv'))
            try: self.command('VCS',['-cm','line+cond+fsm+tgl+branch','-cm_dir','coverage.vdb'] if stage=='cov' else [],directory,'simulation.log')
            finally: self.cfg['VCS']=old
        elif stage=='hcell':
            if self.cfg['HCELL_FILE']:
                shutil.copy2(str(self.path('HCELL_FILE')), str(directory/'hcell_list'))
                return
            if (final/'hcell_list').is_file() and (final/'hcell_list').stat().st_size:
                shutil.copy2(str(final/'hcell_list'), str(directory/'hcell_list'))
                return
            self.config_tcl(directory, stage)
            with (directory/'config.tcl').open('a', encoding='utf-8') as stream:
                stream.write('set CHECKPOINT_IN ' + tcl(final/'design.enc') + '\n')
            self.script('INNOVUS', directory, self.root/'flow/hcell.tcl', True)
        elif stage=='merge':
            args='layout filemerge '+ ' '.join('-in '+tcl(p) for p in [final/(name+'.gds')]+self.libs('GDS_FILES'))+' -topcell '+tcl(self.cfg['TOP_MODULE'])+' -mode overwrite -out '+tcl(directory/(name+'.gds'))+'\n'
            put(directory/'merge.tcl',args); self.command('CALIBREDRV',['merge.tcl'],directory)
        elif stage=='lvs-input':
            merged=self.ws.stage('merge')/(name+'.gds')
            put(directory/'label.tcl','set INPUT_GDS '+tcl(merged)+'\nset OUTPUT_GDS '+tcl(directory/(name+'.gds'))+'\nsource '+tcl(final/'add_pg_text.tcl')+'\n')
            self.command('CALIBREDRV',['label.tcl'],directory,'labels.log')
            args=['-sl','-v',str(final/(name+'_lvs.v')),'-o',str(directory/(name+'.spi')),'-s0',self.cfg['GROUND_NET'],'-s1',self.cfg['POWER_NET']]
            for p in self.libs('CDL_FILES'): args += ['-s',str(p)]
            for p in self.libs('LVS_LIBS'): args += ['-l',str(p)]
            self.command('V2LVS',args,directory)
        elif stage in ('rc','pt'):
            for corner in self.words('CORNERS'):
                sub=directory/corner; (sub/'reports').mkdir(parents=True)
                if stage=='pt':
                    self.config_tcl(sub,stage,corner); self.script('PT_SHELL',sub,self.root/'scripts/pt.tcl')
                else:
                    c=self.corners[corner]
                    lines=['TOP_DEF_FILE: '+str(final/(name+'.def'))]+['LEF_FILE: '+str(p) for p in self.libs('LEFS')]
                    lines += ['MAPPING_FILE: '+str(self.tech/c['mapping']),'TCAD_GRD_FILE: '+str(self.tech/c['nxtgrd']),
                              'NETLIST_FILE: '+str(sub/(name+'.spef')), 'NETLIST_FORMAT: SPEF', 'OPERATING_TEMPERATURE: '+str(c['temperature']), 'NUM_CORES: '+self.cfg['CPU']]
                    put(sub/'rc.cmd','\n'.join(lines)+'\n'+(self.tech/'rc/options.cmd').read_text())
                    self.command('STARXTRACT',['rc.cmd'],sub)

    def outputs(self, stage, directory):
        name=self.cfg['DESIGN_NAME']
        if stage in PNR:
            names=['design.enc']
            if stage=='chipfinish': names += [name+suffix for suffix in ('.v','_lvs.v','.sdc','.sdf','.def','.gds','.lef')] + ['add_pg_text.tcl', 'hcell_list']
        else:
            names={'dc':[name+'.v',name+'.sdc',name+'.sdf','design.svf'], 'formal':['reports/verification.rpt'],
                   'sim':['simv','simulation.log'],'cov':['simv','simulation.log'],
                   'postsim':['simv','simulation.log'],'postsim_sdf':['simv','simulation.log'],
                   'hcell':['hcell_list'], 'merge':[name+'.gds'],'lvs-input':[name+'.gds',name+'.spi']}.get(stage,[])
            if stage=='rc': names=[c+'/'+name+'.spef' for c in self.words('CORNERS')]
            if stage=='pt': names=[c+'/reports/'+p+'.rpt' for c in self.words('CORNERS') for p in ('setup','hold','units','check_timing','parasitics','coverage')]
        missing=[p for p in names if not (directory/p).is_file() or not (directory/p).stat().st_size]
        if missing: raise RuntimeError('Missing/empty outputs: '+', '.join(missing))
        # Checkpoint sidecar directories are part of the artifact, not just the .enc stub.
        return files_hash([directory/p for p in names]+list(directory.glob('design.enc*'))+list(directory.rglob('reports')))

    def resume_route(self):
        """Check and finish a saved manual repair without routing it again."""
        with self.require_workspace().lock():
            if self.final_stage() != 'chipfinish':
                raise ValueError('Use make eco-use-original before resuming the original route branch')
            directory = self.ws.require_checkpoint_tree('route', self.tech)
            source = directory/'manual_fixed.enc'
            if not source.is_file() or not Path(str(source)+'.dat').is_dir():
                raise ValueError('Save the repaired design as route/manual_fixed.enc first')
            issues = self.preflight('route')
            if issues:
                raise ValueError('\n'.join(issues))
            attempt = directory/'manual-resume'/uuid.uuid4().hex
            (attempt/'reports').mkdir(parents=True)
            self.config_tcl(attempt, 'route')
            self.mmmc(attempt)
            with (attempt/'config.tcl').open('a', encoding='utf-8') as stream:
                stream.write('set CHECKPOINT_IN ' + tcl(source) + '\n')
            previous = self.record('route')
            if previous:
                history = self.ws.require_record_directory('route')/'record-history'
                history.mkdir(exist_ok=True)
                write_json(history/(uuid.uuid4().hex+'.json'), previous)
            self.invalidate_dependents('route')
            record = dict(stage='route', status='RUNNING', started=time.time(), manual_source=str(source))
            write_json(directory/'result.json', record)
            write_json(self.ws.base/'latest.json', dict(stage='route'))
            failure, result = None, None
            try:
                self.script('INNOVUS', attempt, self.root/'flow/resume_route.tcl', True)
                artifacts = self.outputs('route', attempt)
                result = reports.collect('route', attempt)
                if result['errors'] or result['timing_status'] == 'INCOMPLETE':
                    raise RuntimeError('Manual route completion has tool errors or incomplete timing reports')
                record.update(status='OK', artifacts=artifacts,
                              checkpoint_rel=(attempt/'design.enc').relative_to(directory).as_posix())
            except (OSError, ValueError, RuntimeError, KeyboardInterrupt) as exc:
                failure = exc
                record.update(status='FAILED', error=str(exc))
            if result is not None:
                result['status'] = record['status']
                record['summaries'] = [result]
            record['finished'] = time.time()
            write_json(directory/'result.json', record)
            self.memo.clear()
            if result is not None:
                reports.display(result)
            print('Manual route attempt: ' + str(attempt))
            if failure is not None:
                raise RuntimeError(record['error']) from failure
            print('Manual route accepted. Continue with make chipfinish GUI=0.')

    def invalidate_dependents(self, changed):
        """An explicit rerun supersedes downstream results; ordinary edits do not."""
        def depends_on(stage, seen):
            if stage in seen:
                return False
            seen.add(stage)
            dependencies = self.deps(stage)
            return changed in dependencies or any(depends_on(dep, seen) for dep in dependencies)
        revision = uuid.uuid4().hex
        affected = [stage for stage in STAGES if stage != changed and depends_on(stage, set())]
        for stage in affected:
            record = self.record(stage)
            if record:
                directory = self.ws.require_record_directory(stage)
                history = directory/'record-history'
                history.mkdir(exist_ok=True)
                write_json(history/(revision+'.json'), record)
                record.update(status='INVALIDATED', reason='Explicit rerun of upstream stage: '+changed)
                write_json(directory/'result.json', record)
        self.memo.clear()

    def run(self, stage):
        if stage == 'eco':
            raise ValueError('Use make eco, eco_export in Innovus, then make eco-accept')
        selected = self.env.get('FORCE_STAGE', '').split()
        if any(name not in STAGES for name in selected):
            raise ValueError('Unknown FORCE_STAGE: ' + ' '.join(selected))
        with self.require_workspace().lock():
            if (stage in PNR or stage == 'dc') and (self.ws.base/'versions/baseline.json').exists() and (self.env.get('FORCE') == '1' or stage in selected):
                raise ValueError('已有 ECO 版本基线。重新实现请先 make clean；继续修版请 make eco。')
            if self.valid(stage) and self.env.get('FORCE','0')!='1' and stage not in selected:
                print('[{}] 已完成且结果齐全，跳过'.format(stage)); return
            issues=self.preflight(stage)
            if issues: raise ValueError('\n'.join(issues))
            if self.record(stage):
                self.invalidate_dependents(stage)
            report_store.collect(self, stage)
            self.ws.remove(stage)
            directory=self.ws.stage(stage); (directory/'reports').mkdir(parents=True)
            record={'stage':stage,'status':'RUNNING','started':time.time()}
            write_json(directory/'result.json',record)
            write_json(self.ws.base/'latest.json',{'stage':stage})
            error=None
            try:
                self.execute(stage,directory)
                record['artifacts']=self.outputs(stage,directory)
                record['status']='OK'
            except (OSError,ValueError,RuntimeError,KeyboardInterrupt) as exc:
                error=exc; record['status']='FAILED'; record['error']=str(exc)
            for path in directory.rglob('*.gz'):
                if 'reports' in path.parts and not any(p.endswith('.enc.dat') for p in path.parts):
                    try:
                        with gzip.open(path,'rb') as source: put_bytes(path.with_suffix(''),source.read())
                    except (OSError,EOFError) as exc:
                        record['status']='FAILED'; record['error']=str(exc); error=exc
            summaries=[]
            for corner in self.words('CORNERS') if stage=='pt' else [None]:
                result=reports.collect(stage,directory/corner if corner else directory,corner)
                if result['errors'] or result['timing_status']=='INCOMPLETE': record['status']='FAILED'
                result['status']=record['status']; summaries.append(result)
            log_errors=reports.messages(list(directory.rglob('*.log')))['errors']
            if log_errors: record['status']='FAILED'; record['error']='Tool log contains errors'; record['log_errors']=log_errors
            record.update(summaries=summaries,finished=time.time())
            # Hash reports after decompression as well.
            if record['status']=='OK': record['artifacts']=self.outputs(stage,directory)
            for result in summaries:
                result['status']=record['status']
            write_json(directory/'result.json',record)
            report_store.collect(self, stage)
            for result in summaries: reports.display(result)
            if record['status']!='OK': raise RuntimeError(record.get('error','Missing timing reports or reported tool errors')) from error
        self.memo.clear()
        goals=self.env.get('FLOW_GOALS','').split()
        if stage in PNR and self.env.get('GUI','0')=='1' and (stage in goals or stage=='chipfinish' and 'pnr' in goals):
            self.open_gui('pnr',stage)

    def check(self):
        return readiness.check(self)

    def progress(self):
        groups = (
            ('前端', ('sim', 'cov', 'dc', 'formal', 'postsim', 'postsim_sdf')),
            ('布局布线', PNR),
            ('手工 ECO / LVS 单元', ('eco', 'hcell')),
            ('签核输入 / 时序', ('merge', 'lvs-input', 'rc', 'pt')),
        )
        styles = {
            'OK': ('■', '32'), 'PENDING': ('□', '90'),
            'FAILED': ('✗', '31'),
            'RUNNING': ('▶', '36'), 'UNKNOWN': ('?', '31'),
        }
        color = (sys.stdout.isatty() and 'NO_COLOR' not in self.env
                 and self.env.get('TERM') != 'dumb')
        states, notes = {}, []
        self.memo.clear()
        print('Progress: {} / {}'.format(self.cfg['DESIGN_NAME'], self.cfg['TECH']))
        for title, stages in groups:
            print('  ' + title)
            cells = []
            for stage in stages:
                try:
                    record = self.record(stage)
                    status = record.get('status')
                    if not record:
                        state = 'UNKNOWN' if self.ws is not None and (self.ws.stage(stage)/'result.json').exists() else 'PENDING'
                    elif status == 'INVALIDATED':
                        state = 'PENDING'
                    elif status in ('FAILED', 'RUNNING'):
                        state = status
                    elif status == 'OK':
                        state = 'OK' if self.valid(stage) else 'PENDING'
                    else:
                        state = 'UNKNOWN'
                    if stage in ('route', 'chipfinish', 'eco'):
                        base = self.final_directory() if stage == 'eco' else self.ws.stage(stage)
                        report = base/'reports'/('route_drc_summary.rpt' if stage == 'route' else 'chipfinish_drc_summary.rpt')
                        if report.is_file():
                            counts = re.findall(r'violations=(\d+)', report.read_text())
                            if counts and int(counts[-1]):
                                notes.append('{}：仍有 {} 条几何 DRC，执行 OK 不代表 DRC 通过'.format(stage, counts[-1]))
                    for result in record.get('summaries', []):
                        timing = result.get('timing_status')
                        if timing in ('VIOLATED', 'INCOMPLETE'):
                            notes.append('{}{}: timing {}'.format(
                                stage, '/'+result['corner'] if result.get('corner') else '', timing))
                except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
                    state = 'UNKNOWN'
                    notes.append('{}: {}'.format(stage, exc))
                states[stage] = state
                mark, shade = styles[state]
                cell = '[{}] {:<12} {:<7}'.format(mark, stage, state)
                cells.append('\033[{}m{}\033[0m'.format(shade, cell) if color else cell)
            for offset in range(0, len(cells), 3):
                print('    ' + '  '.join(cells[offset:offset+3]).rstrip())
        print('  Completed stages: {}/{} (optional branches included)'.format(
            sum(state == 'OK' for state in states.values()), len(states)))
        print('  ■ completed + results present  □ not complete / missing result or prerequisite  ✗ failed  ▶ recorded running  ? unknown')
        print('  当前最终来源：' + self.final_stage())
        selection = read_json(self.ws.base/'active-final.json') if self.ws else {}
        if selection.get('git_version'): print('  Git 版本：' + selection['revision'][:12])
        print('  DRC / LVS: manual GUI checks; check completion is not recorded.')
        print('  GUI aliases: verdi -> sim; postverdi -> postsim; postverdi_sdf -> postsim_sdf; pnr -> chipfinish.')
        print('  ■ means recorded success with complete upstream/results; inputs are not compared.')
        for note in notes:
            print('  ' + note)
        print()
        return states

    def summary(self):
        states = self.progress()
        if self.ws is None:
            print('Design namespace is not configured. Run make check for missing inputs.'); return
        stage=read_json(self.ws.base/'latest.json').get('stage')
        if not stage: print('No recorded run for this design/technology.'); return
        record=self.record(stage)
        print('Latest attempted stage: '+stage+'; '+states.get(stage, 'UNKNOWN'))
        if record.get('error'): print(record['error'])
        for result in record.get('summaries',[]): reports.display(result)

    def invalidate_final_consumers(self, reason):
        names = ['merge', 'hcell', 'lvs-input', 'rc', 'pt', 'postsim_sdf', 'drc', 'lvs']
        if self.cfg['GATE_STAGE'] == 'chipfinish':
            names.append('postsim')
        revision = uuid.uuid4().hex
        for name in names:
            directory = self.ws.require_record_directory(name)
            record = self.record(name)
            if record:
                history = directory/'record-history'
                history.mkdir(exist_ok=True)
                write_json(history/(revision+'.json'), record)
                record.update(status='INVALIDATED', reason=reason)
                write_json(directory/'result.json', record)
        self.memo.clear()

    def prepare_eco_gui(self):
        Versions(self).start()

    def accept_eco(self):
        with self.require_workspace().lock():
            Versions(self).accept()

    def use_original(self):
        with self.require_workspace().lock():
            Versions(self).rollback(original=True)

    def open_gui(self, kind, stage=None):
        if not self.env.get('DISPLAY') and sys.platform!='win32': raise ValueError('DISPLAY is missing; GUI needs an X11 desktop/forwarding')
        with self.require_workspace().lock():
            if kind=='eco':
                self.prepare_eco_gui()
            elif kind=='pnr':
                stage=stage or self.env.get('STAGE') or (self.final_stage() if self.final_stage() == 'eco' or self.valid('chipfinish') else next((s for s in reversed(PNR) if self.valid(s)), ''))
                if stage not in PNR + ('eco',):
                    raise ValueError('No PNR checkpoint selected; use make open STAGE=chipfinish')
                directory=self.final_directory() if stage == 'eco' else self.ws.stage(stage)
                if not self.valid(stage):
                    raise ValueError('PNR checkpoint or required upstream results are incomplete: ' + stage)
                checkpoint = self.checkpoint(stage)
                if stage == 'eco':
                    directory = self.ws.stage('eco')/'viewer'
                    directory.mkdir(parents=True, exist_ok=True)
                    self.config_tcl(directory, 'chipfinish')
                put(directory/'open.tcl','source config.tcl\nsource '+tcl(checkpoint)+'\nwin on\n')
                self.command('INNOVUS',['-log', 'gui', '-overwrite', '-files','open.tcl'],directory,'gui.log', interactive=True)
            elif kind=='cov':
                if not self.valid('cov'):
                    raise ValueError('Coverage result is incomplete; run make cov')
                directory=self.ws.stage('cov')
                database=directory/'coverage.vdb'
                if not database.is_dir() or not any(database.rglob('*.xml')):
                    raise ValueError('Missing/empty coverage database: '+str(database))
                self.command('VERDI_COV',['-cov','-covdir',str(database)],directory,'coverage_gui.log')
            elif kind in ('verdi','postverdi','postverdi_sdf'):
                stage={'verdi': 'sim', 'postverdi': 'postsim', 'postverdi_sdf': 'postsim_sdf'}[kind]
                if not self.valid(stage): raise ValueError('Simulation results are incomplete')
                directory=self.ws.stage(stage); wave=directory/'wave.fsdb'
                sources=self.sources('RTL_LIST') if stage=='sim' else [(self.final_directory() if stage=='postsim_sdf' or self.cfg['GATE_STAGE']=='chipfinish' else self.ws.stage('dc'))/(self.cfg['DESIGN_NAME']+'.v')]+self.libs('SIM_LIBS')
                args=['-sv','-top',self.cfg['TB_TOP']]+list(map(str,sources+self.sources('TB_LIST')))
                if stage=='sim':
                    args += ['+define+'+define for define in self.words('RTL_DEFINES')]
                if wave.is_file(): args += ['-ssf',str(wave)]
                elif (directory/'wave.vcd').is_file(): args += ['-ssf',str(directory/'wave.vcd')]
                self.command('VERDI',args,directory,'gui.log')
            else:
                issues=self.preflight(kind)
                if issues: raise ValueError('\n'.join(issues))
                directory=self.ws.stage(kind); directory.mkdir(parents=True,exist_ok=True)
                # Calibre owns auxiliary links such as .cgidrcdb. Protect only
                # framework copy/write targets, without traversing those databases.
                for name in ('rules.cal', 'sample_design_inc.cal', 'lvs.runset', 'gui.log'):
                    no_links(directory/name)
                source=self.tech/kind
                copy_overlay(source, directory)
                gds=self.ws.stage('merge' if kind=='drc' else 'lvs-input')/(self.cfg['DESIGN_NAME']+'.gds')
                template=directory/('rules.cal.in' if kind=='drc' else 'design.cal.in')
                text=template.read_text()
                for key,value in {'@LAYOUT@':str(gds),'@TOP@':self.cfg['TOP_MODULE'],'@SOURCE@':str(self.ws.stage('lvs-input')/(self.cfg['DESIGN_NAME']+'.spi'))}.items(): text=text.replace(key,value)
                put(directory/('rules.cal' if kind=='drc' else 'sample_design_inc.cal'),text)
                if kind == 'lvs':
                    hcell = self.ws.stage('hcell')/'hcell_list'
                    if not self.valid('hcell'):
                        raise ValueError('Missing completed hcell list; run make hcell')
                    fields = {'lvsRulesFile': str(directory/'rules.cal'), 'lvsRunDir': str(directory),
                              'lvsLayoutPaths': str(gds), 'lvsLayoutPrimary': self.cfg['TOP_MODULE'],
                              'lvsLayoutSystem': 'GDSII', 'lvsLayoutGetFromViewer': '0',
                              'lvsSourcePath': str(self.ws.stage('lvs-input')/(self.cfg['DESIGN_NAME']+'.spi')),
                              'lvsSourcePrimary': self.cfg['TOP_MODULE'], 'lvsSourceSystem': 'SPICE',
                              'lvsSourceGetFromViewer': '0', 'lvsUseHCells': '1',
                              'lvsHCellsFile': str(hcell), 'lvsGenHCells': '0'}
                    put(directory/'lvs.runset', ''.join('*{}: {}\n'.format(key, value) for key, value in fields.items()))
                    print('Load this runset in Calibre Interactive LVS: ' + str(directory/'lvs.runset'))
                print('Prepared rules: '+str(directory/'rules.cal')+'; run checks manually in GUI.')
                try:
                    self.command('CALIBREDRV',['-m',str(gds)],directory,'gui.log')
                finally:
                    report_store.collect(self, kind)

def put_bytes(path, data):
    Path(path).write_bytes(data)

def main():
    action=sys.argv[1] if len(sys.argv)>1 else 'help'
    if action=='help':
        print('make sim/verdi/cov | dc/formal | postsim/postverdi/postsim_sdf/postverdi_sdf\nmake init/floorplan/powerplan/placement/cts/route/chipfinish/pnr\nmake route-resume | eco | eco-accept | eco-use-original | eco-rollback [REV=编号] | eco-history | hcell\nmake drc/lvs (prepare + GUI only) | pt | open [STAGE=route]\nmake check [STAGE=innovus] | summary | reports | output | clean-preview | clean [STAGE=pt] | test\nGUI=0 batch; FORCE=1 rerun visited stages; FORCE_STAGE=route reruns only route. 结果在 work/，报告在 reports/，交付在 output/。')
        return 0
    flow=Flow()
    if action=='check': return flow.check()
    if action=='summary': flow.summary()
    elif action in ('clean','clean-preview'):
        names=[flow.env['STAGE']] if flow.env.get('STAGE') else list(STAGES)
        with flow.require_workspace().lock():
            for name in names: flow.ws.remove(name,True)
            for name in names: print(flow.ws.remove(name,action=='clean-preview'))
            if not flow.env.get('STAGE'):
                extras = [flow.ws.base/'versions', flow.root/'reports'/flow.cfg['DESIGN_NAME']/flow.cfg['TECH']]
                for path in extras:
                    no_links(path)
                    print('清理完整版本历史/报告：'+str(path))
                    if action == 'clean' and path.exists():
                        shutil.rmtree(str(path))
                for name in ('active-final.json', 'latest.json'):
                    path = no_links(flow.ws.base/name)
                    if action == 'clean' and path.exists(): path.unlink()
    elif action=='output':
        from deliver import package
        package(flow)
    elif action=='reports': report_store.refresh(flow)
    elif action=='eco-history': Versions(flow).history()
    elif action=='eco-rollback':
        with flow.require_workspace().lock():
            Versions(flow).rollback(flow.env.get('REV') or None)
    elif action=='route-resume': flow.resume_route()
    elif action=='eco-accept': flow.accept_eco()
    elif action=='eco-use-original': flow.use_original()
    elif action=='run': flow.run(sys.argv[2])
    elif action=='open': flow.open_gui(sys.argv[2])
    else: raise ValueError('Unknown action: '+action)
    return 0

if __name__=='__main__':
    try: sys.exit(main())
    except (ValueError,RuntimeError,OSError) as exc:
        print('FLOW_ERROR: '+str(exc),file=sys.stderr); sys.exit(1)
