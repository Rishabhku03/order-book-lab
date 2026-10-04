import json
import shutil
import tempfile
from pathlib import Path
from common import ROOT, dump, invoke
from generate import generate, write_fixture

def prepare(preset='release'):
    output=ROOT/'web'/'data'; output.mkdir(parents=True,exist_ok=True)
    scenarios=[]
    with tempfile.TemporaryDirectory(prefix='lob-demo-') as tmp:
        for label,profile in [('balanced','balanced'),('cancellation','cancellation')]:
            path=Path(tmp)/(label+'.csv'); generate(path,profile,events=1900,capacity=200)
            target=Path(tmp)/(label+'-result'); invoke('replay',path,preset=preset,extra=['--output',str(target),'--trace'])
            shutil.copyfile(target/'trace.json',output/(label+'.json'))
            shutil.copyfile(path,output/(label+'.csv')); shutil.copyfile(path.with_suffix('.manifest.json'),output/(label+'.manifest.json'))
            scenarios.append({'id':label,'label':'Balanced flow' if label=='balanced' else 'Cancellation-heavy flow','file':f'data/{label}.json'})
        # This short sequence makes empty, crossed, locked and one-sided states easy to inspect.
        rows=[
            [1,0,'ADD',9007199254740993,'B',10000,100,''],
            [2,1000,'ADD',2,'A',10004,60,''],
            [3,2000,'ADD',3,'B',9999,80,''],
            [4,3000,'EXECUTE',9007199254740993,'','',40,''],
            [5,4000,'REPLACE',2,'',9999,60,4],
            [6,5000,'REPLACE',4,'',10000,60,5],
            [7,6000,'CANCEL',9007199254740993,'','',60,''],
            [8,7000,'DELETE',3,'','','',''],
            [9,8000,'EXECUTE',5,'','',60,'']]
        path=Path(tmp)/'lifecycle.csv'; write_fixture(path,rows)
        target=Path(tmp)/'lifecycle-result'; invoke('replay',path,preset=preset,extra=['--output',str(target),'--trace'])
        for source,dest in [(target/'trace.json','lifecycle.json'),(path,'lifecycle.csv'),(path.with_suffix('.manifest.json'),'lifecycle.manifest.json')]:
            shutil.copyfile(source,output/dest)
        scenarios.append({'id':'lifecycle','label':'Order lifecycle and edge cases','file':'data/lifecycle.json'})
    dump(output/'scenarios.json',scenarios)
    print('Prepared three synthetic scenarios in web/data')
