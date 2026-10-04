import argparse
import json
import math
import subprocess
import tempfile
from pathlib import Path
from common import ROOT, VARIANTS, executable, dump, environment
from generate import generate
from reference import Reference, rows

def compare(expected, actual, where=''):
    if isinstance(expected, dict):
        for k,v in expected.items():
            if k not in actual: raise AssertionError(f'{where}.{k} missing')
            compare(v,actual[k],where+'.'+k)
    elif isinstance(expected,list):
        if len(expected)!=len(actual): raise AssertionError(f'{where}: length mismatch')
        for i,(a,b) in enumerate(zip(expected,actual)): compare(a,b,f'{where}[{i}]')
    elif isinstance(expected,float):
        if actual is None or not math.isclose(expected,actual,rel_tol=1e-12,abs_tol=1e-10):
            raise AssertionError(f'{where}: {expected!r} != {actual!r}')
    elif expected!=actual: raise AssertionError(f'{where}: {expected!r} != {actual!r}')

def verify(seeds=100,events=2000,preset='release'):
    total=0
    with tempfile.TemporaryDirectory(prefix='lob-verify-') as tmp:
        for seed in range(seeds):
            path=Path(tmp)/f'{seed}.csv'; generate(path,seed=seed,events=events,capacity=200,levels=20)
            source=list(rows(path)); expected=[]; reference=Reference()
            for e in source: reference.apply(e); expected.append(reference.snapshot())
            for variant in VARIANTS:
                cmd=[str(executable(preset)),'audit','--input',str(path),'--manifest',str(path.with_suffix('.manifest.json')),'--variant',variant]
                proc=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',env=environment() if preset in ('sanitize','coverage','fuzz') else None)
                seen=0
                try:
                    for line in proc.stdout:
                        actual=json.loads(line)
                        if 'summary' in actual: continue
                        compare(expected[seen],actual,f'seed {seed} {variant} event {seen}')
                        seen+=1
                    err=proc.stderr.read(); code=proc.wait()
                    if code or seen!=len(source): raise AssertionError(f'{variant}: exit={code}, seen={seen}, {err}')
                except BaseException:
                    proc.kill(); proc.wait(); raise
                total+=seen
            if seed%10==0: print(f'Differential check: seed {seed+1}/{seeds}, {total:,} comparisons',flush=True)
    from benchmarks import source_hash
    from generate import sha
    result={'source_sha256':source_hash(),'binary_sha256':sha(executable(preset)),'preset':preset,'complete':True,'seeds':seeds,'measured_events_per_seed':events,'setup_events_per_seed':100,
            'variants':VARIANTS,'comparisons_including_setup':total,
            'measured_comparisons_per_variant':seeds*events,'tolerance':{'relative':1e-12,'absolute':1e-10}}
    dump(ROOT/'results'/('verification.json' if preset=='release' and seeds==100 and events==2000 else f'verification-{preset}-{seeds}-{events}.json'),result)
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--seeds',type=int,default=100); p.add_argument('--events',type=int,default=2000)
    p.add_argument('--preset',default='release'); a=p.parse_args(); print(verify(a.seeds,a.events,a.preset))
