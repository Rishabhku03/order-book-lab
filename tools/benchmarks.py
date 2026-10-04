"""One process per measurement; no throughput thresholds on shared CI hosts."""
import argparse
import datetime
import hashlib
import gzip
import json
import os
import random
import re
import subprocess
import tempfile
import datetime as dt
import contextlib
from pathlib import Path
from common import ROOT, VARIANTS, executable, dump, metadata, invoke
from generate import generate, SIZES, PROFILES, sha

def source_hash():
    h=hashlib.sha256()
    for name in ('CMakeLists.txt','CMakePresets.json','requirements-dev.txt'):
        h.update(name.encode());h.update((ROOT/name).read_bytes())
    for folder in ('include','src','tools','bench','cmake'):
        for p in sorted((ROOT/folder).rglob('*')):
            if p.is_file() and p.suffix in ('.py','.cpp','.hpp','.cmake'):
                h.update(p.relative_to(ROOT).as_posix().encode()); h.update(p.read_bytes())
    return h.hexdigest()

def default_cpu():
    if hasattr(os,'sched_getaffinity'): return min(os.sched_getaffinity(0))
    return 0

@contextlib.contextmanager
def pinned(cpu):
    """Children inherit the launcher's temporary affinity; restore it afterward."""
    if os.name=='nt':
        import ctypes
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.GetCurrentProcess.restype=ctypes.c_void_p
        kernel.GetProcessAffinityMask.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_size_t),ctypes.POINTER(ctypes.c_size_t)]
        kernel.SetProcessAffinityMask.argtypes=[ctypes.c_void_p,ctypes.c_size_t]
        handle=kernel.GetCurrentProcess();previous=ctypes.c_size_t();system=ctypes.c_size_t()
        if not kernel.GetProcessAffinityMask(handle,ctypes.byref(previous),ctypes.byref(system)) or not kernel.SetProcessAffinityMask(handle,1<<cpu):
            raise OSError('Cannot pin Google Benchmark process')
        try: yield
        finally:
            if not kernel.SetProcessAffinityMask(handle,previous.value): raise OSError('Cannot restore affinity')
    else:
        previous=os.sched_getaffinity(0);os.sched_setaffinity(0,{cpu})
        try: yield
        finally: os.sched_setaffinity(0,previous)

