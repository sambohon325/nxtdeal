"use client";
import { LoyaltyConnections } from "@/components/LoyaltyConnections";
import { useEffect, useState } from "react";
import { loyaltyRequest, memberPath, type ProgramMember } from "@/lib/loyaltyProgram";

export function CustomerLoyaltyPanel({customerId}:{customerId:string}) {
  const [state,setState]=useState<{id:string;member?:ProgramMember;error?:string}>({id:""});
  useEffect(()=>{let active=true;loyaltyRequest<ProgramMember>(memberPath(customerId)).then(member=>{if(active)setState({id:customerId,member});}).catch(error=>{if(active)setState({id:customerId,error:error.message});});return()=>{active=false;};},[customerId]);
  const current=state.id===customerId?state:undefined;
  return <section className="rounded-lg border border-current/15 p-3"><h3 className="text-sm font-semibold">Loyalty &amp; Rewards</h3>{!current?<p className="mt-1 text-xs opacity-60">Loading membership…</p>:current.member?<><p className="mt-2 text-lg font-semibold">{current.member.available.toLocaleString()} available points</p><p className="text-xs opacity-60">{current.member.reserved.toLocaleString()} reserved · {current.member.status}</p><p className="mt-2 text-xs opacity-60">Manage rewards from Marketing → Loyalty &amp; Rewards.</p><details className="mt-3"><summary className="cursor-pointer text-sm">Visits and reward checkout</summary><LoyaltyConnections customerId={customerId} onChange={async()=>{setState({id:customerId,member:await loyaltyRequest<ProgramMember>(memberPath(customerId))});}}/></details></>:<p className="mt-2 text-xs opacity-60">{current.error}</p>}</section>;
}
