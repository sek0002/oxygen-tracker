import {pressureDelta, status, estimateLitres, validateEntry, textExport} from './model.js';
import {rpc, configured} from './store.js';
const $ = id => document.getElementById(id);
let token = sessionStorage.getItem('oxygen-session') || '', state = {events:[], cylinders:{}}, filter = 'all', submitting = false, entryBaseline = null, entryRequestId = '';
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num = n => new Intl.NumberFormat().format(n);
const date = d => d ? new Date(d).toLocaleString(undefined,{dateStyle:'medium',timeStyle:'short'}) : '—';
const signed = value => value < 0 ? '−'+num(Math.abs(value)) : value > 0 ? '+'+num(value) : '0';
const deltaLabel = e => pressureDelta(e) == null ? 'New baseline' : `Δ ${signed(pressureDelta(e))} bar · ${signed(-e.used)} L`;
const title = side => side === 'left' ? 'Left cylinder' : 'Right cylinder';
function toast(message) { $('toast').textContent=message; $('toast').hidden=false; setTimeout(()=> $('toast').hidden=true,4500); }
function lock(){token='';sessionStorage.removeItem('oxygen-session');state={events:[],cylinders:{}};$('app').hidden=true;$('login').hidden=false;$('pin').value='';$('pin').focus();}
async function refresh(){const next=await rpc('oxygen_state',{p_token:token});state=next;render();$('storage-label').textContent='Synced';}
function render(){
  $('cylinders').innerHTML=['left','right'].map(side=>{
    const c=state.cylinders[side], s=status(c?.pressure), scale=Math.max(c?.startingPressure || 200,125), level=c ? Math.min(100,c.pressure/scale*100) : 0;
    const labels={unknown:'Not set up',healthy:'Ready to use',warning:'Low pressure',critical:'Critical pressure'};
    return `<article class="cylinder-card ${s}" style="--level:${level}%"><div class="card-heading"><div><h3>${title(side)}</h3><small>G cylinder · ${c ? esc(c.serial || 'No ID recorded') : '—'}</small></div><span class="badge">${labels[s]}</span></div><div class="card-main"><div class="tank-wrap" aria-hidden="true"><div class="tank"><div class="tank-liquid"><div class="tank-fill"></div></div><div class="tank-threshold warning-mark" style="bottom:${100/scale*100}%"><span>100 bar</span></div><div class="tank-threshold critical-mark" style="bottom:${50/scale*100}%"><span>50 bar</span></div><div class="tank-label">O₂<small>OXYGEN · G</small></div><div class="tank-base"></div></div></div><div><div class="pressure-label">CURRENT PRESSURE</div><strong class="pressure">${c ? num(c.pressure) : '—'}<small>bar</small></strong><div class="gas">${c ? num(estimateLitres(c.pressure))+' L' : '—'}<small>Gas remaining</small></div></div></div>${s==='critical'||s==='warning' ? `<p class="alert-line" role="status">${s==='critical'?'Critical · below 50 bar':'Warning · below 100 bar'}</p>`:''}<div class="card-meta">Updated: ${date(c?.at)}<br>${c ? 'Installed: '+date(c.installedAt)+' · Start '+num(c.startingPressure)+' bar' : '—'}${c?.kind==='reading'?`<br><span class="last-delta">${deltaLabel(c)}</span>`:''}</div><div class="card-actions"><button class="primary" data-side="${side}" data-kind="${c?'reading':'initial'}" aria-label="${c?'Add reading':'Set up cylinder'}" title="${c?'Add reading':'Set up cylinder'}"><span class="action-icon" aria-hidden="true">＋</span><span class="action-text">${c?'Add reading':'Set up cylinder'}</span></button>${c?`<button class="secondary" data-side="${side}" data-kind="replacement" aria-label="Replace cylinder" title="Replace cylinder"><span class="action-icon" aria-hidden="true">↻</span><span class="action-text">Replace cylinder</span></button>`:''}</div></article>`;
  }).join('');
  const cylinders=Object.values(state.cylinders);
  $('total').innerHTML=(cylinders.length ? num(cylinders.reduce((sum,c)=>sum+estimateLitres(c.pressure),0)) : '—')+' <small>L</small>';
  for(const side of ['left','right']){
    const c=state.cylinders[side];
    const replaced=state.events.some(e=>e.side===side&&e.kind==='replacement');
    const changed=c?new Date(c.installedAt).toLocaleDateString(undefined,{day:'numeric',month:'short',year:'2-digit'}):'—';
    $('summary-'+side).innerHTML=`<div class="summary-current"><span>${side==='left'?'Left':'Right'}</span><strong class="summary-pressure ${status(c?.pressure)}" aria-label="Current pressure${c?' · '+(status(c.pressure)==='critical'?'Critical':status(c.pressure)==='warning'?'Warning':'Normal'):''}">${c?num(c.pressure):'—'} <small>bar</small></strong></div><span class="summary-start">Start: ${c?num(c.startingPressure):'—'} bar</span><span class="summary-change" aria-label="${c&&!replaced?'Initial setup':'Last change'}: ${esc(date(c?.installedAt))}" title="${c&&!replaced?'Initial setup':'Last change'}: ${esc(date(c?.installedAt))}">${esc(changed)}</span>`;
  }
  const events=state.events.filter(e=>filter==='all'||e.side===filter);
  $('event-count').textContent=events.length+' records';$('empty-history').hidden=events.length>0;
  $('history-body').innerHTML=[...events].reverse().map(e=>`<tr><td>${esc(date(e.at))}</td><td>${title(e.side)}</td><td>${({initial:'Initial setup',reading:'Session reading',replacement:'Cylinder replaced'})[e.kind]}</td><td>${e.previousPressure??'—'} → <b>${e.pressure} bar</b></td><td class="delta-cell">${pressureDelta(e)==null?'New baseline':`<b>Δ ${signed(pressureDelta(e))} bar</b><small>${signed(-e.used)} L</small>`}</td><td class="detail">${esc(e.notes||'—')}<small>${esc(e.operator||'No operator')} · ID: ${esc(e.serial||'Not recorded')}</small></td></tr>`).join('');
}
function openEntry(side,kind){
  $('entry-form').reset();$('entry-side').value=side;$('entry-kind').value=kind;$('dialog-side').textContent=title(side);$('entry-error').textContent='';
  $('dialog-title').textContent=({initial:'Set up cylinder',reading:'Record a session',replacement:'Replace cylinder'})[kind];
  $('replacement-fields').hidden=kind==='reading';
  const c=state.cylinders[side];entryBaseline=c;entryRequestId=crypto.randomUUID();
  $('operator').value=sessionStorage.getItem('oxygen-operator')||'';$('pressure').value='';
  $('save-entry').textContent=kind==='reading'?'Save reading':kind==='replacement'?'Confirm replacement':'Save starting reading';
  $('estimate').textContent=kind==='reading'?`Previous: ${c.pressure} bar · Δ — bar · — L`:'New baseline · Δ — bar · — L';
  $('entry-dialog').showModal();$('pressure').focus();
}
$('cylinders').addEventListener('click',e=>{const b=e.target.closest('[data-kind]');if(b)openEntry(b.dataset.side,b.dataset.kind);});
$('close-dialog').onclick=()=>{if(!submitting)$('entry-dialog').close();};
$('entry-dialog').addEventListener('cancel',e=>{if(submitting)e.preventDefault();});
$('pressure').addEventListener('input',()=>{
  const c=entryBaseline, value=$('pressure').value, p=Number(value);
  if($('entry-kind').value!=='reading')return;
  if(value==='' || !Number.isFinite(p) || p<0 || p>400){$('estimate').textContent=`Previous: ${c.pressure} bar · Δ — bar · — L`;return;}
  $('estimate').textContent=p>c.pressure?'Pressure increased. Use Replace cylinder for a new cylinder.':deltaLabel({kind:'reading',previousPressure:c.pressure,pressure:p,used:estimateLitres(c.pressure-p)});
});
$('entry-form').addEventListener('submit',async e=>{
  e.preventDefault();if(submitting)return;
  const side=$('entry-side').value,c=entryBaseline;
  const entry={side,kind:$('entry-kind').value,pressure:Number($('pressure').value),serial:$('serial').value.trim(),operator:$('operator').value.trim(),notes:$('notes').value.trim()};
  try{validateEntry(entry,c);submitting=true;$('save-entry').disabled=true;$('entry-error').textContent='';
    const result=await rpc('oxygen_record',{p_token:token,p_entry:entry,p_expected:c?.id||null,p_request_id:entryRequestId});
    state=result;render();sessionStorage.setItem('oxygen-operator',entry.operator);$('entry-dialog').close();toast('Saved · '+deltaLabel(state.cylinders[side]));
  }catch(err){$('entry-error').textContent=err.message;if(err.message.includes('changed')){await refresh().catch(()=>{});entryBaseline=state.cylinders[side];entryRequestId=crypto.randomUUID();$('pressure').dispatchEvent(new Event('input'));}}
  finally{submitting=false;$('save-entry').disabled=false;}
});
$('login-form').addEventListener('submit',async e=>{e.preventDefault();const button=e.submitter;button.disabled=true;$('login-error').textContent='';try{const result=await rpc('oxygen_login',{p_pin:$('pin').value});token=result.token;sessionStorage.setItem('oxygen-session',token);await refresh();$('login').hidden=true;$('app').hidden=false;$('pin').value='';}catch(err){$('login-error').textContent=err.message;}finally{button.disabled=false;}});
$('lock').onclick=async()=>{const previous=token;lock();await rpc('oxygen_logout',{p_token:previous}).catch(()=>{});};
document.querySelectorAll('[data-filter]').forEach(b=>b.onclick=()=>{filter=b.dataset.filter;document.querySelectorAll('[data-filter]').forEach(x=>x.classList.toggle('active',x===b));render();});
$('export').onclick=()=>{const blob=new Blob([textExport(state.events)],{type:'text/plain;charset=utf-8'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=`oxygen-history-${new Date().toISOString().slice(0,10)}.txt`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
if(!configured){$('login-error').textContent='Shared database setup is pending. The tracker will be ready once connected.';}
if(token)refresh().then(()=>{$('login').hidden=true;$('app').hidden=false;}).catch(err=>{lock();$('login-error').textContent=err.message;});
setInterval(()=>{if(token&&!document.hidden)refresh().catch(err=>{$('storage-label').textContent='Sync unavailable — '+err.message;});},15000);
