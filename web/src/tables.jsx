import React,{createContext,useContext,useEffect,useMemo,useRef,useState} from 'react';
import {ArrowUp,ArrowDown,ArrowUpDown,Columns3,GripVertical,ChevronUp,ChevronDown} from 'lucide-react';

export const TablePreferencesContext=createContext({tables:{},update:()=>{}});
const defaults={hidden_columns:[],column_order:[],sort_by:'created_at',sort_dir:'desc'};
export function useTableSettings(id) {
 const context=useContext(TablePreferencesContext);
 const settings=context.tables[id]||defaults;
 return [settings,patch=>context.update(id,{...settings,...patch})];
}
export function DataTable({id,label,columns,rows,serverSorted=false,busy=false,empty='No results',heading,actions}) {
 const [settings,update]=useTableSettings(id);
 const menuRef=useRef(null);
 const [dragged,setDragged]=useState(null);
 useEffect(()=>{
  const dismissOutside=e=>{const menu=menuRef.current;if(menu?.open&&!menu.contains(e.target))menu.open=false;};
  const dismissEscape=e=>{const menu=menuRef.current;if(e.key==='Escape'&&menu?.open){e.preventDefault();e.stopPropagation();menu.open=false;menu.querySelector('summary')?.focus({preventScroll:true});}};
  document.addEventListener('click',dismissOutside,true);
  document.addEventListener('keydown',dismissEscape,true);
  return()=>{document.removeEventListener('click',dismissOutside,true);document.removeEventListener('keydown',dismissEscape,true);};
 },[]);
 const hidden=settings.hidden_columns||[];
 const ordered=[...new Set([...(settings.column_order||[]),...columns.map(c=>c.key)])].map(key=>columns.find(c=>c.key===key)).filter(Boolean);
 const move=(key,target)=>{const order=ordered.map(c=>c.key);const from=order.indexOf(key),to=order.indexOf(target);if(from<0||to<0||from===to)return;order.splice(from,1);order.splice(to,0,key);update({column_order:order})};
 const visible=ordered.filter(c=>!hidden.includes(c.key));
 const sorted=useMemo(()=>{
  if(serverSorted)return rows;
  const column=columns.find(c=>c.key===settings.sort_by);
  if(!column?.value)return rows;
  return [...rows].sort((a,b)=>{
   const av=column.value(a),bv=column.value(b);
   const comparison=column.type==='number'?Number(av||0)-Number(bv||0):column.type==='date'?new Date(av||0).getTime()-new Date(bv||0).getTime():String(av??'').localeCompare(String(bv??''),undefined,{numeric:true,sensitivity:'base'});
   return (comparison||String(a.id).localeCompare(String(b.id)))*(settings.sort_dir==='asc'?1:-1);
  });
 },[rows,columns,serverSorted,settings.sort_by,settings.sort_dir]);
 const sort=column=>update({sort_by:column.key,sort_dir:settings.sort_by===column.key?(settings.sort_dir==='asc'?'desc':'asc'):(column.type==='date'?'desc':'asc')});
 return <div className="data-table" aria-label={label}><div className={`table-tools${heading?' panel-heading':''}`}>{heading&&<h2>{heading}</h2>}<div className="actions"><details ref={menuRef} className="column-menu"><summary><Columns3 size={14}/> Columns</summary><div role="group" aria-label={`Columns for ${label}`}><p className="helptext">Drag to reorder, or use the arrows.</p>{ordered.map((column,index)=><div className={`column-option${dragged===column.key?' dragging':''}`} key={column.key} draggable onDragStart={e=>{setDragged(column.key);e.dataTransfer.setData('text/plain',column.key);e.dataTransfer.effectAllowed='move'}} onDragOver={e=>{e.preventDefault();e.dataTransfer.dropEffect='move'}} onDrop={e=>{e.preventDefault();move(dragged||e.dataTransfer.getData('text/plain'),column.key);setDragged(null)}} onDragEnd={()=>setDragged(null)}><GripVertical size={14} aria-hidden="true"/><label><input type="checkbox" aria-label={`Show ${column.label} column`} checked={!hidden.includes(column.key)} disabled={visible.length===1&&!hidden.includes(column.key)} onChange={e=>update({hidden_columns:e.target.checked?hidden.filter(key=>key!==column.key):[...hidden,column.key]})}/>{column.label}</label><button type="button" className="ghost" aria-label={`Move ${column.label} column left`} disabled={index===0} onClick={()=>move(column.key,ordered[index-1].key)}><ChevronUp size={14}/></button><button type="button" className="ghost" aria-label={`Move ${column.label} column right`} disabled={index===ordered.length-1} onClick={()=>move(column.key,ordered[index+1].key)}><ChevronDown size={14}/></button></div>)}<button type="button" className="link" onClick={()=>update(defaults)}>Reset table</button></div></details>{actions}</div></div><div className="table-wrap"><table aria-label={label} aria-busy={busy}><thead><tr>{visible.map(column=>{
 const active=settings.sort_by===column.key;
 return <th key={column.key} aria-sort={column.value?(active?(settings.sort_dir==='asc'?'ascending':'descending'):'none'):undefined}>{column.value?<button type="button" className="column-sort" onClick={()=>sort(column)}>{column.label}{active?(settings.sort_dir==='asc'?<ArrowUp size={13}/>:<ArrowDown size={13}/>):<ArrowUpDown size={13}/>}</button>:column.label}</th>;
 })}</tr></thead><tbody>{sorted.map(row=><tr key={row.id}>{visible.map(column=><td key={column.key} className={column.className}>{column.render?column.render(row):column.value?.(row)}</td>)}</tr>)}{!rows.length&&<tr><td colSpan={Math.max(1,visible.length)} className="empty">{empty}</td></tr>}</tbody></table></div></div>;
}
