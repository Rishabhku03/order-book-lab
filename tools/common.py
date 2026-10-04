import json
import os
import platform
import shutil
import subprocess
import sys
import hashlib
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VARIANTS = ['tree','hash','hash_reserved']

@lru_cache(maxsize=1)
def environment():
    env=os.environ.copy()
    # pip installations need not have their scripts directory on PATH.
    paths=[]
    for package in ('cmake','ninja'):
        try:
            module=__import__(package)
            paths.append(str(Path(module.__file__).parent/'data'/'bin'))
        except ImportError: pass
    if os.name=='nt' and not shutil.which('cl',path=env.get('PATH','')):
        vswhere=Path(os.environ.get('ProgramFiles(x86)','C:/Program Files (x86)'))/'Microsoft Visual Studio/Installer/vswhere.exe'
        if vswhere.exists():
            install=subprocess.check_output([str(vswhere),'-latest','-products','*','-requires','Microsoft.VisualStudio.Component.VC.Tools.x86.x64','-property','installationPath'],text=True).strip()
            if install:
                batch=Path(install)/'Common7/Tools/VsDevCmd.bat'
                # A fixed command invokes the vendor's environment initializer; no user input is interpolated.
                output=subprocess.check_output(f'cmd.exe /d /s /c ""{batch}" -arch=x64 >nul && set"',text=True)
                for line in output.splitlines():
                    if '=' in line:
                        k,v=line.split('=',1); env[k]=v
    if os.name=='nt': env={k.upper():v for k,v in env.items()}
    if os.name=='nt' and Path('C:/Program Files/LLVM/bin').exists():
        paths.append('C:/Program Files/LLVM/bin')
        installed_runtimes=Path('C:/Program Files/LLVM/lib/clang')
        if installed_runtimes.exists(): paths.extend(str(p/'lib/windows') for p in installed_runtimes.iterdir() if p.is_dir())
    if os.name=='nt':
        portable=Path(os.environ['LOCALAPPDATA'])/'OrderBookLab/llvm/bin'
        if portable.exists(): paths.append(str(portable))
        runtimes=portable.parent/'lib/clang'
        if runtimes.exists(): paths.extend(str(p/'lib/windows') for p in runtimes.iterdir() if p.is_dir())
    path_key=next((k for k in env if k.lower()=='path'),'PATH')
    env[path_key]=os.pathsep.join(paths+[env.get(path_key,'')])
    return env

def run(command, **kwargs):
    return subprocess.run([str(x) for x in command],cwd=ROOT,check=True,**kwargs)

def executable(preset='release',name='lob'):
    path=ROOT/'build'/preset/(name+('.exe' if os.name=='nt' else ''))
    if not path.exists(): raise RuntimeError(f'Missing {path.name}; run python tools/run.py build --preset {preset}')
    return path

def fuzz_fingerprint():
    source=hashlib.sha256()
    for folder in ('include','fuzz'):
        for path in sorted((ROOT/folder).rglob('*')):
            if path.is_file() and path.suffix in ('.cpp','.hpp'):
                source.update(path.relative_to(ROOT).as_posix().encode());source.update(path.read_bytes())
    binaries={name:hashlib.sha256(executable('fuzz','fuzz_'+name).read_bytes()).hexdigest() for name in ('parser','state')}
    return {'target_source_sha256':source.hexdigest(),'binary_sha256':binaries}

def invoke(command, path, variant='hash_reserved', preset='release', extra=()):
    args=[executable(preset),command,'--input',path,'--manifest',Path(path).with_suffix('.manifest.json'),'--variant',variant,*extra]
    return json.loads(subprocess.check_output(list(map(str,args)),cwd=ROOT,text=True,
                    env=environment() if preset in ('sanitize','coverage','fuzz') else None))

def dump(path,data):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,indent=2,allow_nan=False)+'\n',encoding='utf-8')

def commit():
    r=subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,text=True,capture_output=True)
    return r.stdout.strip() if r.returncode==0 else 'uncommitted'

def metadata():
    info={'os':platform.platform(),'machine':platform.machine(),'python':platform.python_version(),'logical_cpus':os.cpu_count(),
          'engine_commit':commit(),'working_tree_dirty':bool(subprocess.run(['git','status','--porcelain'],cwd=ROOT,capture_output=True,text=True).stdout)}
    if os.name=='nt':
        info['cpu']=os.environ.get('PROCESSOR_IDENTIFIER','unknown')
        ps='Get-CimInstance Win32_Processor | Select-Object -ExpandProperty Name'
        info['cpu_model']=subprocess.check_output(['powershell','-NoProfile','-Command',ps],text=True).strip()
        info['power_plan']=subprocess.check_output(['powercfg','/getactivescheme'],text=True).strip()
        details=subprocess.check_output(['powershell','-NoProfile','-Command',
            '$b=Get-CimInstance Win32_Battery; $c=Get-CimInstance Win32_ComputerSystem; @{ram_bytes=$c.TotalPhysicalMemory; battery_status=$b.BatteryStatus} | ConvertTo-Json -Compress'],text=True)
        info.update(json.loads(details))
    else:
        info['cpu_model']=next((line.split(':',1)[1].strip() for line in Path('/proc/cpuinfo').read_text().splitlines() if line.startswith('model name')),'unknown')
    return info