def benchmark(suite='smoke',out=None,cpu=None):
    cpu=default_cpu() if cpu is None else cpu
    out=Path(out) if out else ROOT/'results'/('benchmark-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
    out.mkdir(parents=True,exist_ok=True)
    env=metadata(); env.update(source_sha256=source_hash(),cpu_affinity=cpu,suite=suite,
          flags='CMake Release: /O2 /Ob2 /DNDEBUG on MSVC; -O3 -DNDEBUG on GCC/Clang',
          timer='std::chrono::steady_clock',repetitions=7 if suite=='full' else 2,
          order_seed=73,cache='uncontrolled; input checksum read before timing',
          data_location='OS temporary directory outside repository',units='prices in ticks; time in seconds/ns; memory in bytes',
          timing_claim='instrumented local update durations, not network or queue latency')
    env['source_folder']='OneDrive path' if any('onedrive' in part.lower() for part in ROOT.parts) else 'local path'
    env['results_folder']='OneDrive path' if any('onedrive' in part.lower() for part in out.resolve().parts) else 'local nonsynchronized path'
    binary=executable(); env['binary_sha256']=sha(binary)
    cache=(ROOT/'build/release/CMakeCache.txt').read_text()
    env['configured_flags']={key:next((line.split('=',1)[1] for line in cache.splitlines() if line.startswith(key+':')),None) for key in ('CMAKE_CXX_FLAGS','CMAKE_CXX_FLAGS_RELEASE','LOB_SANITIZE','LOB_COVERAGE','LOB_WARNINGS_AS_ERRORS')}
    if env['configured_flags']['LOB_SANITIZE']=='ON' or env['configured_flags']['LOB_COVERAGE']=='ON':raise RuntimeError('Instrumented builds cannot supply performance results')
    compiler_files=list((ROOT/'build/release/CMakeFiles').glob('*/CMakeCXXCompiler.cmake'))
    if compiler_files:
        compiler=compiler_files[-1].read_text()
        for field in ('CMAKE_CXX_COMPILER_ID','CMAKE_CXX_COMPILER_VERSION'):
            match=re.search(r'set\('+field+r' "([^"]+)"\)',compiler)
            if match: env[field.lower()]=match.group(1)
    env['dependencies']={'Catch2':'3.8.1','Google Benchmark':'1.9.4','nlohmann/json':'3.12.0','PicoSHA2':'161cb3fc4170fa7a3eca9e582cebd27cc4d1fe29'}
    env['started_at_utc']=dt.datetime.now(dt.timezone.utc).isoformat()
    manifest_path=out/'environment.json'
    if manifest_path.exists():
        prior=json.loads(manifest_path.read_text())
        if any(prior.get(k)!=env.get(k) for k in ('source_sha256','binary_sha256','suite','cpu_affinity','os','cpu_model','cmake_cxx_compiler_id','cmake_cxx_compiler_version')):
            raise RuntimeError('Resume requires identical source, binary, suite and CPU')
        env=prior
    else: dump(manifest_path,env)
    repeats=env['repetitions']; rng=random.Random(73)
    configs=[(profile,size,seed) for profile in PROFILES for size in SIZES for seed in (17,42,2027)] if suite=='full' else [('balanced','small',42)]
    with tempfile.TemporaryDirectory(prefix='lob-benchmark-') as scratch:
        for index,(profile,size,seed) in enumerate(configs):
            label=f'{profile}-{size}-{seed}'; path=Path(scratch)/(label+'.csv')
            m=generate(path,profile,seed,1000000 if suite=='full' else 10000,*SIZES[size])
            dump(out/'workloads'/(label+'.json'),m)
            print(f'Benchmark workload {index+1}/{len(configs)}: {label}',flush=True)
            # Checkpoint comparisons are separate from all timed passes.
            checkpoints=[invoke('validate',path,v,extra=['--checkpoints']) for v in VARIANTS]
            for c in checkpoints[1:]:
                if (c['checkpoints'],c['final_state_sha256'])!=(checkpoints[0]['checkpoints'],checkpoints[0]['final_state_sha256']):
                    raise AssertionError('variant checkpoint mismatch')
            dump(out/'validation'/(label+'.json'),checkpoints[0])
            modes=['book','analytics','end_to_end','memory']
            if (size=='medium' and seed==42) or suite=='smoke': modes.append('latency')
            for mode in modes+['parse']:
                variants=['hash_reserved'] if mode=='parse' else VARIANTS
                for repetition in range(-1,repeats):
                    order=variants.copy(); rng.shuffle(order)
                    for variant in order:
                        target=out/'raw'/f'{label}-{mode}-{variant}-{repetition}.json'
                        if repetition>=0 and target.exists(): continue
                        extra=['--mode',mode,'--cpu',str(cpu)]
                        sample_path=Path(scratch)/'latency.csv'
                        if mode=='latency' and repetition>=0: extra+=['--samples-file',str(sample_path)]
                        result=invoke('bench',path,variant,extra=extra)
                        if mode=='latency' and repetition>=0:
                            sample_output=out/'latency'/f'{label}-{variant}-{repetition}.csv.gz'
                            sample_output.parent.mkdir(exist_ok=True)
                            with sample_path.open('rb') as source, sample_output.open('wb') as dest:
                                with gzip.GzipFile(filename='',mode='wb',fileobj=dest,mtime=0) as compressed:
                                    compressed.write(source.read())
                            result['latency_samples']={'file':sample_output.relative_to(out).as_posix(),'sha256':sha(sample_output),'order':'input order','format':'gzip CSV duration_ns'}
                        if result['final_state_sha256']!=checkpoints[0]['final_state_sha256']:
                            raise AssertionError('timed pass final state differs')
                        result.update(workload=label,profile=profile,size=size,seed=seed,repetition=repetition,
                                      recorded_at_utc=dt.datetime.now(dt.timezone.utc).isoformat())
                        if repetition>=0: dump(target,result)
            # Small export fixture gives a bounded and explicitly separate serialization workload.
            if index==0:
                demo=Path(scratch)/'export.csv'; generate(demo,events=1900,capacity=200)
                demo_manifest=json.loads(demo.with_suffix('.manifest.json').read_text())
                dump(out/'workloads/export-demo.json',demo_manifest)
                demo_states=[invoke('validate',demo,v,extra=['--checkpoints']) for v in VARIANTS]
                if len({r['final_state_sha256'] for r in demo_states})!=1: raise AssertionError('export fixture variant mismatch')
                dump(out/'validation/export-demo.json',demo_states[0])
                for repetition in range(-1,repeats):
                    order=VARIANTS.copy();rng.shuffle(order)
                    for variant in order:
                        for mode in ('book','end_to_end','export'):
                            target=out/'raw'/f'export-demo-{mode}-{variant}-{repetition}.json'
                            if repetition>=0 and target.exists(): continue
                            extra=['--mode',mode,'--cpu',str(cpu)]
                            if mode=='export': extra+=['--export-file',str(Path(scratch)/'export.ndjson')]
                            r=invoke('bench',demo,variant,extra=extra)
                            if r['final_state_sha256']!=demo_states[0]['final_state_sha256']: raise AssertionError('export state mismatch')
                            r.update(workload='export-demo',profile='balanced',size='demo',seed=42,repetition=repetition,
                                     recorded_at_utc=dt.datetime.now(dt.timezone.utc).isoformat())
                            if repetition>=0: dump(target,r)
        micro=ROOT/'build'/'release'/('lob_microbench.exe' if os.name=='nt' else 'lob_microbench')
        if not (out/'microbench.json').exists():
            with pinned(cpu):
                subprocess.run([str(micro),'--benchmark_min_time=0.1s','--benchmark_repetitions=7',
                    '--benchmark_min_warmup_time=0.1','--benchmark_out_format=json','--benchmark_out='+str(out/'microbench.json')],check=True,stdout=subprocess.DEVNULL)
            micro_data=json.loads((out/'microbench.json').read_text())
            micro_data['context'].pop('host_name',None)
            micro_data['context']['executable']=micro.name
            dump(out/'microbench.json',micro_data)
    env['finished_at_utc']=dt.datetime.now(dt.timezone.utc).isoformat()
    env['ending_environment']=metadata();dump(manifest_path,env)
    dump(out/'complete.json',{'complete':True,'workloads':len(configs),'timing_repetitions':repeats,'memory_repetitions':repeats,'source_sha256':env['source_sha256']})
    print(f'Benchmark results: {out}',flush=True)
    return out
