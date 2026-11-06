import React,{useEffect,useState} from 'react';
import {CheckCircle2,XCircle,LoaderCircle,X} from 'lucide-react';
import {DataTable,useTableSettings} from './tables.jsx';
import {Dialog,PageHeading,Field,ErrorMessage} from './ui.jsx';

export function IncomingView({api,routes,refresh,onDeliveries}) {
 const [table]=useTableSettings('incoming');
 const [route,setRoute]=useState(''),[reason,setReason]=useState(''),[search,setSearch]=useState(''),[page,setPage]=useState(1);
 const [data,setData]=useState({items:[],total:0}),[busy,setBusy]=useState(false),[error,setError]=useState('');
 useEffect(()=>{let active=true;setBusy(true);const q=new URLSearchParams({page:String(page),page_size:'25',sort_by:table.sort_by,sort_dir:table.sort_dir});for(const [key,value] of Object.entries({route_id:route,reason,search}))if(value)q.set(key,value);api(`/api/events?${q}`).then(d=>{if(active){setData(d);setError('')}}).catch(e=>{if(active)setError(e.message)}).finally(()=>{if(active)setBusy(false)});return()=>{active=false}},[api,route,reason,search,page,refresh,table.sort_by,table.sort_dir]);
 useEffect(()=>setPage(1),[table.sort_by,table.sort_dir]);
 const filter=(setter,value)=>{setter(value);setPage(1)};
 return <><PageHeading title="Incoming webhooks" description="Accepted events, including events that queued no deliveries."/><div className="history-filters"><Field label="Route"><select value={route} onChange={e=>filter(setRoute,e.target.value)}><option value="">All routes</option>{routes.map(r=><option key={r.id} value={r.id}>{r.name}</option>)}</select></Field><Field label="Routing result"><select value={reason} onChange={e=>filter(setReason,e.target.value)}><option value="">All results</option>{['queued','priority_below_minimum','no_destinations','no_active_destinations','legacy'].map(r=><option key={r} value={r}>{r.replaceAll('_',' ')}</option>)}</select></Field><Field label="Search events"><input type="search" value={search} maxLength={250} onChange={e=>filter(setSearch,e.target.value)}/></Field></div><ErrorMessage error={error}/><section className="panel" aria-busy={busy}><DataTable id="incoming" label="Incoming webhooks" rows={data.items} busy={busy} serverSorted empty="No matching incoming events" columns={[
 {key:'created_at',label:'Time',type:'date',value:e=>e.created_at,render:e=>new Date(e.created_at).toLocaleString()},
 {key:'title',label:'Event',value:e=>e.title},
 {key:'route',label:'Route',value:e=>e.route_name},
 {key:'routing',label:'Routing',value:e=>e.routing?.reason||'legacy',render:e=>(e.routing?.reason||'legacy').replaceAll('_',' ')},
 {key:'deliveries',label:'Deliveries',type:'number',value:e=>e.deliveries,render:e=>`${e.sent} sent / ${e.deliveries} total`},
 {key:'details',label:'Details',render:e=><><details><summary>Event details</summary><p className="event-message">{e.message}</p><p>Priority: {e.priority} · Tags: {(Array.isArray(e.tags)?e.tags:[]).join(', ')||'None'}</p><code>{e.id}</code><pre>{e.routing?JSON.stringify(e.routing,null,2):'Routing diagnostics were not recorded for this older event.'}</pre></details>{e.deliveries>0&&<button className="small-btn" onClick={()=>onDeliveries(e)}>View deliveries</button>}</>},
 ]}/><div className="pagination"><span>{data.total} events</span><div className="actions"><button className="secondary compact" disabled={busy||page===1} onClick={()=>setPage(page-1)}>Previous</button><span>Page {page}</span><button className="secondary compact" disabled={busy||page*25>=data.total} onClick={()=>setPage(page+1)}>Next</button></div></div></section></>;
}
export function AttemptDialog({id,api,onClose,onRetry}) {
 const [data,setData]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const load=()=>api(`/api/deliveries/${id}/attempts`).then(setData).catch(e=>setError(e.message));
 useEffect(()=>{void load()},[id]);
 const retry=async()=>{setBusy(true);setError('');try{await onRetry(id);await load()}catch(e){setError(e.message)}finally{setBusy(false)}};
 return <Dialog title="Delivery attempts" description={id} onClose={onClose} busy={busy}><ErrorMessage error={error}/>{data?<><p>{data.attempts} total attempt(s) · {data.status}{data.is_fallback?' · Fallback':''}</p><p className="helptext">Retry starts a new cycle of up to five attempts and preserves previous attempt history. Older deliveries may have an attempt count without detailed records. The latest 100 records are shown.</p><div className="attempt-list">{data.items.map(a=><section key={a.number}><strong>Attempt {a.number} · {a.status}</strong><p>{new Date(a.started_at).toLocaleString()}{a.finished_at?` → ${new Date(a.finished_at).toLocaleString()}`:''}</p>{a.error&&<p className="delivery-error">{a.error}</p>}</section>)}</div>{data.can_retry&&<button className="secondary" disabled={busy} onClick={retry}>Retry delivery</button>}</>:<p>Loading attempts…</p>}</Dialog>;
}
const stageLabels={configuration:'Configuration',transport:'Connection',credentials:'Bot authentication',destination:'Chat access'};
export function InlineDiagnostics({state,onDismiss}) {
 if(!state)return null;
 return <section className="inline-diagnostics" aria-label="Channel diagnostics" aria-busy={state.busy}><div className="diagnostics-heading"><strong>Diagnostics</strong><button type="button" className="ghost" onClick={onDismiss} aria-label="Dismiss diagnostics"><X size={14}/></button></div>{state.busy&&<p className="diagnostic-running" role="status"><LoaderCircle className="spin" size={17}/> Checking connection…</p>}<ErrorMessage error={state.error}/>{state.result&&<ul className="diagnostic-steps">{state.result.steps.filter(s=>s.name!=='permissions').map(s=><li key={s.name} className={s.status==='passed'?'diagnostic-passed':'diagnostic-failed'}>{s.status==='passed'?<CheckCircle2 size={19} aria-label="Passed"/>:<XCircle size={19} aria-label="Failed"/>}<div><strong>{stageLabels[s.name]||s.name}</strong><p>{s.detail}</p></div></li>)}</ul>}</section>;
}
