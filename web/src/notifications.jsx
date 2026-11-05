import React,{createContext,useContext,useEffect,useState,useRef} from 'react';
import {X,AlertCircle,CheckCircle2} from 'lucide-react';

export const NotificationTimeoutContext=createContext(8);
export function Banner({message,variant='notice',onDismiss}) {
 const seconds=useContext(NotificationTimeoutContext),bannerRef=useRef(null);
 const [dismissed,setDismissed]=useState(null),[paused,setPaused]=useState(false);
 const hidden=dismissed===message;
 useEffect(()=>{setDismissed(null);setPaused(Boolean(bannerRef.current?.matches(':hover')||bannerRef.current?.contains(document.activeElement)))},[message]);
 useEffect(()=>{
  if(!message||hidden||paused||!seconds)return;
  const timer=setTimeout(()=>{setDismissed(message);onDismiss?.()},seconds*1000);
  return()=>clearTimeout(timer);
 },[message,hidden,paused,seconds,onDismiss]);
 if(!message||hidden)return null;
 const close=()=>{setDismissed(message);setPaused(false);onDismiss?.()};
 return <div ref={bannerRef} className={`banner ${variant}`} role={variant==='error'?'alert':'status'} onMouseEnter={()=>setPaused(true)} onMouseLeave={()=>setPaused(false)} onFocusCapture={()=>setPaused(true)} onBlurCapture={e=>{if(!e.currentTarget.contains(e.relatedTarget))setPaused(false)}}>
  {variant==='error'?<AlertCircle size={18}/>:<CheckCircle2 size={18}/>}<span className="banner-message">{message}</span>
  <button type="button" className="banner-close" aria-label={variant==='error'?'Dismiss error':'Dismiss notification'} title={seconds?`Closes after ${seconds} seconds; pauses while hovered or focused`:'Close notification'} onClick={close}><X size={16}/></button>
 </div>;
}
