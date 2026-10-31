"use client";
import {useState} from 'react';
import {DealerEmailStudio} from '@/components/marketing/DealerEmailStudio';
import {JourneyPlans} from '@/components/marketing/JourneyPlans';
export function EmailJourneyLab(){const [journey,setJourney]=useState(false);return <main style={{background:'#0a1724',color:'#eef5fa',padding:32,minHeight:'100vh'}}><p>NXTDeal / Marketing · isolated synthetic preview</p><nav style={{display:'flex',gap:20,margin:'20px 0'}}><button onClick={()=>setJourney(false)}>Matching email designs</button><button onClick={()=>setJourney(true)}>Journey builder</button></nav>{journey?<JourneyPlans canEdit/>:<DealerEmailStudio canEdit/>}</main>}
