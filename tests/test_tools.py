import csv
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from common import executable, invoke, VARIANTS, ROOT
from generate import generate, write_fixture, sha
from reference import Reference, rows
from verify import compare

class Integration(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='lob tests ');self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'events with spaces.csv'
        self.preset=os.environ.get('LOB_PRESET','release')

    def test_determinism(self):
        a=generate(self.path,events=100,capacity=20)
        other=self.path.parent/'second.csv';b=generate(other,events=100,capacity=20)
        self.assertEqual(a,b);self.assertEqual(self.path.read_bytes(),other.read_bytes())
        self.assertEqual(sum(a['population']['histogram'].values()),100)
        self.assertAlmostEqual(sum(a['realized_percentages'].values()),100)
        with self.assertRaises(ValueError):generate(self.path.parent/'invalid-band.csv',levels=100000)
        golden=ROOT/'tests'/'golden.sha256'
        if golden.exists(): self.assertEqual(a['sha256'],golden.read_text().strip())
        else: self.fail('Committed generator golden hash is missing')

    def test_metamorphic(self):
        generate(self.path,events=50,capacity=10,levels=4)
        original=list(rows(self.path)); baseline=invoke('validate',self.path,preset=self.preset,extra=['--full-state'])['summary']
        for transform in ('rename','scale','shift'):
            modified=[]
            for row in original:
                e=row.copy()
                if transform=='rename':
                    for key in ('order_id','new_order_id'):
                        if e[key]:e[key]=str(int(e[key])+9007199254740993)
                if transform=='scale' and e['quantity']:e['quantity']=str(int(e['quantity'])*3)
                if transform=='shift' and e['price_ticks']:e['price_ticks']=str(int(e['price_ticks'])+123)
                modified.append([e[k] for k in e])
            p=self.path.parent/(transform+'.csv');write_fixture(p,modified)
            for variant in VARIANTS:
                actual=invoke('validate',p,variant,self.preset,extra=['--full-state'])['summary']
                for side in ('bids','asks'):
                    expected=[{**level,'price_ticks':str(int(level['price_ticks'])+(123 if transform=='shift' else 0)),
                               'quantity':str(int(level['quantity'])*(3 if transform=='scale' else 1))} for level in baseline[side]]
                    self.assertEqual(actual[side],expected)
                for metric in ('imbalance','imbalance5','spread'):
                    self.assertAlmostEqual(actual['analytics'][metric],baseline['analytics'][metric])
                for metric in ('midpoint','vwap','weighted_midpoint'):
                    self.assertAlmostEqual(actual['analytics'][metric],baseline['analytics'][metric]+(123 if transform=='shift' else 0))

    def test_reference_and_cli(self):
        generate(self.path,events=80,capacity=20)
        ref=Reference()
        for row in rows(self.path):ref.apply(row)
        for variant in VARIANTS:
            result=invoke('validate',self.path,variant,self.preset,extra=['--full-state'])
            compare(ref.snapshot(),result['summary'])
        result=invoke('inspect',self.path,preset=self.preset,extra=['--sequence','1'])
        self.assertEqual(result['event_count'],1)
        out=self.path.parent/'output'
        invoke('replay',self.path,preset=self.preset,extra=['--output',str(out),'--trace'])
        trace=json.loads((out/'trace.json').read_text());self.assertEqual(len(trace['frames']),90)
        command=[str(executable(self.preset)),'replay','--input',str(self.path),'--manifest',str(self.path.with_suffix('.manifest.json')),'--output',str(out)]
        failure=subprocess.run(command,capture_output=True,text=True)
        self.assertEqual(failure.returncode,2);self.assertFalse(json.loads(failure.stderr)['complete'])
        self.path.write_text('corrupted')
        failure=subprocess.run(command,capture_output=True,text=True);self.assertIn('SHA-256',failure.stderr)

    def test_failures(self):
        for args in ([],['unknown'],['validate','--unknown','x'],['validate','--input','missing','--manifest','missing']):
            p=subprocess.run([str(executable(self.preset)),*args],capture_output=True,text=True)
            self.assertEqual(p.returncode,2); self.assertFalse(json.loads(p.stderr)['complete'])
        write_fixture(self.path,[[1,0,'ADD',1,'B',10,1,''],[2,1,'CANCEL',1,'','',2,'']])
        p=subprocess.run([str(executable(self.preset)),'validate','--input',str(self.path),'--manifest',str(self.path.with_suffix('.manifest.json'))],capture_output=True,text=True)
        self.assertEqual(p.returncode,2);self.assertIn('sequence 2',p.stderr);self.assertIn('line 3',p.stderr)

    def test_trace_time_range_replays_prefix(self):
        write_fixture(self.path,[[1,0,'ADD',1,'B',10,7,''],[2,10,'CANCEL',1,'','',2,''],[3,20,'EXECUTE',1,'','',1,'']])
        out=self.path.parent/'range'
        result=invoke('replay',self.path,preset=self.preset,extra=['--output',str(out),'--trace','--trace-from-ns','10','--trace-to-ns','10'])
        frames=json.loads((out/'trace.json').read_text())['frames']
        self.assertEqual(len(frames),1);self.assertEqual(frames[0]['bids'][0]['quantity'],'5')
        self.assertEqual(result['event_count'],3)

    def test_manifest_and_output_errors(self):
        generate(self.path,events=5,capacity=10)
        manifest=self.path.with_suffix('.manifest.json');original=json.loads(manifest.read_text())
        base=[str(executable(self.preset)),'validate','--input',str(self.path),'--manifest',str(manifest)]
        for key,value in [('max_live_orders',-1),('max_live_orders',0),('setup_events',999),('total_events',1),('schema_version',2),('schema_version',1.9),('synthetic',False),('tick_size',0)]:
            changed={**original,key:value};manifest.write_text(json.dumps(changed))
            failure=subprocess.run(base,capture_output=True,text=True);self.assertEqual(failure.returncode,2,(key,value))
        manifest.write_text(json.dumps(original))
        # A file where a directory is needed gives a deterministic write failure, including on Windows.
        obstacle=self.path.parent/'obstacle';obstacle.write_text('keep')
        failure=subprocess.run([str(executable(self.preset)),'replay','--input',str(self.path),'--manifest',str(manifest),'--output',str(obstacle/'result')],capture_output=True,text=True)
        self.assertEqual(failure.returncode,2);self.assertEqual(obstacle.read_text(),'keep')
        failure=subprocess.run(base+['--variant','unknown'],capture_output=True,text=True);self.assertEqual(failure.returncode,2)
        failure=subprocess.run(base+['--input',str(self.path)],capture_output=True,text=True);self.assertEqual(failure.returncode,2)

    def test_empty_book_and_missing_sequence(self):
        write_fixture(self.path,[])
        result=invoke('validate',self.path,preset=self.preset)
        self.assertEqual(result['summary']['analytics']['status'],'empty')
        self.assertIsNone(result['summary']['analytics']['midpoint'])
        failure=subprocess.run([str(executable(self.preset)),'inspect','--input',str(self.path),'--manifest',str(self.path.with_suffix('.manifest.json')),'--sequence','1'],capture_output=True,text=True)
        self.assertEqual(failure.returncode,2)
        # Inspection skips later book updates, but the input ordering contract
        # applies to every parsed record, including records beyond the target.
        for records,target,message in [
            ([[1,0,'ADD',1,'B',100,10,''],[3,1,'ADD',2,'A',101,10,''],[2,2,'DELETE',1,'','','','']],2,'sequence must increase'),
            ([[1,0,'ADD',1,'B',100,10,''],[3,2,'ADD',2,'A',101,10,''],[4,1,'DELETE',1,'','','','']],1,'timestamp decreased')]:
            write_fixture(self.path,records)
            for variant in VARIANTS:
                failure=subprocess.run([str(executable(self.preset)),'inspect','--input',str(self.path),'--manifest',str(self.path.with_suffix('.manifest.json')),'--sequence',str(target),'--variant',variant],capture_output=True,text=True)
                self.assertEqual(failure.returncode,2);self.assertIn(message,failure.stderr)

    @unittest.skipUnless(os.environ.get('LOB_PRESET','release')=='release','Measured harness requires Release')
    def test_analytics_benchmark_consumes_every_metric(self):
        manifest=generate(self.path,events=20,capacity=10)
        reference=Reference();expected=0
        for index,row in enumerate(rows(self.path)):
            reference.apply(row)
            if index>=manifest['setup_events']:
                a=reference.snapshot()['analytics']
                expected+=sum(a[k] or 0 for k in ('midpoint','spread','imbalance','imbalance5','weighted_midpoint','vwap'))+len(a['status'])
        for variant in VARIANTS:
            result=invoke('bench',self.path,variant,extra=['--mode','analytics'])
            self.assertAlmostEqual(result['analytics_sink'],expected,places=6)
        exported=self.path.parent/'export.ndjson'
        invoke('bench',self.path,extra=['--mode','export','--export-file',str(exported)])
        frames=[json.loads(line) for line in exported.read_text().splitlines()]
        self.assertEqual(len(frames),manifest['total_events'])
        self.assertEqual(frames[-1]['event']['sequence'],str(manifest['total_events']))

if __name__=='__main__':unittest.main()
