"""Inspect the monochrome viewer, interactions, downloads and responsive layouts."""
import functools
import hashlib
import http.server
import json
import sys
import threading
from pathlib import Path
from playwright.sync_api import sync_playwright
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from common import ROOT, dump

out=ROOT/'results/visual-audit';out.mkdir(parents=True,exist_ok=True)
handler=functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(ROOT/'web'))
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),handler)
threading.Thread(target=server.serve_forever,daemon=True).start()
checks=[];errors=[];screens=[];palettes={}
base=f'http://127.0.0.1:{server.server_port}'

def palette(page,label):
    colors=page.evaluate("""() => {
      const values=new Set();
      for(const element of document.querySelectorAll('*')) {
        if(!element.getClientRects().length)continue;
        for(const pseudo of [null,'::before','::after']) {
          const style=getComputedStyle(element,pseudo);
          for(const key of ['color','backgroundColor','borderTopColor','borderLeftColor','outlineColor','accentColor','fill','stroke']) {
            const value=style[key];if(value&&value.startsWith('rgb'))values.add(value);
          }
        }
      }
      return [...values].sort();
    }""")
    for value in colors:
        channels=value[value.index('(')+1:value.index(')')].split(',')
        rgb=[float(channel.strip()) for channel in channels[:3]]
        assert rgb[0]==rgb[1]==rgb[2],f'{label}: colored element {value}'
        assert rgb[0] in (0,255),f'{label}: unexpected palette color {value}'
    palettes[label]=colors

def capture(page,label,full=True):
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'),label+' overflows'
    assert page.evaluate("getComputedStyle(document.body).backgroundColor === 'rgb(255, 255, 255)' && getComputedStyle(document.body).color === 'rgb(0, 0, 0)'"),label+' theme polarity'
    palette(page,label)
    page.screenshot(path=str(out/(label+'.png')),full_page=full and page.evaluate('document.documentElement.scrollHeight')<14000)
    screens.append(label+'.png')

