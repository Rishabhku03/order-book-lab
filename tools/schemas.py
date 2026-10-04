"""Validate saved exports and benchmark evidence without third-party packages."""
import argparse
import gzip
import json
import math
import re
from collections import defaultdict
from pathlib import Path
from common import ROOT, VARIANTS, dump
from generate import sha, PROFILES, SIZES

def require(condition, message):
    if not condition: raise ValueError(message)

def digest(value):
    require(isinstance(value,str) and re.fullmatch('[0-9a-f]{64}',value), 'invalid SHA-256')

def decimal(value, maximum=(1<<64)-1):
    require(isinstance(value,str) and re.fullmatch('0|[1-9][0-9]*',value) and int(value)<=maximum,'invalid decimal integer string')

def finite(value):
    require(type(value) in (int,float) and math.isfinite(value),'invalid numeric value')

def state(value):
    for side in ('bids','asks'):
        levels=value[side]; previous=None
        for level in levels:
            for key in ('price_ticks','quantity','orders'): decimal(level[key],(1<<63)-1 if key=='price_ticks' else (1<<64)-1)
            price=int(level['price_ticks'])
            require(price>0 and int(level['quantity'])>0 and int(level['orders'])>0,'empty level')
            require(previous is None or (price<previous if side=='bids' else price>previous),'unsorted levels')
            previous=price
    stats=value['statistics']
    for key in ('sequence','timestamp_ns','active_orders','total_quantity','peak_live_orders','bid_levels','ask_levels','execution_volume','execution_notional'):decimal(stats[key])
    require(len(stats['event_counts'])==5 and all(type(x)==int and 0<=x<(1<<64) for x in stats['event_counts']),'event counters')
    require(value['analytics']['status'] in ('empty','one-sided','normal','locked','crossed'),'book status')
    for key in ('midpoint','spread','imbalance','imbalance5','weighted_midpoint','vwap'):
        if value['analytics'][key] is not None:finite(value['analytics'][key])

def trace(value):
    require(type(value['schema_version'])==int and value['schema_version']==1 and value['synthetic'] is True,'trace schema')
    digest(value['input_sha256']);finite(value['tick_size']);require(value['tick_size']>0,'tick size')
    previous=None;timestamp=0
    for frame in value['frames']:
        state(frame);event=frame['event']
        for key in ('sequence','timestamp_ns','order_id'):decimal(event[key])
        for key in ('quantity','new_order_id','price_ticks'):
            if event[key] is not None:decimal(event[key],(1<<63)-1 if key=='price_ticks' else (1<<64)-1)
        seq=int(event['sequence']);ts=int(event['timestamp_ns'])
        require(previous is None or seq>previous,'trace sequence');require(ts>=timestamp,'trace timestamp')
        require(event['type'] in ('ADD','CANCEL','DELETE','EXECUTE','REPLACE'),'event type')
        require(event['sequence']==frame['statistics']['sequence'] and event['timestamp_ns']==frame['statistics']['timestamp_ns'],'frame/event ordering')
        previous=seq;timestamp=ts

def benchmark(directory, samples=True):
    directory=Path(directory);env=json.loads((directory/'environment.json').read_text())
    complete=json.loads((directory/'complete.json').read_text());require(complete['complete'] is True,'incomplete run')
    repeats=7 if env['suite']=='full' else 2
    configs=[f'{p}-{s}-{seed}' for p in PROFILES for s in SIZES for seed in (17,42,2027)] if env['suite']=='full' else ['balanced-small-42']
    expected=set()
    for label in configs:
        for mode in ('book','analytics','end_to_end','memory','parse'):
            for variant in (['hash_reserved'] if mode=='parse' else VARIANTS):expected.add((label,mode,variant))
        if '-medium-42' in label or env['suite']=='smoke':
            for variant in VARIANTS:expected.add((label,'latency',variant))
    expected.update(('export-demo',mode,v) for mode in ('book','end_to_end','export') for v in VARIANTS)
    groups=defaultdict(set);count=0;sample_files=0
    for path in sorted((directory/'raw').glob('*.json')):
        r=json.loads(path.read_text());count+=1
        require(r['schema_version']==1 and r['synthetic'] is True and r['build_type']=='Release','raw schema/build')
        key=(r['workload'],r['mode'],r['variant']);require(key in expected,'unexpected measurement group')
        require(type(r['repetition'])==int and 0<=r['repetition']<repeats and r['repetition'] not in groups[key],'duplicate repetition')
        groups[key].add(r['repetition']);digest(r['input_sha256']);digest(r['final_state_sha256'])
        manifest=json.loads((directory/'workloads'/(r['workload']+'.json')).read_text())
        validated=json.loads((directory/'validation'/(r['workload']+'.json')).read_text())
        require(r['input_sha256']==manifest['sha256'] and r['final_state_sha256']==validated['final_state_sha256'],'input/final state mismatch')
        expected_events=manifest['total_events'] if r['mode'] in ('parse','end_to_end','export') else manifest['measured_events']
        require(r.get('measured_events',expected_events)==expected_events,'measured event count')
        require(sum(r['statistics']['event_counts'])==manifest['total_events'],'accepted event count')
        require(str(r['cpu'])==str(env['cpu_affinity']),'affinity mismatch')
        if r['mode'] not in ('memory','latency'):
            elapsed=r['elapsed_seconds'];finite(elapsed);require(elapsed>0,'nonpositive duration')
            require(math.isclose(r['events_per_second'],r['measured_events']/elapsed,rel_tol=1e-12),'throughput formula')
            require(math.isclose(r['average_ns_per_event'],elapsed*1e9/r['measured_events'],rel_tol=1e-12),'average formula')
        if r['mode']=='latency':
            latency=r['latency_ns'];require(latency['p50']<=latency['p95']<=latency['p99']<=latency['max'],'percentile ordering')
            artifact=r['latency_samples'];target=directory/artifact['file'];require(target.resolve().is_relative_to(directory.resolve()),'unsafe sample path')
            require(sha(target)==artifact['sha256'],'sample checksum');sample_files+=1
            if samples:
                with gzip.open(target,'rt') as f:
                    require(next(f).strip()=='duration_ns','sample header');values=sorted(int(line) for line in f)
                require(len(values)==latency['samples']==r['measured_events'],'sample count')
                for name,pct in (('p50',50),('p95',95),('p99',99)):
                    require(values[(len(values)*pct+99)//100-1]==latency[name],'sample percentile mismatch')
                require(values[-1]==latency['max'],'sample maximum')
        if r['mode']=='memory':
            require(r['memory_final']['peak_bytes']>=r['memory_populated_before_buffer']['current_bytes']>0,'memory measurements')
    require(set(groups)==expected,'missing groups')
    require(all(repetitions==set(range(repeats)) for repetitions in groups.values()),'missing repetitions')
    require((directory/'microbench.json').exists(),'missing Google Benchmark evidence')
    result={'complete':True,'groups':len(groups),'raw_runs':count,'repetitions':repeats,'latency_artifacts':sample_files,'samples_recomputed':samples}
    dump(directory/('schema-validation.json' if samples else 'schema-structure-validation.json'),result);return result

def exports():
    count=0
    for path in (ROOT/'web/data').glob('*.json'):
        if path.name.endswith('.manifest.json') or path.name=='scenarios.json':continue
        trace(json.loads(path.read_text()));count+=1
    require(count==3,'expected three demo traces');return {'complete':True,'traces':count}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run');p.add_argument('--skip-samples',action='store_true');a=p.parse_args()
    print(benchmark(a.run,not a.skip_samples) if a.run else exports())
