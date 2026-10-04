"""Aggregate the local release checks; publishing is a separate step."""
import json
import shutil
import sys
import time
from common import ROOT, dump, run, fuzz_fingerprint

def complete(fuzz_seconds=900,reuse_fuzz=False):
    from run import build, test
    from verify import verify
    from demo import prepare
    from schemas import exports
    started=time.monotonic();checks=['release core/integration and 100-seed differential tests']
    for preset in ('debug','sanitize'):
        print('Release verification:',preset,flush=True);build(preset);test(preset)
        if preset=='sanitize':verify(3,2000,preset)
        checks.append(preset+' build and tests')
    build('coverage');run([sys.executable,'tools/coverage.py']);checks.append('coverage thresholds')
    build('fuzz')
    saved=ROOT/'results/fuzz/summary.json'
    previous=json.loads(saved.read_text()) if saved.exists() else {}
    reusable=(reuse_fuzz and previous.get('complete') is True and previous.get('fingerprint')==fuzz_fingerprint()
              and all(r['budget_seconds']>=fuzz_seconds and r['exit_code']==0 for r in previous.get('runs',[]))
              and len(previous.get('runs',[]))==2)
    if reusable:print('Reusing completed fuzz evidence for identical targets and binaries',flush=True)
    else:run([sys.executable,'tools/fuzz.py','--seconds',str(fuzz_seconds)])
    checks.append(f'{fuzz_seconds}-second parser/state fuzz sessions')
    prepare();exports();checks.append('regenerated demo and export schemas')
    run([sys.executable,'tests/browser.py']);run([sys.executable,'tests/visual_audit.py']);checks.append('desktop/mobile browser and visual checks')
    run([sys.executable,'tools/reproduce.py']);checks.append('fresh source reproduction')
    run([sys.executable,'tools/format.py','--check']);checks.append('formatting and compiler warnings')
    evidence=ROOT/'docs/evidence';evidence.mkdir(exist_ok=True)
    for source,name in [('results/verification.json','verification.json'),('results/coverage/summary.json','coverage.json'),('results/fuzz/summary.json','fuzz.json'),('results/reproduction/summary.json','reproduction.json'),('results/visual-audit/summary.json','visual-audit.json')]:
        path=ROOT/source
        if path.exists():shutil.copyfile(path,evidence/name)
    result={'complete':True,'local_checks':checks,'fuzz_seconds_per_target':fuzz_seconds,'elapsed_seconds':time.monotonic()-started,'elapsed_scope':'this invocation','reused_fuzz_evidence':reusable,
            'external_checks_pending':['Linux GitHub Actions execution','GitHub Pages deployment','Git release commit'],
            'scope':'Local verification; full performance matrix is a separate benchmark command.'}
    dump(ROOT/'results/release-verification.json',result);dump(evidence/'release-verification.json',result)
    from evidence import publish
    publish()
    print('Local release verification passed',flush=True)
