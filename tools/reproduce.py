"""Build and test a fresh source copy, then reproduce the bundled demo bytes."""
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from common import ROOT, dump

started=time.monotonic()
out=ROOT/'results/reproduction';out.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory(prefix='lob-clean-source-') as temp:
    checkout=Path(temp)
    for folder in ('include','src','tests','tools','bench','fuzz','cmake','web','.github'):
        shutil.copytree(ROOT/folder,checkout/folder,ignore=shutil.ignore_patterns('__pycache__','evidence'))
    for name in ('CMakeLists.txt','CMakePresets.json','requirements-dev.txt','.clang-format'):
        shutil.copyfile(ROOT/name,checkout/name)
    commands=[['tools/run.py','build'],['tools/run.py','test'],
              ['-c',"import sys;sys.path.insert(0,'tools');from demo import prepare;prepare()"]]
    with (out/'build-and-test.log').open('w') as log:
        for command in commands:
            subprocess.run([sys.executable,*command],cwd=checkout,stdout=log,stderr=subprocess.STDOUT,check=True)
    compared=[]
    for name in ('balanced','cancellation','lifecycle'):
        for extension in ('.csv','.manifest.json','.json'):
            source=ROOT/'web/data'/(name+extension);rebuilt=checkout/'web/data'/(name+extension)
            if extension=='.csv':
                equal=source.read_bytes()==rebuilt.read_bytes()
            else:
                expected=json.loads(source.read_text());actual=json.loads(rebuilt.read_text())
                # A source copy has no Git metadata; the book output must still match.
                if extension=='.json':expected.pop('engine_commit',None);actual.pop('engine_commit',None)
                equal=expected==actual
            if not equal:raise AssertionError('Reproduction differs: '+name+extension)
            compared.append(name+extension)
dump(out/'summary.json',{'complete':True,'method':'fresh source copy without build cache or Git metadata',
                        'checks':['native release build','C++ tests','Python integration tests','demo regeneration'],
                        'identical_files_or_json_values':compared,'elapsed_seconds':time.monotonic()-started})
print('Fresh source build, tests and nine demo artifacts reproduced successfully')