try:
    with sync_playwright() as p:
        browser=p.chromium.launch();page=browser.new_page(viewport={'width':1440,'height':1000})
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('console',lambda message:errors.append(message.text) if message.type=='error' else None)
        page.goto(base+'/');page.locator('#position').filter(has_text='Event 1 / 2000').wait_for()
        assert page.locator('#depth circle').count()==1
        capture(page,'desktop-initial')
        page.locator('#seek').fill('150');page.locator('#seek').dispatch_event('input')
        assert page.locator('#bids tr').count()==10 and page.locator('#asks tr').count()==10
        assert page.locator('#depth polyline').count()==2
        assert page.locator('#depth polyline').nth(0).get_attribute('stroke-dasharray')=='none'
        assert page.locator('#depth polyline').nth(1).get_attribute('stroke-dasharray')=='6 4'
        capture(page,'desktop-populated');checks.append('Top-ten book, solid bid/dashed ask depth and history charts')
        page.set_viewport_size({'width':390,'height':844});capture(page,'mobile-populated')
        page.set_viewport_size({'width':1440,'height':1000})
        page.locator('#scenario').select_option('cancellation')
        page.locator('#position').filter(has_text='Event 1 / 2000').wait_for()
        page.locator('#seek').fill('150');page.locator('#seek').dispatch_event('input')
        capture(page,'desktop-cancellation');checks.append('Cancellation-heavy scenario loads and renders saved C++ output')
        page.locator('#scenario').select_option('lifecycle')
        page.locator('#event-title').filter(has_text='9007199254740993').wait_for()
        fixture=json.loads((ROOT/'web/data/lifecycle.json').read_text(encoding='utf-8'))
        kinds=set();statuses=set();captured_types=set()
        for index,frame in enumerate(fixture['frames']):
            page.locator('#seek').fill(str(index));page.locator('#seek').dispatch_event('input')
            assert page.locator('#status').inner_text()==frame['analytics']['status']
            assert frame['event']['order_id'] in page.locator('#event-title').inner_text()
            kinds.add(frame['event']['type']);statuses.add(frame['analytics']['status'])
            if frame['event']['type'] not in captured_types:
                capture(page,'event-'+frame['event']['type'].lower())
                captured_types.add(frame['event']['type'])
            if frame['analytics']['status'] in ('locked','crossed','empty'):capture(page,'lifecycle-'+frame['analytics']['status'])
        assert kinds=={'ADD','CANCEL','DELETE','EXECUTE','REPLACE'}
        assert statuses=={'normal','one-sided','locked','crossed','empty'}
        checks.append('All five event types and all five book statuses, including exact large IDs')
        page.locator('#reset').click();assert 'Event 1 / 9' in page.locator('#position').inner_text()
        page.locator('#next').click();page.locator('#previous').click()
        page.locator('#play').focus();assert page.evaluate("document.activeElement.id==='play'")
        page.keyboard.press('Space');assert page.locator('#play').inner_text()=='Pause'
        page.keyboard.press('Space');assert page.locator('#play').inner_text()=='Play'
        for speed in ('1','10','100'):
            page.locator('#speed').select_option(speed);page.locator('#play').click()
            page.wait_for_function("document.querySelector('#position').textContent !== 'Event 1 / 9'",timeout=5000)
            page.locator('#play').click();page.locator('#reset').click()
        checks.append('Keyboard play/pause, all playback rates, reset, previous/next and seeking')
        input_response=page.request.get(base+'/'+page.locator('#download-input').get_attribute('href'))
        manifest_response=page.request.get(base+'/'+page.locator('#download-manifest').get_attribute('href'))
        trace_response=page.request.get(base+'/'+page.locator('#download-trace').get_attribute('href'))
        assert input_response.ok and manifest_response.ok and trace_response.ok
        assert hashlib.sha256(input_response.body()).hexdigest()==manifest_response.json()['sha256']==trace_response.json()['input_sha256']
        checks.append('Scenario CSV, manifest and C++ trace downloads have matching checksums')
        page.locator('#upload').set_input_files(str(ROOT/'web/data/lifecycle.json'))
        assert not page.locator('#error').is_visible()
        for label,content in [('malformed',{'bad':True}),('frame-limit',{**fixture,'frames':[fixture['frames'][0]]*10001})]:
            page.locator('#upload').set_input_files({'name':label+'.json','mimeType':'application/json','buffer':json.dumps(content).encode()})
            assert page.locator('#error').is_visible()
        capture(page,'upload-error');checks.append('Valid uploads and malformed/10,001-frame rejection')
        page.goto(base+'/benchmarks.html');assert page.locator('h1').count()==1
        assert ('Preliminary smoke run' in page.inner_text('main')) == (json.loads((ROOT/'web/evidence/environment.json').read_text())['suite']!='full')
        for link in page.locator('a[href]').all():
            href=link.get_attribute('href')
            if href and href.startswith('evidence/'):
                response=page.request.get(base+'/'+href);assert response.ok and len(response.body())>0
        capture(page,'desktop-benchmarks')
        for title,label in [('Instrumented p99 update latency','benchmark-latency-chart'),
                            ('Populated process memory before event buffer','benchmark-memory-chart'),
                            ('Instrumented latency distribution','benchmark-latency-table'),
                            ('Analytics and export overhead','benchmark-overhead')]:
            page.get_by_role('heading',name=title,exact=True).evaluate("(element) => window.scrollTo({top:element.getBoundingClientRect().top + window.scrollY - 24,behavior:'instant'})")
            capture(page,label,full=False)
        page.evaluate("window.scrollTo({top:0,behavior:'instant'})")
        page.set_viewport_size({'width':390,'height':844});capture(page,'mobile-benchmarks')
        assert page.locator('.chart-bar').count()>0
        assert page.locator('.report-table tbody tr').count()>0
        checks.append('Benchmark charts, comparison tables and downloadable measurement evidence')
        page.goto(base+'/verification.html');assert page.locator('h1').inner_text()=='Check the results.'
        for link in page.locator('a[download]').all():
            response=page.request.get(base+'/'+link.get_attribute('href'))
            assert response.ok and response.json()
        page.locator('details').first.locator('summary').click()
        assert page.locator('details').first.evaluate('(element) => element.open')
        capture(page,'mobile-evidence-expanded')
        page.locator('details').first.locator('summary').click()
        capture(page,'mobile-verification');page.set_viewport_size({'width':1440,'height':1000});capture(page,'desktop-verification')
        checks.append('Visible verification evidence for engine, fuzzing, coverage and reproduction')
        assert not errors,errors
        browser.close()
    dump(out/'summary.json',{'complete':True,'browser':'Chromium','checked_viewports':[[1440,1000],[390,844]],
                            'palette':'black and white; series distinguished by line pattern','computed_colors':palettes,
                            'checks':checks,'page_errors':errors,'screenshots':screens})
    print('Monochrome visual and interaction audit passed')
finally:server.shutdown();server.server_close()
