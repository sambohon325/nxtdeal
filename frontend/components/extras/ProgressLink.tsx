"use client";
import {useEffect,useState} from "react";
import {API_BASE} from "@/lib/api";
import {authHeaders} from "@/lib/auth";
export function ProgressLink({onTheme}:{onTheme:(theme:string)=>void}){
  const [score,setScore]=useState<{level:number;xp:number;enabled?:boolean}|null>(null);
  useEffect(()=>{let active=true;const load=()=>fetch(`${API_BASE}/extras/progress`,{headers:authHeaders()}).then(r=>r.ok?r.json():null).then(p=>{if(active){setScore(p);onTheme(p?.enabled===false?"glacier":p?.equipped?.skin||"glacier");}}).catch(()=>{if(active)setScore(null);});load();window.addEventListener("focus",load);window.addEventListener("nxtdeal-rewards-state",load);window.addEventListener("nxtdeal-progress",load);return()=>{active=false;window.removeEventListener("focus",load);window.removeEventListener("nxtdeal-rewards-state",load);window.removeEventListener("nxtdeal-progress",load);};},[onTheme]);
  if(!score || score.enabled===false)return null;
  return <a href="/extras" title="Learning progress and cosmetic rewards; not business performance">{score?`Level ${score.level} · ${score.xp.toLocaleString()} XP`:"Progress & rewards"}</a>;
}
