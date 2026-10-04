"""Local browser automation against the viewer, with no external service."""
import functools
import http.server
import json
import sys
import threading
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from common import ROOT, dump

handler=functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(ROOT/'web'))
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),handler)
threading.Thread(target=server.serve_forever,daemon=True).start()
try:
    with sync_playwright() as p:
        browser=p.chromium.launch();page=browser.new_page(viewport={'width':1440,'height':1000})
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('console',lambda message:errors.append(message.text) if message.type=='error' else None)
        page.goto(f'http://127.0.0.1:{server.server_port}/')
        page.locator('#position').filter(has_text='Event 1 /').wait_for()
        page.locator('#next').click();assert 'Event 2 /' in page.locator('#position').inner_text()
        page.locator('#previous').click();assert 'Event 1 /' in page.locator('#position').inner_text()
        page.locator('#seek').fill('15');page.locator('#seek').dispatch_event('input');assert 'Event 16 /' in page.locator('#position').inner_text()
        page.locator('#reset').click();page.locator('#speed').select_option('100');page.locator('#play').click()
        page.wait_for_function("document.querySelector('#position').textContent !== 'Event 1 / 2000'")
        page.locator('#play').click()
        page.locator('#scenario').select_option('lifecycle');page.locator('#event-title').filter(has_text='9007199254740993').wait_for()
        page.locator('#seek').fill('8');page.locator('#seek').dispatch_event('input');assert page.locator('#status').inner_text()=='empty'
        page.locator('#upload').set_input_files({'name':'invalid.json','mimeType':'application/json','buffer':b'{"bad":true}'})
        assert page.locator('#error').is_visible()
        page.locator('#upload').set_input_files(str(ROOT/'web/data/lifecycle.json'));assert not page.locator('#error').is_visible()
        for speed in ('1','10','100'): page.locator('#speed').select_option(speed)
        malformed=json.loads((ROOT/'web/data/lifecycle.json').read_text())
        malformed['frames'][0]['event']['quantity']='0'
        page.locator('#upload').set_input_files({'name':'zero-quantity.json','mimeType':'application/json','buffer':json.dumps(malformed).encode()})
        assert 'ADD fields' in page.locator('#error').inner_text()
        malformed=json.loads((ROOT/'web/data/lifecycle.json').read_text())
        malformed['frames'][0]['event']['order_id']+='\n'
        page.locator('#upload').set_input_files({'name':'invalid-id.json','mimeType':'application/json','buffer':json.dumps(malformed).encode()})
        assert 'identifiers' in page.locator('#error').inner_text()
        page.locator('#upload').set_input_files({'name':'large.json','mimeType':'application/json','buffer':b' '*(10*1024*1024+1)})
        assert '10 MB' in page.locator('#error').inner_text()
        original=json.loads((ROOT/'web/data/lifecycle.json').read_text(encoding='utf-8'))
        payload=json.dumps(original).encode()
        page.locator('#upload').set_input_files({'name':'exact-limit.json','mimeType':'application/json','buffer':payload+b' '*(10*1024*1024-len(payload))})
        expect(page.locator('#error')).to_be_hidden(timeout=15000)
        for field,value in [('input_sha256','bad'),('instrument','')]:
            malformed={**original,field:value}
            page.locator('#upload').set_input_files({'name':'bad-provenance.json','mimeType':'application/json','buffer':json.dumps(malformed).encode()})
            expect(page.locator('#error')).to_contain_text('provenance')
        malformed=json.loads(json.dumps(original));malformed['frames'][0]['statistics']['sequence']='999'
        page.locator('#upload').set_input_files({'name':'bad-statistics.json','mimeType':'application/json','buffer':json.dumps(malformed).encode()})
        expect(page.locator('#error')).to_contain_text('match')
        malformed=json.loads(json.dumps(original));malformed['frames'][2]['bids'].reverse()
        page.locator('#upload').set_input_files({'name':'unsorted-levels.json','mimeType':'application/json','buffer':json.dumps(malformed).encode()})
        expect(page.locator('#error')).to_contain_text('not sorted')
        frames=[]
        for i in range(10001):
            frame=json.loads(json.dumps(original['frames'][0]));frame['event']['sequence']=str(i+1);frame['statistics']['sequence']=str(i+1);frames.append(frame)
        for count,valid in [(10000,True),(10001,False)]:
            payload=json.dumps({**original,'frames':frames[:count]},separators=(',',':')).encode()
            assert len(payload)<10*1024*1024
            page.locator('#upload').set_input_files({'name':'frame-boundary.json','mimeType':'application/json','buffer':payload})
            if valid:
                expect(page.locator('#error')).to_be_hidden(timeout=15000)
                expect(page.locator('#position')).to_contain_text('Event 1 / 10000')
            else:expect(page.locator('#error')).to_contain_text('10,000 frames')
        safe={**original,'engine_commit':'<img src=x onerror=alert(1)>'}
        page.locator('#upload').set_input_files({'name':'text-only.json','mimeType':'application/json','buffer':json.dumps(safe).encode()})
        expect(page.locator('#provenance')).to_contain_text(safe['engine_commit'])
        assert page.locator('#provenance img').count()==0
        page.locator('#scenario').select_option('balanced');page.locator('#position').filter(has_text='Event 1 / 2000').wait_for()
        page.locator('#seek').fill('150');page.locator('#seek').dispatch_event('input')
        (ROOT/'results/browser').mkdir(parents=True,exist_ok=True)
        page.screenshot(path=str(ROOT/'results/browser/desktop.png'),full_page=True)
        page.set_viewport_size({'width':390,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        page.screenshot(path=str(ROOT/'results/browser/mobile.png'),full_page=True)
        page.goto(f'http://127.0.0.1:{server.server_port}/benchmarks.html');assert page.locator('h1').count()==1
        assert not errors,errors
        browser.close();dump(ROOT/'results/browser/verification.json',{'complete':True,'browser':'Chromium','console_errors':errors,'desktop':[1440,1000],'mobile':[390,844]})
        print('Browser interactions passed on desktop and mobile layouts')
finally:server.shutdown();server.server_close()
