import {useState,useRef,useCallback,useEffect} from 'react';

export const monitoringPeriods=[['5m','5 minutes'],['15m','15 minutes'],['30m','30 minutes'],['1h','1 hour'],['24h','1 day'],['7d','7 days'],['30d','30 days']];
export const periodLabel=value=>monitoringPeriods.find(([key])=>key===value)?.[1]||'30 days';
export const defaultFilters={status:'',channel_id:'',route_id:'',event_id:'',from:'',to:'',search:'',tag:'',period:''};
export const defaultPreferences={tables:{},theme:'light',refresh_interval_seconds:15,delivery_filters:defaultFilters,route_tag_filter:'',page_size:50,list_search:'',dashboard_period:'30d',api_token_tag_filter:'',notification_timeout_seconds:8};
const pendingKey=owner=>`relayix-pending-preferences:${owner}`;
const pendingRead=owner=>{try{return JSON.parse(localStorage.getItem(pendingKey(owner))||'null')}catch{return null}};
const pendingWrite=(owner,value)=>{try{if(value)localStorage.setItem(pendingKey(owner),JSON.stringify(value));else localStorage.removeItem(pendingKey(owner))}catch{}};
const normalizeTables=tables=>Object.fromEntries(Object.entries(tables||{}).map(([id,settings])=>{
 if(!['deliveries','dashboard_deliveries'].includes(id))return [id,settings];
 const hidden=[...new Set((settings.hidden_columns||[]).filter(key=>!['attempts','status'].includes(key)).map(key=>key==='channel'?'recipients':key))];
 const removed=['attempts','status'].includes(settings.sort_by);
 return [id,{...settings,hidden_columns:hidden.length>=6?[]:hidden,sort_by:removed?'created_at':settings.sort_by==='channel'?'recipients':settings.sort_by,sort_dir:removed?'desc':settings.sort_dir}];
}));
const normalized=value=>({...defaultPreferences,...value,tables:normalizeTables(value?.tables),delivery_filters:{...defaultFilters,...value?.delivery_filters}});

export function usePreferences(save) {
 const [preferences,setPreferences]=useState(()=>normalized({theme:localStorage.getItem('relayix-theme')==='dark'?'dark':'light'}));
 const [status,setStatus]=useState('saved'),[error,setError]=useState('');
 const valueRef=useRef(preferences),ownerRef=useRef(null),dirty=useRef(false),revision=useRef(0),timer=useRef(null),queue=useRef(Promise.resolve()),saveRef=useRef(save);
 saveRef.current=save;
 const enqueue=useCallback(()=>{
  clearTimeout(timer.current);timer.current=null;
  const value=valueRef.current,version=revision.current,owner=ownerRef.current,writer=saveRef.current;
  if(!owner)return Promise.resolve();
  const task=queue.current.catch(()=>{}).then(async()=>{
   if(ownerRef.current!==owner)return;
   try{await writer(value);if(ownerRef.current===owner&&revision.current===version){dirty.current=false;pendingWrite(owner,null);setStatus('saved');setError('')}}
   catch(e){if(ownerRef.current===owner&&revision.current===version){setStatus('error');setError(`Could not save settings: ${e.message}`)}throw e}
  });
  queue.current=task;task.catch(()=>{});return task;
 },[]);
 const update=useCallback(patch=>{
  const next=normalized({...valueRef.current,...patch});if(JSON.stringify(next.delivery_filters)===JSON.stringify(valueRef.current.delivery_filters))next.delivery_filters=valueRef.current.delivery_filters;valueRef.current=next;revision.current++;setPreferences(next);setError('');
  if(!ownerRef.current){setStatus('saved');return}
  dirty.current=true;setStatus('saving');pendingWrite(ownerRef.current,next);enqueue();
 },[enqueue]);
 const load=useCallback((user,requestRevision)=>{
  const owner=user.id||`token:${user.username}`,changedOwner=ownerRef.current!==owner;
  if(changedOwner){clearTimeout(timer.current);timer.current=null;dirty.current=false;ownerRef.current=owner;setStatus('saved');setError('')}
  else if(dirty.current||(requestRevision!==undefined&&requestRevision!==revision.current))return;
  let next=normalized(user.preferences);
  const pending=changedOwner?pendingRead(owner):null;
  if(pending){
   const cached=normalized(pending);
   if(JSON.stringify(cached)!==JSON.stringify(next)){next=cached;dirty.current=true;revision.current++;setStatus('saving');timer.current=setTimeout(enqueue,0)}
   else pendingWrite(owner,null);
  }
  if(JSON.stringify(next.delivery_filters)===JSON.stringify(valueRef.current.delivery_filters))next.delivery_filters=valueRef.current.delivery_filters;
  if(JSON.stringify(next)!==JSON.stringify(valueRef.current)){valueRef.current=next;setPreferences(next)}
 },[enqueue]);
 const flush=useCallback(async()=>{if(timer.current||dirty.current){await enqueue()}else{await queue.current.catch(()=>{})}},[enqueue]);
 const reset=useCallback(()=>{clearTimeout(timer.current);timer.current=null;ownerRef.current=null;dirty.current=false;revision.current++;setStatus('saved');setError('')},[]);
 useEffect(()=>()=>clearTimeout(timer.current),[]);
 const readRevision=useCallback(()=>dirty.current?-1:revision.current,[]);
 return {preferences,update,load,flush,reset,status,error,revision,readRevision};
}
