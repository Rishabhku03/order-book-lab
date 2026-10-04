import argparse
import functools
import http.server
import os
import shutil
import subprocess
import sys
import webbrowser
from common import ROOT, environment, run

def build(preset):
    env=environment(); cmake=shutil.which('cmake',path=env.get('PATH',env.get('Path','')))
    if not cmake: raise RuntimeError('Install requirements-dev.txt and the C++ toolchain; run doctor')
    options=[]
    if os.name=='nt':
        compiler=shutil.which('clang++' if preset in ('sanitize','coverage','fuzz') else 'cl',path=env['PATH'])
        if not compiler: raise RuntimeError('Required C++ compiler is missing; run doctor')
        if preset=='debug': options.append('-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreadedDebug')
    if os.name=='nt' and preset in ('sanitize','coverage','fuzz'):
        if preset in ('sanitize','fuzz'):
            # LLVM's Windows sanitizer/fuzzer runtimes use the release CRT.
            options.append('-DCMAKE_BUILD_TYPE=RelWithDebInfo')
        if preset in ('sanitize','fuzz'): options.append('-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded')
        for key,tool in [('CMAKE_AR','llvm-ar'),('CMAKE_RANLIB','llvm-ranlib')]:
            found=shutil.which(tool,path=env['PATH'])
            if found: options.append(f'-D{key}={found}')
    cache=ROOT/'build'/preset/'CMakeCache.txt'
    fresh=[]
    if os.name=='nt' and cache.exists():
        configured=next((line.split('=',1)[1] for line in cache.read_text().splitlines() if line.startswith('CMAKE_CXX_COMPILER:')),None)
        if configured:
            if os.path.normcase(os.path.normpath(configured))!=os.path.normcase(os.path.normpath(compiler)): fresh=['--fresh']
            else: compiler=configured
    if os.name=='nt': options.append(f'-DCMAKE_CXX_COMPILER={compiler}')
    run([cmake,*fresh,'--preset',preset,*options],env=env)
    targets=['--target','fuzz_parser','fuzz_state'] if preset=='fuzz' else []
    run([cmake,'--build','--preset',preset,'--parallel',str(min(8,os.cpu_count() or 2)),*targets],env=env)

def test(preset):
    env=environment(); ctest=shutil.which('ctest',path=env.get('PATH',env.get('Path','')))
    run([ctest,'--preset',preset],env=env)
    run([sys.executable,'-m','unittest','discover','-s','tests','-p','test_*.py'],env={**env,'LOB_PRESET':preset})

def main():
    p=argparse.ArgumentParser(description='Build, verify, measure and explore the synthetic C++ order book.')
    p.add_argument('command',choices=['doctor','build','test','verify','benchmark','report','demo','serve','browser-test'])
    p.add_argument('--preset',default='release',choices=['release','debug','sanitize','coverage','fuzz'])
    p.add_argument('--suite',choices=['smoke','full'],default='smoke'); p.add_argument('--run')
    p.add_argument('--checks',choices=['core','all'],default='all');p.add_argument('--fuzz-seconds',type=int,default=900)
    p.add_argument('--cpu',type=int); p.add_argument('--port',type=int,default=8765); p.add_argument('--no-open',action='store_true')
    a=p.parse_args()
    if a.command=='doctor':
        env=environment()
        missing=[]
        for name in ('cmake','ninja','cl' if os.name=='nt' else 'c++'):
            found=shutil.which(name,path=env.get('PATH',''));print(f'{name}: {found or "MISSING"}')
            if not found:missing.append(name)
        print('Python:',sys.version.split()[0])
        if os.name=='nt':
            print('Windows setup: install Visual Studio Build Tools with Desktop development with C++, then python -m pip install -r requirements-dev.txt')
        else:
            print('Linux setup: install GCC, Clang and LLVM tools, then python -m pip install -r requirements-dev.txt')
        for name in ('clang++','llvm-profdata','llvm-cov'):
            print(f'Additional verification / {name}: {shutil.which(name,path=env.get("PATH","")) or "install Clang and LLVM tools"}')
        print('Browser setup: python -m playwright install chromium')
        if missing:raise RuntimeError('Missing dependencies: '+', '.join(missing))
    elif a.command=='build': build(a.preset)
    elif a.command=='test': test(a.preset)
    elif a.command=='verify':
        test(a.preset)
        from verify import verify
        verify(100 if a.suite=='full' else 3,2000,a.preset)
        if a.suite=='full' and a.checks=='all':
            from release_verify import complete
            complete(a.fuzz_seconds)
    elif a.command=='benchmark':
        from benchmarks import benchmark
        from report import report
        from schemas import benchmark as validate_results
        directory=benchmark(a.suite,a.run,a.cpu)
        validate_results(directory)
        report(directory)
    elif a.command=='report':
        if not a.run: p.error('report needs --run')
        from report import report
        report(a.run)
    elif a.command=='browser-test': run([sys.executable,'tests/browser.py'])
    else:
        if a.command=='demo':
            from demo import prepare
            prepare(a.preset)
        handler=functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(ROOT/'web'))
        server=http.server.ThreadingHTTPServer(('127.0.0.1',a.port),handler)
        url=f'http://127.0.0.1:{server.server_port}/'; print(url,flush=True)
        if not a.no_open: webbrowser.open(url)
        try: server.serve_forever()
        except KeyboardInterrupt: pass
        finally: server.server_close()

if __name__=='__main__':
    try: main()
    except (RuntimeError,ValueError,OSError,subprocess.CalledProcessError) as e:
        if getattr(e,'winerror',None)==4551:
            print('Windows application control blocked the compiled program. Use a trusted signed toolchain or ask your administrator about the blocked binary; keep security protections enabled.',file=sys.stderr)
        else: print(str(e),file=sys.stderr)
        raise SystemExit(2)
