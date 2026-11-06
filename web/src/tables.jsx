import React,{createContext,useContext,useMemo} from 'react';
import {ArrowUp,ArrowDown,ArrowUpDown,Columns3} from 'lucide-react';

export const TablePreferencesContext=createContext({tables:{},update:()=>{}});
const defaults={hidden_columns:[],sort_by:'created_at',sort_dir:'desc'};
export function useTableSettings(id) {
 const context=useContext(TablePreferencesContext);
 const settings=context.tables[id]||defaults;
 return [settings,patch=>context.update(id,{...settings,...patch})];
}
export function DataTable({id,label,columns,rows,serverSorted=false,busy=false,empty='No results'}) {
 const [settings,update]=useTableSettings(id);
 const hidden=settings.hidden_columns||[];
 const visible=columns.filter(c=>!hidden.includes(c.key));
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
 return <div className="data-table" aria-label={label}><div className="table-tools"><details className="column-menu"><summary><Columns3 size={14}/> Columns</summary><div role="group" aria-label={`Columns for ${label}`}>{columns.map(column=><label key={column.key}><input type="checkbox" aria-label={`Show ${column.label} column`} checked={!hidden.includes(column.key)} disabled={visible.length===1&&!hidden.includes(column.key)} onChange={e=>update({hidden_columns:e.target.checked?hidden.filter(key=>key!==column.key):[...hidden,column.key]})}/>{column.label}</label>)}<button type="button" className="link" onClick={()=>update(defaults)}>Reset table</button></div></details></div><div className="table-wrap"><table aria-label={label} aria-busy={busy}><thead><tr>{visible.map(column=>{
 const active=settings.sort_by===column.key;
 return <th key={column.key} aria-sort={column.value?(active?(settings.sort_dir==='asc'?'ascending':'descending'):'none'):undefined}>{column.value?<button type="button" className="column-sort" onClick={()=>sort(column)}>{column.label}{active?(settings.sort_dir==='asc'?<ArrowUp size={13}/>:<ArrowDown size={13}/>):<ArrowUpDown size={13}/>}</button>:column.label}</th>;
 })}</tr></thead><tbody>{sorted.map(row=><tr key={row.id}>{visible.map(column=><td key={column.key} className={column.className}>{column.render?column.render(row):column.value?.(row)}</td>)}</tr>)}{!rows.length&&<tr><td colSpan={Math.max(1,visible.length)} className="empty">{empty}</td></tr>}</tbody></table></div></div>;
}
