import {createContext,useEffect,useState,type ReactNode} from 'react';
import {api} from './api';
import type {LiveConnection} from './types';

export const LiveConnectionContext=createContext<LiveConnection|null>(null);
export function liveConnectionLabel(check:LiveConnection,at=Date.now()){
 if(check.expires_at&&at>=Date.parse(check.expires_at))return {status:'not_checked',text:'Check expired'};
 if(check.status==='connected')return {status:'connected',text:'Endpoint reachable'};
 if(check.status==='error')return {status:'error',text:'Connection issue'};
 if(check.status==='not_configured')return {status:'not_configured',text:'Not configured'};
 if(check.status==='unavailable')return {status:'not_checked',text:'Status unavailable'};
 return {status:'not_checked',text:'Checking…'};
}
export function LiveConnectionProvider({identity,refreshKey,children}:{identity:string|null;refreshKey:string;children:ReactNode}){
 const [value,setValue]=useState<LiveConnection|null>(null);
 useEffect(()=>{
  setValue(null);if(!identity)return;
  let active=true,pending=false;const controller=new AbortController();
  async function refresh(){
   if(!active||pending||document.visibilityState==='hidden')return;pending=true;setValue(old=>old?{...old}:null);
   try{const fresh=await api.liveConnection(controller.signal);if(active)setValue(fresh);}
   catch{if(active)setValue({status:'unavailable',model:'',checked_at:null,expires_at:null,message:'Connection status could not be refreshed.',check_kind:'status_transport',poll_interval_seconds:30});}
   finally{pending=false;}
  }
  void refresh();const timer=setInterval(()=>void refresh(),30000);
  const visible=()=>{if(document.visibilityState==='visible')void refresh();};document.addEventListener('visibilitychange',visible);
  return()=>{active=false;controller.abort();clearInterval(timer);document.removeEventListener('visibilitychange',visible);};
 },[identity,refreshKey]);
 return <LiveConnectionContext.Provider value={value}>{children}</LiveConnectionContext.Provider>;
}
