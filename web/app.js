'use strict';
const $=id=>document.getElementById(id);
let trace=null,index=0,timer=null,scenarios=[],uploadUrl=null;
const NS='http://www.w3.org/2000/svg';
function svgNode(name,attrs){const n=document.createElementNS(NS,name);for(const [k,v] of Object.entries(attrs))n.setAttribute(k,String(v));return n;}
function stop(){if(timer)clearInterval(timer);timer=null;$('play').textContent='Play';}
function decimal(value){return typeof value==='string' && value.length<=20 && value===value.trim() && /^(0|[1-9]\d*)$/.test(value) && BigInt(value)<=18446744073709551615n;}
function validate(t){
  if(t.schema_version!==1 || t.synthetic!==true || !Number.isFinite(t.tick_size) || t.tick_size<=0 || !Array.isArray(t.frames) || !t.frames.length || t.frames.length>10000)throw Error('Expected a version 1 synthetic trace with 1–10,000 frames and a positive tick size.');
  if(typeof t.instrument!=='string'||!t.instrument.trim()||typeof t.engine_commit!=='string'||typeof t.input_sha256!=='string'||!/^[0-9a-f]{64}$/.test(t.input_sha256))throw Error('Missing or invalid trace provenance.');
  let previous=-1n,previousTime=0n;
  for(const f of t.frames){
    if(!f.event || !decimal(f.event.sequence) || !decimal(f.event.order_id) || !decimal(f.event.timestamp_ns) || BigInt(f.event.sequence)<=previous)throw Error('Invalid event identifiers or sequence.');
    previous=BigInt(f.event.sequence);
    if(BigInt(f.event.timestamp_ns)<previousTime)throw Error('Event timestamps must not decrease.');
    previousTime=BigInt(f.event.timestamp_ns);
    if(!['ADD','CANCEL','DELETE','EXECUTE','REPLACE'].includes(f.event.type))throw Error('Unknown event type.');
    const e=f.event,positive=v=>decimal(v)&&BigInt(v)>0n,priceTick=v=>positive(v)&&BigInt(v)<=9223372036854775807n;
    if(e.type==='ADD' && (!['B','A'].includes(e.side)||!priceTick(e.price_ticks)||!positive(e.quantity)||e.new_order_id!==null))throw Error('Invalid ADD fields.');
    if(e.type==='REPLACE' && (e.side!==null||!priceTick(e.price_ticks)||!positive(e.quantity)||!decimal(e.new_order_id)||e.new_order_id===e.order_id))throw Error('Invalid REPLACE fields.');
    if(['CANCEL','EXECUTE'].includes(e.type) && (e.side!==null||e.price_ticks!==null||!positive(e.quantity)||e.new_order_id!==null))throw Error('Invalid reduction fields.');
    if(e.type==='DELETE' && [e.side,e.price_ticks,e.quantity,e.new_order_id].some(v=>v!==null))throw Error('Invalid DELETE fields.');
    if(!f.analytics || !['empty','one-sided','normal','locked','crossed'].includes(f.analytics.status))throw Error('Missing or invalid analytics.');
    if(!f.statistics)throw Error('Missing frame statistics.');
    for(const key of ['sequence','timestamp_ns','active_orders','total_quantity','peak_live_orders','bid_levels','ask_levels','execution_volume','execution_notional'])if(!decimal(f.statistics[key]))throw Error('Invalid frame statistics.');
    if(f.statistics.sequence!==e.sequence||f.statistics.timestamp_ns!==e.timestamp_ns)throw Error('Frame statistics do not match the event.');
    if(!Array.isArray(f.statistics.event_counts)||f.statistics.event_counts.length!==5||f.statistics.event_counts.some(v=>!Number.isInteger(v)||v<0||v>=2**64))throw Error('Invalid event counters.');
    for(const key of ['spread','midpoint','imbalance','imbalance5','weighted_midpoint','vwap'])if(f.analytics[key]!==null && !Number.isFinite(f.analytics[key]))throw Error('Non-finite or missing analytics.');
    for(const key of ['bids','asks']){
      if(!Array.isArray(f[key]) || f[key].length>10)throw Error('Expected at most ten price levels per side.');
      for(const q of f[key])if(!priceTick(q.price_ticks)||!positive(q.quantity)||!positive(q.orders))throw Error('Invalid price level.');
      for(let i=1;i<f[key].length;i++)if(key==='bids'?BigInt(f[key][i-1].price_ticks)<=BigInt(f[key][i].price_ticks):BigInt(f[key][i-1].price_ticks)>=BigInt(f[key][i].price_ticks))throw Error('Price levels are not sorted.');
    }
  }
  return t;
}
function setTrace(t){stop();trace=validate(t);index=0;$('seek').max=String(trace.frames.length-1);$('error').hidden=true;render();}
function error(e){stop();$('error').textContent=e.message;$('error').hidden=false;}
function price(v){if(v==null)return 'N/A';if(typeof v==='string'&&BigInt(v)>9007199254740991n)return `${v} ticks`;return (Number(v)*trace.tick_size).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:6});}
function levels(id,rows){const body=$(id);body.replaceChildren();for(const q of rows){const tr=document.createElement('tr');for(const v of [price(q.price_ticks),q.quantity,q.orders]){const td=document.createElement('td');td.textContent=v;tr.append(td);}body.append(tr);}if(!rows.length){const tr=document.createElement('tr'),td=document.createElement('td');td.colSpan=3;td.textContent='No orders';tr.append(td);body.append(tr);}}
function lineChart(id,series,min=null,max=null){
  const svg=$(id);svg.replaceChildren();const height=id==='depth'?240:160,width=520,left=46,right=505,top=15,bottom=height-27;
  const values=series.flatMap(s=>s.values).filter(Number.isFinite);
  min=min??Math.min(0,...values);max=max??Math.max(1,...values);if(max===min)max=min+1;
  for(let k=0;k<3;k++){const y=top+(bottom-top)*k/2;svg.append(svgNode('line',{x1:left,x2:right,y1:y,y2:y,stroke:'#000000','stroke-dasharray':'2 6'}));const text=svgNode('text',{x:left-7,y:y+4,'text-anchor':'end'});const tick=max-(max-min)*k/2;text.textContent=tick.toFixed(id==='imbalance-chart'||!Number.isInteger(tick)?1:0);svg.append(text);}
  for(const s of series){let segments=[];let current=[];s.values.forEach((v,i)=>{if(v===null){if(current.length)segments.push(current);current=[];return;}current.push(`${left+(right-left)*i/Math.max(1,s.values.length-1)},${bottom-(v-min)/(max-min)*(bottom-top)}`);});if(current.length)segments.push(current);for(const pts of segments){svg.append(svgNode('polyline',{points:pts.join(' '),fill:'none',stroke:s.color,'stroke-width':2,'stroke-dasharray':s.dash||'none'}));if(pts.length===1){const [cx,cy]=pts[0].split(',');svg.append(svgNode('circle',{cx,cy,r:3,fill:s.color}));}}}
  const label=svgNode('text',{x:left,y:height-5});label.textContent=id==='depth'?'Best level → deeper levels':'First event → selected event';svg.append(label);
}
function render(){
  if(!trace)return;const f=trace.frames[index],e=f.event,a=f.analytics;
  $('seek').value=String(index);$('position').textContent=`Event ${index+1} / ${trace.frames.length}`;
  $('previous').disabled=index===0;$('next').disabled=index===trace.frames.length-1;
  $('bid').textContent=price(f.bids[0]?.price_ticks);$('ask').textContent=price(f.asks[0]?.price_ticks);
  $('spread').textContent=a.spread??'N/A';$('imbalance').textContent=a.imbalance===null?'N/A':a.imbalance.toFixed(3);$('status').textContent=a.status;
  levels('bids',f.bids);levels('asks',f.asks);
  const cumulative=qs=>{let sum=0;return qs.map(q=>sum+=Number(q.quantity));};
  lineChart('depth',[{values:cumulative(f.bids),color:'#000000'},{values:cumulative(f.asks),color:'#000000',dash:'6 4'}]);
  const history=trace.frames.slice(0,index+1);const sample=xs=>xs.filter((_,i)=>i%Math.max(1,Math.ceil(xs.length/500))===0 || i===xs.length-1);
  lineChart('spread-chart',[{values:sample(history.map(x=>x.analytics.spread)),color:'#000000'}]);
  lineChart('imbalance-chart',[{values:sample(history.map(x=>x.analytics.imbalance)),color:'#000000'}],-1,1);
  $('event-title').textContent=`${e.type} · Order ${e.order_id}`;
  const explanations={ADD:`Adds ${e.quantity} units on the ${e.side==='B'?'bid':'ask'} side at ${price(e.price_ticks)}.`,CANCEL:`Removes ${e.quantity} units from the outstanding order.`,DELETE:'Removes the entire outstanding order.',EXECUTE:`Records execution of ${e.quantity} units at the resting order price.`,REPLACE:`Replaces this order with ID ${e.new_order_id}, ${e.quantity} units at ${price(e.price_ticks)}.`};
  $('event-description').textContent=explanations[e.type];$('event-details').textContent=`Sequence ${e.sequence} · Synthetic timestamp ${e.timestamp_ns} ns`;
  $('provenance').textContent=`Engine: ${trace.engine_commit||'uncommitted'} · Input SHA-256: ${trace.input_sha256||'not supplied'}`;
}
async function choose(){try{const s=scenarios.find(s=>s.id===$('scenario').value);const r=await fetch(s.file);if(!r.ok)throw Error('Could not load scenario.');setTrace(await r.json());$('upload').value='';$('download-trace').href=s.file;$('download-input').href=`data/${s.id}.csv`;$('download-manifest').href=`data/${s.id}.manifest.json`;$('download-input').hidden=false;$('download-manifest').hidden=false;}catch(e){error(e);}}
$('play').onclick=()=>{if(timer){stop();return;}if(!trace)return;if(index===trace.frames.length-1)index=0;$('play').textContent='Pause';timer=setInterval(()=>{if(index<trace.frames.length-1){index++;render();}else stop();},1000/Number($('speed').value));};
$('speed').onchange=()=>{if(timer){stop();$('play').click();}};
$('next').onclick=()=>{stop();index=Math.min(index+1,trace.frames.length-1);render();};
$('previous').onclick=()=>{stop();index=Math.max(0,index-1);render();};
$('reset').onclick=()=>{stop();index=0;render();};$('seek').oninput=()=>{stop();index=Number($('seek').value);render();};$('scenario').onchange=choose;
$('upload').onchange=async()=>{try{const file=$('upload').files[0];if(!file)return;if(file.size>10*1024*1024)throw Error('Trace exceeds 10 MB.');const t=validate(JSON.parse(await file.text()));setTrace(t);if(uploadUrl)URL.revokeObjectURL(uploadUrl);uploadUrl=URL.createObjectURL(file);$('download-trace').href=uploadUrl;$('download-input').hidden=true;$('download-manifest').hidden=true;}catch(e){error(e);}};
(async()=>{try{const r=await fetch('data/scenarios.json');if(!r.ok)throw Error('Scenarios missing: run python tools/run.py demo.');scenarios=await r.json();for(const s of scenarios){const o=document.createElement('option');o.value=s.id;o.textContent=s.label;$('scenario').append(o);}await choose();}catch(e){error(e);}})();
