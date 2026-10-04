"""Create inspectable contract fixtures and check them with every native index."""
import argparse
import copy
import hashlib
import json
import subprocess
from pathlib import Path
from common import ROOT, VARIANTS, dump, executable
from generate import HEADER, write_fixture
from reference import Reference, rows
from verify import compare

def prepare(out, check=False):
    out=Path(out)
    if out.exists():raise FileExistsError('Choose a new fixture directory: '+str(out))
    out.mkdir(parents=True)
    cases=[]
    def add(name, records=None, error=None, raw=None):
        path=out/(name+'.csv')
        manifest=write_fixture(path,records or [])
        if raw is not None:
            path.write_bytes(raw)
            manifest['sha256']=hashlib.sha256(raw).hexdigest()
            dump(path.with_suffix('.manifest.json'),manifest)
        cases.append({'name':name,'expected_exit':2 if error else 0,'error_contains':error})
    base=[[1,0,'ADD',1,'B',100,10,''],[3,0,'ADD',2,'A',104,30,'']]
    lifecycle=base+[[4,2,'ADD',3,'B',100,20,''],[5,3,'CANCEL',3,'','',5,''],
        [6,4,'EXECUTE',1,'','',4,''],[7,5,'REPLACE',2,'',99,7,4],
        [8,6,'REPLACE',4,'',100,7,2],[9,7,'DELETE',3,'','','',''],
        [10,8,'EXECUTE',1,'','',6,''],[11,9,'CANCEL',2,'','',7,''],
        [12,10,'ADD',1,'B',100,1,'']]
    add('lifecycle',lifecycle);add('empty',[])
    add('one-sided',[base[0]])
    add('vwap',[[1,0,'ADD',1,'B',100,3,''],[2,0,'ADD',2,'A',110,7,''],
        [3,1,'EXECUTE',1,'','',2,''],[4,1,'EXECUTE',2,'','',3,'']])
    invalid={
        'duplicate-id':[4,1,'ADD',1,'B',100,1,''],
        'unknown-cancel':[4,1,'CANCEL',99,'','',1,''],
        'unknown-delete':[4,1,'DELETE',99,'','','',''],
        'unknown-execute':[4,1,'EXECUTE',99,'','',1,''],
        'unknown-replace':[4,1,'REPLACE',99,'',100,1,3],
        'excess-cancel':[4,1,'CANCEL',1,'','',11,''],
        'excess-execute':[4,1,'EXECUTE',1,'','',11,''],
        'zero-add':[4,1,'ADD',3,'B',100,0,''],
        'zero-cancel':[4,1,'CANCEL',1,'','',0,''],
        'zero-execute':[4,1,'EXECUTE',1,'','',0,''],
        'zero-replace':[4,1,'REPLACE',1,'',100,0,3],
        'zero-price':[4,1,'ADD',3,'B',0,1,''],
        'negative-price':[4,1,'ADD',3,'B',-1,1,''],
        'replace-active-id':[4,1,'REPLACE',1,'',101,1,2],
        'replace-same-id':[4,1,'REPLACE',1,'',101,1,1],
        'replace-missing-id':[4,1,'REPLACE',1,'',101,1,''],
        'replace-side':[4,1,'REPLACE',1,'B',101,1,3],
        'delete-quantity':[4,1,'DELETE',1,'','',1,''],
        'cancel-price':[4,1,'CANCEL',1,'',100,1,''],
        'add-missing-side':[4,1,'ADD',3,'',100,1,''],
        'add-extra-id':[4,1,'ADD',3,'B',100,1,4],
        'duplicate-sequence':[3,1,'DELETE',1,'','','',''],
        'reversed-sequence':[2,1,'DELETE',1,'','','','']}
    for name,record in invalid.items():add(name,base+[record],error='sequence '+str(record[0]))
    add('reversed-time',[[1,10,'ADD',1,'B',100,1,''],[2,9,'DELETE',1,'','','','']],error='timestamp decreased')
    maximum=(1<<64)-1
    add('quantity-overflow',[[1,0,'ADD',1,'B',1,maximum,''],[2,0,'ADD',2,'A',2,1,'']],error='book quantity overflow')
    add('replacement-overflow',[[1,0,'ADD',1,'B',1,1,''],[2,0,'ADD',2,'A',2,1,''],[3,0,'REPLACE',1,'',1,maximum,3]],error='book quantity overflow')
    add('trade-product-overflow',[[1,0,'ADD',1,'B',(1<<63)-1,3,''],[2,0,'EXECUTE',1,'','',3,'']],error='trade multiplication overflow')
    add('trade-total-overflow',[[1,0,'ADD',1,'B',1,maximum,''],[2,0,'EXECUTE',1,'','',maximum,''],[3,0,'ADD',2,'A',1,1,''],[4,0,'EXECUTE',2,'','',1,'']],error='trade accumulator overflow')
    header=','.join(HEADER)+'\n'
    for name,line,error in [
        ('missing-field','1,0,ADD,1,B,100,1','eight fields'),
        ('extra-field','1,0,ADD,1,B,100,1,,','eight fields'),
        ('bad-integer','x,0,ADD,1,B,100,1,','invalid integer'),
        ('unsigned-negative','-1,0,ADD,1,B,100,1,','invalid integer'),
        ('integer-overflow','18446744073709551616,0,ADD,1,B,100,1,','invalid integer'),
        ('price-overflow','1,0,ADD,1,B,9223372036854775808,1,','invalid integer'),
        ('unknown-type','1,0,BOGUS,1,B,100,1,','unknown event type'),
        ('invalid-side','1,0,ADD,1,X,100,1,','invalid side'),
        ('whitespace','1,0,ADD,1,B,100, 1,','invalid integer'),
        ('quoted-field','1,0,ADD,1,B,100,"1",','invalid integer'),
        ('blank-record','','eight fields'),
        ('oversized-record','x'*4097,'4096 bytes')]:
        add(name,error=error,raw=(header+line+'\n').encode())
    add('empty-file',error='empty input',raw=b'')
    add('malformed-header',error='invalid header',raw=b'bad\n')
    for name,raw in [('lf',(header+'1,0,ADD,1,B,100,1,\n').encode()),
                     ('crlf',(header+'1,0,ADD,1,B,100,1,\n').replace('\n','\r\n').encode()),
                     ('no-final-newline',(header+'1,0,ADD,1,B,100,1,').encode())]:
        add(name,[[1,0,'ADD',1,'B',100,1,'']],raw=raw)
    dump(out/'cases.json',cases)
    # Browser fixtures preserve the exported schema and need no second book engine.
    original=json.loads((ROOT/'web/data/lifecycle.json').read_text(encoding='utf-8'))
    dump(out/'valid-upload.json',original)
    dump(out/'bad-upload.json',{'bad':True})
    bad=copy.deepcopy(original);bad['frames'][0]['event']['quantity']='0';dump(out/'zero-upload.json',bad)
    bad=copy.deepcopy(original);bad['frames'][0]['event']['order_id']=9007199254740993;dump(out/'numeric-id-upload.json',bad)
    frames=[]
    for i in range(10001):
        f=copy.deepcopy(original['frames'][0]);f['event']['sequence']=str(i+1)
        f['statistics']['sequence']=str(i+1);frames.append(f)
    (out/'frame-limit-upload.json').write_text(json.dumps({**original,'frames':frames},separators=(',',':')),encoding='utf-8')
    (out/'10000-frames-upload.json').write_text(json.dumps({**original,'frames':frames[:10000]},separators=(',',':')),encoding='utf-8')
    payload=json.dumps(original).encode()
    (out/'10mb-upload.json').write_bytes(payload+b' '*(10*1024*1024-len(payload)))
    (out/'over-10mb-upload.json').write_bytes(payload+b' '*(10*1024*1024+1-len(payload)))
    if check:
        checked=0
        for case in cases:
            path=out/(case['name']+'.csv')
            for variant in VARIANTS:
                result=subprocess.run([str(executable()),'validate','--input',str(path),'--manifest',str(path.with_suffix('.manifest.json')),'--variant',variant,'--full-state'],capture_output=True,text=True)
                assert result.returncode==case['expected_exit'],(case,result.stdout,result.stderr)
                if case['expected_exit']:
                    error=json.loads(result.stderr)
                    assert error['complete'] is False and case['error_contains'] in error['error'],error
                else:
                    ref=Reference()
                    for row in rows(path):ref.apply(row)
                    compare(ref.snapshot(),json.loads(result.stdout)['summary'],case['name']+' '+variant)
                checked+=1
        dump(out/'verification.json',{'complete':True,'cases':len(cases),'native_checks':checked,'variants':VARIANTS})
        print(f'{len(cases)} contract cases passed across all three indexes ({checked} native checks).')
    print('Manual fixtures:',out)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--check',action='store_true');a=p.parse_args()
    prepare(a.out,a.check)
