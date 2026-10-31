"use client";
import { WorkButton } from "./WorkspaceUi";
import {useEffect,useRef,useState} from 'react';
import {API_BASE} from '@/lib/api';
import type {Website} from '@/lib/websites';
type AnalyticsWindow=Window & {dataLayer?:unknown[];gtag?:(...args:unknown[])=>void;[key:`ga-disable-${string}`]:boolean};
const allowed=new Set(['home','main','inventory','payment-shop','financing','team','trade','service','promotions','contact','vehicle']);
export function WebsiteVisitorAnalytics({site,page='home'}:{site:Website;page?:string}){
 const ga=site.admin_settings?.google_analytics_id||'';
 const valid=/^G-[A-Z0-9]{4,20}$/.test(ga);
 const [consent,setConsent]=useState<'allow'|'decline'|null>(null),[preferences,setPreferences]=useState(false);
 const sendRef=useRef<(event:string,page:string)=>void>(()=>{});
 useEffect(()=>{try{const choice=sessionStorage.getItem(`nxt-analytics-choice-${site.id}`);if(choice==='allow'||choice==='decline')setConsent(choice)}catch{}},[site.id]);
 useEffect(()=>{
  if(navigator.doNotTrack==='1'||(navigator as Navigator&{globalPrivacyControl?:boolean}).globalPrivacyControl)return;
  const w=window as unknown as AnalyticsWindow;
  let fallback=crypto.randomUUID();
  const send=(event:string,section:string)=>{
   if(!allowed.has(section))return;
   let session=fallback;const key=`nxt-visit-${site.id}`;
   try{const old=JSON.parse(sessionStorage.getItem(key)||'null');if(old&&Date.now()-old.last<1800000)session=old.id;sessionStorage.setItem(key,JSON.stringify({id:session,last:Date.now()}));fallback=session}catch{}
   let source=new URLSearchParams(location.search).get('utm_source')||'';
   if(!source&&document.referrer){try{const host=new URL(document.referrer).hostname;if(host!==location.hostname)source=host}catch{}}
   const body={id:crypto.randomUUID(),session,event,page:section,source,device:innerWidth<600?'mobile':innerWidth<1024?'tablet':'desktop'};
   void fetch(`${API_BASE}/public/websites/${encodeURIComponent(site.id)}/events`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),keepalive:true}).catch(()=>{});
   if(consent==='allow'&&valid&&w.gtag)w.gtag('event',event==='page_view'?'page_view':event,{page_location:location.origin+location.pathname,page_title:section,page_referrer:'',send_to:ga});
  };
  sendRef.current=send;
  const listener=(e:Event)=>{const data=(e as CustomEvent).detail;if(data?.site===site.id)send(data.event,data.page)};
  window.addEventListener('nxt-website-activity',listener);
  return()=>{sendRef.current=()=>{};window.removeEventListener('nxt-website-activity',listener)};
 },[site.id,consent,ga,valid]);
 // One event per page transition; re-renders or consent changes do not count another visit.
 const seen=useRef('');
 useEffect(()=>{const key=site.id+':'+page;if(seen.current===key)return;seen.current=key;sendRef.current('page_view',allowed.has(page)?page:'home')},[site.id,page]);
 useEffect(()=>{
  if(!valid||consent!=='allow'||navigator.doNotTrack==='1'||(navigator as Navigator&{globalPrivacyControl?:boolean}).globalPrivacyControl)return;
  const w=window as unknown as AnalyticsWindow;w[`ga-disable-${ga}`]=false;w.dataLayer=w.dataLayer||[];w.gtag=w.gtag||function(){w.dataLayer!.push(arguments)};
  w.gtag('consent','default',{analytics_storage:'granted',ad_storage:'denied',ad_user_data:'denied',ad_personalization:'denied'});
  w.gtag('js',new Date());w.gtag('config',ga,{send_page_view:false,allow_google_signals:false,allow_ad_personalization_signals:false});
  w.gtag('event','page_view',{send_to:ga,page_location:location.origin+location.pathname,page_title:'Dealership website',page_referrer:''});
  const script=document.createElement('script');script.async=true;script.src=`https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(ga)}`;document.head.appendChild(script);
  return()=>{w.gtag?.('consent','update',{analytics_storage:'denied'});w[`ga-disable-${ga}`]=true;script.remove()};
 },[valid,ga,consent]);
 function choose(value:'allow'|'decline'){setConsent(value);setPreferences(false);try{sessionStorage.setItem(`nxt-analytics-choice-${site.id}`,value)}catch{}}
 if(!valid)return null;
 return <aside aria-label="Analytics preferences" style={{position:'fixed',bottom:16,left:16,zIndex:9999,maxWidth:360,padding:16,borderRadius:16,background:'#112b3a',color:'#f3f8fb',boxShadow:'0 8px 30px #0005',font:'13px/1.6 system-ui'}}>{consent&&!preferences?<WorkButton type="submit" onClick={()=>setPreferences(true)}>Analytics preferences</WorkButton>:<><strong>Help us improve your visit</strong><p>Allow optional Google Analytics to measure website usage? You can change this choice here.</p><div style={{display:'flex',gap:16,marginTop:12}}><WorkButton type="submit" onClick={()=>choose('decline')}>Decline</WorkButton><WorkButton type="submit" onClick={()=>choose('allow')}>Allow analytics</WorkButton></div></>}</aside>
}

