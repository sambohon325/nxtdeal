"use client";
import {useEffect,useState} from "react";
import {API_BASE} from "@/lib/api";
import {authHeaders} from "@/lib/auth";

// No click interception, toast, sound or modal. Only foreground, recently active
// staff sessions report a dwell; the server owns deduplication and all XP.
export function useEngagement(area:string, active=true, headers=authHeaders) {
  const [enabled,setEnabled]=useState(false);
  useEffect(()=>{
    if(!active)return;
    let cancelled=false, lastInput=Date.now(), visibleSince=Date.now(), busy=false, participating=false;
    const input=()=>{lastInput=Date.now();};
    const refresh=async(visit=false)=>{
      if(busy||document.visibilityState!=="visible")return;
      busy=true;
      try {
        const r=await fetch(`${API_BASE}/extras/${visit?"exploration":"journey"}`,{method:visit?"POST":"GET",headers:{...headers(),"Content-Type":"application/json"},...(visit?{body:JSON.stringify({area})}:{})});
        if(r.ok){const p=await r.json();if(!cancelled){participating=p.enabled===true;setEnabled(participating);window.dispatchEvent(new CustomEvent("nxtdeal-rewards-state",{detail:p.enabled===true}));if(visit)window.dispatchEvent(new Event("nxtdeal-progress"));}}
        else if(!cancelled)setEnabled(false);
      }catch{/* Rewards never block a work screen. */}finally{busy=false;}
    };
    const tick=()=>{void refresh(participating && Date.now()-lastInput<60000 && Date.now()-visibleSince>=20000 && area!=="Extras");};
    const focus=()=>{lastInput=Date.now();visibleSince=Date.now();void refresh();};
    void refresh();
    const dwell=window.setTimeout(tick,20000);
    const interval=window.setInterval(tick,60000);
    document.addEventListener("visibilitychange",focus);window.addEventListener("pointerdown",input,{passive:true});window.addEventListener("keydown",input);window.addEventListener("focus",focus);window.addEventListener("nxtdeal-rewards-policy",focus);
    return()=>{cancelled=true;clearTimeout(dwell);clearInterval(interval);document.removeEventListener("visibilitychange",focus);window.removeEventListener("pointerdown",input);window.removeEventListener("keydown",input);window.removeEventListener("focus",focus);window.removeEventListener("nxtdeal-rewards-policy",focus);};
  },[area,active,headers]);
  return enabled;
}
