"use client";
import "@/components/NxtGlass.css";
import {useState} from 'react';
import {BdcWorkspace} from '@/components/bdc/BdcWorkspace';
import type {Session} from '@/lib/auth';
export function Preview(){const [host,setHost]=useState<HTMLElement|null>(null);return <main data-nxt-glass data-theme="dark" style={{background:'#0c1726',color:'#eef5fa',minHeight:'100vh',padding:24}}><p>NXTDeal · isolated BDC test</p><div style={{display:'grid',gridTemplateColumns:'200px minmax(0,1fr)',gap:24}}><aside className="sidebar glass" style={{position:"relative",width:"auto",height:"auto"}} ref={setHost}/><BdcWorkspace navigationHost={host} theme="dark" session={{employeeId:'EMP-EMAIL-QA',role:'MARKETING'} as Session} items={['marketing:crm','marketing:campaigns','marketing:email_sms','marketing:analytics','sales:workflows'].map(key=>({key,label:key,description:''}))} initialItem="campaigns" onOpenEntity={()=>{}} onOpenBrand={()=>{window.location.href='/email-studio-lab'}} onDraftOpenChange={()=>{}} onSavingChange={()=>{}}/></div></main>}

