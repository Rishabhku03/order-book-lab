"""Regenerate every measured workload and independently review stored aggregates."""
import argparse
import datetime
import hashlib
import json
import math
import statistics
import tempfile
import zipfile
from pathlib import Path
from common import ROOT, VARIANTS, dump, executable, invoke
from generate import generate, sha, PROFILES, SIZES
from schemas import benchmark

def audit(directory,out):
    directory=Path(directory);out=Path(out);out.mkdir(parents=True,exist_ok=True)
    started=datetime.datetime.now(datetime.timezone.utc).isoformat()
    schema=benchmark(directory) # Recalculate every saved latency percentile.
    env=json.loads((directory/'environment.json').read_text(encoding='utf-8'))
    assert env['suite']=='full'
    measured_binary=directory/'bin'/executable().name
    if not measured_binary.exists():measured_binary=executable()
    assert sha(measured_binary)==env['binary_sha256'],'Measured engine binary changed'
    current_binary_matches=sha(executable())==env['binary_sha256']
    archive=directory/'measurement-sources.zip'
    identity=json.loads((directory/'measurement-sources.json').read_text(encoding='utf-8'))
    assert sha(archive)==identity['archive_sha256']
    changes=[]
    with zipfile.ZipFile(archive) as z:
        names=z.namelist()
        ordered=['CMakeLists.txt','CMakePresets.json','requirements-dev.txt']
        ordered += [name for folder in ('include','src','tools','bench','cmake') for name in sorted(names) if name.startswith(folder+'/')]
        digest=hashlib.sha256()
        for name in ordered:
            content=z.read(name);digest.update(name.encode());digest.update(content)
            if (ROOT/name).read_bytes()!=content:changes.append(name)
        assert digest.hexdigest()==env['source_sha256']==identity['measured_source_sha256']
    # Publication prose and unused screenshot copies do not participate in timing.
    assert set(changes)<= {'tools/report.py','tools/run.py','tools/evidence.py','src/main.cpp'},('Measurement source changed',changes)
    if 'src/main.cpp' in changes:
        with zipfile.ZipFile(archive) as z:
            old=z.read('src/main.cpp').decode('utf-8').replace('\r\n','\n')
        current=(ROOT/'src/main.cpp').read_text(encoding='utf-8')
        timed=lambda text:text[text.index('template <class B> static Json run_bench'):text.index('\nint main(')]
        assert timed(old)==timed(current),'Native measurement function changed'
    regenerated=[]
    with tempfile.TemporaryDirectory(prefix='lob-audit-inputs-') as tmp:
        for profile in PROFILES:
            for size,(cap,levels) in SIZES.items():
                for seed in (17,42,2027):
                    label=f'{profile}-{size}-{seed}'
                    print('Regenerating and replaying:',label,flush=True)
                    path=Path(tmp)/(label+'.csv')
                    manifest=generate(path,profile,seed,1000000,cap,levels)
                    saved=json.loads((directory/'workloads'/(label+'.json')).read_text(encoding='utf-8'))
                    assert manifest==saved,('Workload bytes or metadata changed',label)
                    assert manifest['population']['max']<=cap
                    assert sum(manifest['realized_counts'].values())==1000000
                    saved_state=json.loads((directory/'validation'/(label+'.json')).read_text(encoding='utf-8'))
                    runs=[invoke('validate',path,v,extra=['--checkpoints']) for v in VARIANTS]
                    for result in runs:
                        assert result['checkpoints']==saved_state['checkpoints']
                        assert result['final_state_sha256']==saved_state['final_state_sha256']
                        expected=[manifest['realized_counts'].get(k,0)+(manifest['setup_events'] if k=='ADD' else 0) for k in ('ADD','CANCEL','DELETE','EXECUTE','REPLACE')]
                        assert result['summary']['statistics']['event_counts']==expected
                    regenerated.append({'workload':label,'input_sha256':manifest['sha256'],'variants':VARIANTS,'checkpoints':len(runs[0]['checkpoints']),'final_state_sha256':runs[0]['final_state_sha256']})
    raw=[json.loads(p.read_text(encoding='utf-8')) for p in sorted((directory/'raw').glob('*.json'))]
    summary=json.loads((directory/'summary.json').read_text(encoding='utf-8'))
    for group in summary['groups']:
        matches=[r for r in raw if all(r[k]==group[k] for k in ('workload','mode','variant'))]
        assert len(matches)==group['repetitions']==7
        for metric in ('events_per_second','average_ns_per_event','elapsed_seconds','construction_seconds','preload_seconds','setup_seconds'):
            if metric not in group:continue
            values=[r[metric] for r in matches];quartiles=statistics.quantiles(values,n=4,method='inclusive')
            for key,value in [('median',statistics.median(values)),('q1',quartiles[0]),('q3',quartiles[2]),('min',min(values)),('max',max(values))]:
                assert math.isclose(group[metric][key],value,rel_tol=1e-12,abs_tol=1e-15)
        if group['mode']=='latency':
            for key in ('p50','p95','p99','max','timer_pair_p50'):
                assert group['latency_ns'][key]==statistics.median(r['latency_ns'][key] for r in matches)
                assert group['latency_run_quartiles_ns'][key]==statistics.quantiles([r['latency_ns'][key] for r in matches],n=4,method='inclusive')
        if group['mode']=='parse':
            values=[r['bytes']/r['elapsed_seconds']/1e6 for r in matches]
            quartiles=statistics.quantiles(values,n=4,method='inclusive')
            for key,value in [('median',statistics.median(values)),('q1',quartiles[0]),('q3',quartiles[2])]:
                assert group['parse_mb_per_second'][key]==value
        if group['mode']=='memory':
            for metric,field in [('populated_memory_mib','memory_populated_before_buffer'),('peak_memory_mib','memory_final')]:
                key='current_bytes' if metric=='populated_memory_mib' else 'peak_bytes'
                assert group[metric]==statistics.median(r[field][key]/1048576 for r in matches)
    for comparison in summary['comparisons']:
        def runs(variant):return {r['repetition']:r for r in raw if r['workload']==comparison['workload'] and r['mode']=='book' and r['variant']==variant}
        candidate=runs(comparison['candidate']);base=runs('tree')
        ratios=[candidate[i]['events_per_second']/base[i]['events_per_second'] for i in range(7)]
        reductions=[1-candidate[i]['elapsed_seconds']/base[i]['elapsed_seconds'] for i in range(7)]
        assert comparison['paired_median_throughput_speedup']==statistics.median(ratios)
        assert comparison['paired_median_time_reduction']==statistics.median(reductions)
    for overhead in summary['overhead']:
        def matched(mode):return {r['repetition']:r for r in raw if r['workload']==overhead['workload'] and r['variant']==overhead['variant'] and r['mode']==mode}
        candidate=matched(overhead['mode']);base=matched(overhead['baseline_mode'])
        assert overhead['paired_median_time_ratio']==statistics.median(candidate[i]['elapsed_seconds']/base[i]['elapsed_seconds'] for i in range(7))
    from report import report
    reviewed_writeup=(ROOT/'docs/BENCHMARK_RESULTS.md').read_bytes()
    report(directory)
    assert (ROOT/'docs/BENCHMARK_RESULTS.md').read_bytes()==reviewed_writeup,'Reporting overwrote the reviewed write-up'
    result={'complete':True,'started_at_utc':started,'finished_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'schema':schema,'regenerated_workloads':regenerated,'archived_measured_binary_verified':True,
        'current_binary_matches_measured_binary':current_binary_matches,
        'measured_source_archive_verified':True,'changed_archived_files':changes,
        'timing_measurements_date':env['started_at_utc'],'new_performance_measurements':False,
        'summary_groups_recomputed':len(summary['groups']),'paired_comparisons_recomputed':len(summary['comparisons']),
        'report_regeneration_preserves_reviewed_writeup':True}
    dump(out/'workload-audit.json',result);print('All 27 input manifests, all three replays and stored aggregates agree.',flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',default='results/full');p.add_argument('--out',required=True);a=p.parse_args()
    audit(a.run,a.out)
