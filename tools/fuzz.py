"""Run both fuzz targets in isolated disposable corpora; preserve crash artifacts."""
import argparse
import json
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from common import ROOT, executable, environment, dump, fuzz_fingerprint

p=argparse.ArgumentParser();p.add_argument('--seconds',type=int,default=900);p.add_argument('--out');a=p.parse_args()
if a.seconds<1: p.error('--seconds must be positive')
out=Path(a.out) if a.out else ROOT/'results'/('fuzz' if a.seconds>=900 else 'fuzz-smoke');out.mkdir(parents=True,exist_ok=True)
results=[]
fingerprint=fuzz_fingerprint()
with tempfile.TemporaryDirectory(prefix='lob-fuzz-') as tmp:
    children=[]
    for name in ('parser','state'):
        corpus=Path(tmp)/name;shutil.copytree(ROOT/'fuzz/corpus'/name,corpus)
        log=(out/(name+'.log')).open('w')
        cmd=[str(executable('fuzz','fuzz_'+name)),str(corpus),f'-max_total_time={a.seconds}',
             '-max_len='+('8192' if name=='parser' else '6000'),'-seed=42','-artifact_prefix='+str(out.resolve())+'/']
        start=time.monotonic();process=subprocess.Popen(cmd,env=environment(),stdout=log,stderr=subprocess.STDOUT)
        children.append((name,process,log,start))
    for name,process,log,start in children:
        code=process.wait();log.close()
        executions=re.findall(r'Done ([0-9]+) runs', (out/(name+'.log')).read_text(errors='replace'))
        results.append({'target':name,'exit_code':code,'elapsed_seconds':time.monotonic()-start,'budget_seconds':a.seconds,'executions':int(executions[-1]) if executions else None})
        shutil.copytree(Path(tmp)/name,out/'corpus'/name,dirs_exist_ok=True)
        print(name,code,flush=True)
from benchmarks import source_hash
from generate import sha
dump(out/'summary.json',{'complete':all(r['exit_code']==0 for r in results) and fingerprint==fuzz_fingerprint(),'runs':results,'source_sha256':source_hash(),'fingerprint':fingerprint,
                         'binary_sha256':{name:sha(executable('fuzz','fuzz_'+name)) for name in ('parser','state')}})
if any(r['exit_code']!=0 for r in results) or fingerprint!=fuzz_fingerprint():raise SystemExit(1)
