import csv

import html

import json

import shutil

import statistics

from collections import defaultdict

from pathlib import Path

from common import ROOT, dump



def chart(title,items,unit):

    if not items: return ''

    largest=max(v for _,v in items) or 1; height=45+len(items)*26

    body=[f'<h2>{html.escape(title)}</h2><div class="report-chart"><svg viewBox="0 0 920 {height}" role="img" aria-label="{html.escape(title)}">']

    for i,(label,value) in enumerate(items):

        y=25+i*26; width=value/largest*420

        body.append(f'<text x="0" y="{y+13}">{html.escape(label)}</text><rect class="chart-bar" x="325" y="{y}" width="{width}" height="16"/><text x="{755}" y="{y+13}">{value:,.2f} {unit}</text>')

    return ''.join(body)+'</svg></div><p class="chart-hint">Scroll horizontally to see the complete chart on a narrow screen.</p>'



def report(directory):

    directory=Path(directory)

    if not (directory/'complete.json').exists(): raise RuntimeError('Benchmark run is incomplete; finish it before reporting')

    from schemas import benchmark as validate_benchmark

    validate_benchmark(directory, samples=False)

    env=json.loads((directory/'environment.json').read_text())

    raw=[json.loads(p.read_text()) for p in sorted((directory/'raw').glob('*.json'))]

    groups=defaultdict(list)

    for r in raw: groups[(r['workload'],r['mode'],r['variant'])].append(r)

    records=[]

    for (workload,mode,variant),runs in sorted(groups.items()):

        record={'workload':workload,'mode':mode,'variant':variant,'repetitions':len(runs)}

        if mode=='parse':

            for r in runs: r['parse_mb_per_second']=r['bytes']/r['elapsed_seconds']/1e6

        keys=['events_per_second','average_ns_per_event','elapsed_seconds','parse_mb_per_second','construction_seconds','preload_seconds','setup_seconds']

        for k in keys:

            vals=[r[k] for r in runs if k in r]

            if vals:

                quartiles=statistics.quantiles(vals,n=4,method='inclusive') if len(vals)>1 else [vals[0]]*3

                record[k]={'median':statistics.median(vals),'q1':quartiles[0],'q3':quartiles[2],'min':min(vals),'max':max(vals)}

        if mode=='latency':

            record['latency_ns']={k:statistics.median(r['latency_ns'][k] for r in runs) for k in ('p50','p95','p99','max','timer_pair_p50')}

            record['latency_run_quartiles_ns']={k:statistics.quantiles([r['latency_ns'][k] for r in runs],n=4,method='inclusive') for k in ('p50','p95','p99','max','timer_pair_p50')}

        if mode=='memory':

            record['populated_memory_mib']=statistics.median(r['memory_populated_before_buffer']['current_bytes']/1048576 for r in runs)

            record['peak_memory_mib']=statistics.median(r['memory_final']['peak_bytes']/1048576 for r in runs)

        records.append(record)

    comparisons=[]

    for (workload,mode,variant),runs in sorted(groups.items()):

        if mode!='book' or variant=='tree':continue

        baseline={r['repetition']:r for r in groups[(workload,'book','tree')]}

        ratios=[r['events_per_second']/baseline[r['repetition']]['events_per_second'] for r in runs]

        comparisons.append({'workload':workload,'candidate':variant,'baseline':'tree',

                            'paired_median_throughput_speedup':statistics.median(ratios),

                            'paired_min_speedup':min(ratios),'paired_max_speedup':max(ratios),

                            'paired_median_time_reduction':statistics.median(1-r['elapsed_seconds']/baseline[r['repetition']]['elapsed_seconds'] for r in runs)})

    overhead=[]

    for (workload,mode,variant),runs in sorted(groups.items()):

        if mode not in ('analytics','export'):continue

        base_mode='book' if mode=='analytics' else 'end_to_end'

        baseline={r['repetition']:r for r in groups[(workload,base_mode,variant)]}

        ratios=[r['elapsed_seconds']/baseline[r['repetition']]['elapsed_seconds'] for r in runs]

        overhead.append({'workload':workload,'mode':mode,'variant':variant,'baseline_mode':base_mode,

                         'paired_median_time_ratio':statistics.median(ratios)})

    dump(directory/'summary.json',{'environment':env,'groups':records,'comparisons':comparisons,'overhead':overhead})

    if env['suite']=='full':

        text=['# Local benchmark results','',

              f"Measured on {env.get('cpu_model','unknown CPU')}, {env['os']}, {env.get('cmake_cxx_compiler_id','unknown compiler')} {env.get('cmake_cxx_compiler_version','')}. Logical CPU {env['cpu_affinity']}; seven repetitions per group.",'',

              'Inputs are synthetic. Each main workload contains one million measured events plus its setup prefix. Figures below are medians; raw repetitions and inclusive quartiles remain in the report.','',

              '## Order index comparison','',

              '| Candidate / tree | Lowest paired median speedup | Highest paired median speedup | Median across 27 workloads |',

              '| --- | ---: | ---: | ---: |']

        for variant in ('hash','hash_reserved'):

            ratios=[c['paired_median_throughput_speedup'] for c in comparisons if c['candidate']==variant and c['workload']!='export-demo']

            text.append(f'| {variant} | {min(ratios):.3f}× | {max(ratios):.3f}× | {statistics.median(ratios):.3f}× |')

        text+=['','The range shows workload dependence. The median across configurations gives equal weight to each workload; it is not a combined stream throughput. Reservation trades bucket allocation and setup costs against lookup and rehash behavior. Compare its populated memory and construction costs alongside speed.','',

               '## Workload patterns at seed 42','',

               '| Workload | Tree M events/s | Hash M events/s | Reserved hash M events/s |',

               '| --- | ---: | ---: | ---: |']

        lookup={(r['workload'],r['mode'],r['variant']):r for r in records}

        for profile in ('balanced','cancellation','execution'):

            for size in ('small','medium','large'):

                label=f'{profile}-{size}-42'

                text.append('| '+label+' | '+' | '.join(f"{lookup[(label,'book',v)]['events_per_second']['median']/1e6:.3f}" for v in ('tree','hash','hash_reserved'))+' |')

        text+=['','Compare event profiles within a scale and implementation. Both order population and available depth change between scales, so the scaling result cannot be attributed to order count alone.','',

               '## Analytics, parsing and export','']

        for mode in ('analytics','export'):

            ratios=[r['paired_median_time_ratio'] for r in overhead if r['mode']==mode]

            text.append(f"{mode.capitalize()} elapsed-time ratios range from {min(ratios):.3f}× to {max(ratios):.3f}× against their matching baselines. Values below one indicate measurement variability rather than negative work.")

        parsing=[r['parse_mb_per_second']['median'] for r in records if r['mode']=='parse']

        text+=['',f'Parse-only medians range from {min(parsing):.2f} to {max(parsing):.2f} MB/s. End-to-end runs include file opening, parsing, replay and summary calculation; their file cache is uncontrolled.','',

               '## Limits and reproduction','',

               'Instrumented update latency includes timer reads; run-level p50, p95, p99, maxima, dispersion and the empty timer baseline are in the report. The saved gzip samples reproduce each percentile. Memory is Windows working set or Linux RSS, including process overhead.','',

               'Laptop power, scheduling and thermal drift can affect results. No network, queueing, real-market or profitability claim follows from these inputs.','',

               'Run `python tools/run.py benchmark --suite full` after a release build. This creates a fresh timestamped directory. Use its printed path with `python tools/schemas.py --run <run-directory>` and `python tools/run.py report --run <run-directory>`. Existing runs can resume only when their source and binary fingerprints match.','',

               'Evidence: [comparison report](report.html), [all measured groups](summary.json), [raw repetitions](evidence/raw-results.json), [environment](environment.json).','']

        (directory/'BENCHMARK_RESULTS.md').write_text('\n'.join(text),encoding='utf-8')

    columns=['workload','mode','variant','repetitions']

    metrics=['events_per_second','average_ns_per_event','elapsed_seconds','parse_mb_per_second','construction_seconds','preload_seconds','setup_seconds']

    columns += [stat+'_'+metric for metric in metrics for stat in ('median','q1','q3')]

    columns += ['latency_'+key+'_ns' for key in ('p50','p95','p99','max','timer_pair_p50')] + ['populated_memory_mib','peak_memory_mib']

    with (directory/'summary.csv').open('w',newline='') as f:

        writer=csv.writer(f);writer.writerow(columns)

        for r in records:

            row=[r[k] for k in columns[:4]]

            row += [r.get(metric,{}).get(stat,'') for metric in metrics for stat in ('median','q1','q3')]

            row += [r.get('latency_ns',{}).get(key,'') for key in ('p50','p95','p99','max','timer_pair_p50')]

            row += [r.get(key,'') for key in ('populated_memory_mib','peak_memory_mib')]

            writer.writerow(row)

    selected=[r for r in records if r['mode']=='book' and ('-42' in r['workload'])]

    items=[(r['workload']+' / '+r['variant'],r['events_per_second']['median']/1e6) for r in selected]

    lat=[(r['workload']+' / '+r['variant'],r['latency_ns']['p99']) for r in records if r['mode']=='latency']

    mem=[(r['workload']+' / '+r['variant'],r['populated_memory_mib']) for r in records if r['mode']=='memory' and '-42' in r['workload']]

    chunks=['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Benchmarks · Order Book Lab</title><link rel="stylesheet" href="style.css"><header><a class="brand" href="index.html">ORDER BOOK <span>LAB</span></a><nav><a href="index.html">Replay</a></nav></header><main>',

            '<section class="intro"><p class="eyebrow">NATIVE C++ · SYNTHETIC WORKLOADS</p><h1>Measured, with context.</h1>',

            f'<p>{html.escape(env.get("cpu_model",env.get("cpu","Unknown CPU")))} · {html.escape(env["os"])} · {html.escape(env["suite"])} suite</p>',

            '<p>Each bar is the median of repeated runs. Throughput excludes parsing and export; p99 is an instrumented update duration. Playback speed in the demo has no relationship to these measurements.</p>',

            f'<p class="mono">Source SHA-256: {env["source_sha256"]}<br>Engine commit: {html.escape(env["engine_commit"])}</p></section>',

            chart('Book updates · seed 42',items,'M events/s'),chart('Instrumented p99 update latency',lat,'ns'),chart('Populated process memory before event buffer',mem,'MiB'),

            '<h2>All measured groups</h2><div class="report-table"><table><thead><tr><th>Workload</th><th>Mode</th><th>Variant</th><th>Runs</th><th>Median events/s</th><th>IQR events/s</th></tr></thead><tbody>']

    for r in records:

        eps=r.get('events_per_second')

        chunks.append('<tr>'+''.join(f'<td>{html.escape(str(v))}</td>' for v in [r['workload'],r['mode'],r['variant'],r['repetitions'],f'{eps["median"]:,.0f}' if eps else 'N/A',f'{eps["q1"]:,.0f} to {eps["q3"]:,.0f}' if eps else 'N/A'])+'</tr>')

    chunks.append('</tbody></table></div><section class="about"><h2>Paired comparisons</h2><p>Speedups compare each candidate with the tree index on the same workload and repetition. The summary JSON also records analytics and export time ratios against their matching baselines.</p><div class="report-table"><table><thead><tr><th>Workload</th><th>Candidate</th><th>Median speedup</th><th>Observed range</th></tr></thead><tbody>')

    for c in comparisons:

        chunks.append(f'<tr><td>{html.escape(c["workload"])}</td><td>{c["candidate"]}</td><td>{c["paired_median_throughput_speedup"]:.3f}×</td><td>{c["paired_min_speedup"]:.3f} to {c["paired_max_speedup"]:.3f}×</td></tr>')

    chunks.append('</tbody></table></div><h2>Parsing and setup costs</h2><div class="report-table"><table><thead><tr><th>Workload / mode / variant</th><th>Parsing MB/s</th><th>Construction ms</th><th>Preload ms</th><th>Setup ms</th></tr></thead><tbody>')

    for r in records:

        values=[r['workload']+' / '+r['mode']+' / '+r['variant']]

        values += [f"{r[key]['median']*factor:,.3f}" if key in r else 'N/A' for key,factor in [('parse_mb_per_second',1),('construction_seconds',1000),('preload_seconds',1000),('setup_seconds',1000)]]

        chunks.append('<tr>'+''.join('<td>'+html.escape(str(v))+'</td>' for v in values)+'</tr>')

    chunks.append('</tbody></table></div><h2>Instrumented latency distribution</h2><p>Entries summarize run-level statistics by their median. Percentiles use nearest rank within each run. The maximum column is the median of run maxima; individual maxima remain in raw results. Timer-pair readings are reported without subtraction, and clock quantization can produce zero readings.</p><div class="report-table"><table><thead><tr><th>Workload / variant</th><th>p50 ns</th><th>p95 ns</th><th>p99 ns</th><th>p99 run IQR ns</th><th>Median run max ns</th><th>Timer pair ns</th></tr></thead><tbody>')

    for r in records:

        if r['mode']!='latency':continue

        l=r['latency_ns'];q=r['latency_run_quartiles_ns']['p99']

        values=[r['workload']+' / '+r['variant'],l['p50'],l['p95'],l['p99'],f'{q[0]} to {q[2]}',l['max'],l['timer_pair_p50']]

        chunks.append('<tr>'+''.join('<td>'+html.escape(str(v))+'</td>' for v in values)+'</tr>')

    chunks.append('</tbody></table></div><h2>Analytics and export overhead</h2><div class="report-table"><table><thead><tr><th>Workload / variant</th><th>Mode / baseline</th><th>Paired time ratio</th></tr></thead><tbody>')

    for r in overhead:

        chunks.append(f"<tr><td>{html.escape(r['workload']+' / '+r['variant'])}</td><td>{r['mode']} / {r['baseline_mode']}</td><td>{r['paired_median_time_ratio']:.3f}×</td></tr>")

    chunks.append('</tbody></table></div><h2>Method and limitations</h2><p>Warm-up precedes measured passes. Each measurement runs in a separate process on the recorded logical CPU. File cache is uncontrolled and input checksums are read before timing. Workload sizes change both order count and available price levels. Memory is process working set/RSS, not exact allocator bytes. Every variant must end in the same state.</p><p>Local laptop scheduling, power and temperature can change results. The timer-pair baseline is included in the raw latency results; it is not subtracted. No market-profitability or network-latency claim is made.</p><p><a href="evidence/summary.json">Summary JSON</a> · <a href="evidence/summary.csv">Summary CSV</a> · <a href="evidence/environment.json">Environment</a> · <a href="evidence/raw-results.json">All repetitions</a></p></section></main></html>')

    if env['suite']!='full':

        chunks.insert(2,'<p class="error">Preliminary smoke run. These setup measurements are not final resume evidence. The full benchmark matrix remains pending.</p>')

    chunks[-1]=chunks[-1].replace('</section></main>', '<p><a href="evidence/workload-manifests.json">Workload manifests</a> · <a href="evidence/state-validation.json">State validation</a> · <a href="evidence/schema-validation.json">Evidence validation</a></p></section></main>')

    page=''.join(chunks);(directory/'report.html').write_text(page,encoding='utf-8')

    shutil.copyfile(ROOT/'web'/'style.css',directory/'style.css')

    evidence=directory/'evidence'; evidence.mkdir(exist_ok=True)

    for name in ('summary.json','summary.csv','environment.json','schema-validation.json'): shutil.copyfile(directory/name,evidence/name)

    dump(evidence/'raw-results.json',raw)

    dump(evidence/'workload-manifests.json',[json.loads(p.read_text()) for p in sorted((directory/'workloads').glob('*.json'))])

    dump(evidence/'state-validation.json',[json.loads(p.read_text()) for p in sorted((directory/'validation').glob('*.json'))])

    print(f'Report: {directory / "report.html"}')

    return records



def publish_local(directory):

    directory=Path(directory);report(directory)

    shutil.copyfile(directory/'report.html',ROOT/'web'/'benchmarks.html')

    shutil.copytree(directory/'evidence',ROOT/'web'/'evidence',dirs_exist_ok=True)
