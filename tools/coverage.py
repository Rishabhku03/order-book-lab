"""Generate a coverage report and enforce targets on core/parser headers."""
import json
import os
import shutil
import subprocess
from pathlib import Path
from common import ROOT, environment, executable, dump

out=ROOT/'results'/'coverage';out.mkdir(parents=True,exist_ok=True)
env=environment();env['LLVM_PROFILE_FILE']=str(out/'%p.profraw')
previous=set(out.glob('*.profraw'))
binary=executable('coverage','lob_tests')
subprocess.run([str(binary)],env=env,check=True)
def tool(name):
    p=shutil.which(name,path=env.get('PATH',''))
    if p:return p
    # Ubuntu packages may expose only versioned names.
    for version in range(30,13,-1):
        p=shutil.which(f'{name}-{version}',path=env.get('PATH',''))
        if p:return p
    raise RuntimeError(f'Missing {name}')
prof=out/'merged.profdata'
profiles=set(out.glob('*.profraw'))-previous
if not profiles: raise RuntimeError('No new coverage profile was written')
subprocess.run([tool('llvm-profdata'),'merge','-sparse',*[str(p) for p in profiles],'-o',str(prof)],check=True,env=env)
cmd=[tool('llvm-cov'),'export',str(binary),'-instr-profile='+str(prof)]
data=json.loads(subprocess.check_output(cmd,env=env,text=True))
files=[f for unit in data['data'] for f in unit['files'] if f['filename'].replace('\\','/').endswith(('/lob/book.hpp','/lob/parser.hpp','/lob/types.hpp'))]
lines=sum(f['summary']['lines']['count'] for f in files);line_hits=sum(f['summary']['lines']['covered'] for f in files)
branches=sum(f['summary']['branches']['count'] for f in files);branch_hits=sum(f['summary']['branches']['covered'] for f in files)
summary={'lines':lines,'covered_lines':line_hits,'line_percent':100*line_hits/lines,
         'branches':branches,'covered_branches':branch_hits,'branch_percent':100*branch_hits/branches,
         'scope':['book.hpp (including analytics)','parser.hpp','types.hpp'],'files':[{'file':Path(f['filename']).name,'summary':f['summary']} for f in files]}
dump(out/'summary.json',summary)
subprocess.run([tool('llvm-cov'),'show',str(binary),'-instr-profile='+str(prof),'-format=html','-output-dir='+str(out/'html'),str(ROOT/'include/lob/book.hpp'),str(ROOT/'include/lob/parser.hpp')],check=True,env=env,stdout=subprocess.DEVNULL)
print(json.dumps(summary,indent=2))
if summary['line_percent']<90 or summary['branch_percent']<80:raise SystemExit('Coverage target not met')
