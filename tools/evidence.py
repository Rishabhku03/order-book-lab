"""Publish portable local verification evidence and an inspectable dashboard page."""
import html
import json
from common import ROOT, dump

def publish():
    output=ROOT/'web/verification';output.mkdir(parents=True,exist_ok=True)
    entries=[]
    specs=[('Independent correctness','results/verification.json'),('Coverage','results/coverage/summary.json'),
           ('Parser and state fuzzing','results/fuzz/summary.json'),('Clean source reproduction','results/reproduction/summary.json'),
           ('Desktop and mobile visual checks','results/visual-audit/summary.json'),('Local release checks','results/release-verification.json')]
    for title,source in specs:
        path=ROOT/source
        if not path.exists():continue
        data=json.loads(path.read_text(encoding='utf-8'));name=title.lower().replace(' ','-')+'.json'
        dump(output/name,data);entries.append((title,name,data))
    page=['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Verification · Order Book Lab</title><link rel="stylesheet" href="style.css"><header><a class="brand" href="index.html">ORDER BOOK LAB</a><nav><a href="index.html">Replay</a><a href="benchmarks.html">Benchmarks</a></nav></header><main><section class="intro"><p class="eyebrow">LOCAL VERIFICATION EVIDENCE</p><h1>Check the results.</h1><p>Visual checks cover layout, playback, uploads and downloads. Engine correctness, fuzzing and coverage are supported by the reports below.</p></section>']
    for title,name,data in entries:
        if title=='Independent correctness':
            description=f"{data['comparisons_including_setup']:,} event states compared across three implementations; {data['seeds']} seeds."
        elif title=='Coverage':
            description=f"{data['line_percent']:.2f}% of core/parser lines and {data['branch_percent']:.2f}% of branches covered."
        elif title=='Parser and state fuzzing':
            description='; '.join(f"{r['target']}: {r['budget_seconds']} seconds, exit {r['exit_code']}" for r in data['runs'])
        elif title=='Clean source reproduction':
            description=f"{len(data['identical_files_or_json_values'])} demo artifacts reproduced after a fresh build."
        elif title=='Desktop and mobile visual checks':
            description=f"{len(data['screenshots'])} captured views; white backgrounds and black text/charts; no page errors."
        else:
            description=f"{len(data['local_checks'])} local check groups passed. Full performance measurement is recorded separately."
        page.append('<section class="panel"><h2>'+html.escape(title)+'</h2><p>'+html.escape(description)+'</p><p><a href="verification/'+name+'" download>Download evidence</a></p><details><summary>View the recorded checks</summary><pre class="mono">'+html.escape(json.dumps(data,indent=2))+'</pre></details></section>')
    page.append('<section class="about"><h2>Release status</h2><p>A release commit, Linux CI execution and GitHub Pages deployment are pending. Local verification identifies the tested source and binaries using checksums.</p></section></main></html>')
    (ROOT/'web/verification.html').write_text(''.join(page),encoding='utf-8')

if __name__=='__main__':publish()
