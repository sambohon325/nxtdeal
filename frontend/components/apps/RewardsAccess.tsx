"use client";
import { useEffect, useState, type ReactNode } from "react";
import { customerRewards } from "@/lib/customerRewards";

export function RewardsAccess({children}:{children:ReactNode}) {
  const [status,setStatus]=useState<"loading"|"invitation"|"ready">("loading");
  const [code,setCode]=useState("");
  const [error,setError]=useState("");
  const [busy,setBusy]=useState(false);
  useEffect(()=>{
    let active=true;
    const expired=()=>setStatus("invitation");
    window.addEventListener("rewards-session-expired",expired);
    customerRewards("/session").then(()=>{if(active)setStatus("ready");}).catch(()=>{if(active)setStatus("invitation");});
    return()=>{active=false;window.removeEventListener("rewards-session-expired",expired);};
  },[]);
  if(status==="loading")return <p role="status" className="text-sm text-zinc-400">Checking your rewards access…</p>;
  if(status==="ready")return <div className="space-y-3"><div className="flex justify-end"><button className="text-xs text-zinc-400 underline" onClick={async()=>{try{await customerRewards("/logout",{});}catch(e){setError(e instanceof Error?e.message:"Sign out failed. Close this browser and ask your dealership to revoke access.");}finally{setStatus("invitation");}}}>Sign out of rewards</button></div>{children}</div>;
  return <form className="space-y-4 rounded-2xl border border-white/10 bg-white/5 p-5 text-white" onSubmit={async e=>{
    e.preventDefault();setBusy(true);setError("");
    try{await customerRewards("/session",{invitation:code.trim()});setCode("");setStatus("ready");}
    catch(e){setError(e instanceof Error?e.message:"Unable to sign in.");}finally{setBusy(false);}
  }}><h3 className="font-semibold">Your dealership rewards invitation</h3><p className="text-sm text-zinc-400">Ask your dealership for a one-time invitation after they verify your identity. It connects you to your own rewards and visits.</p><label className="block text-sm">Invitation code<input autoComplete="off" required minLength={32} value={code} onChange={e=>setCode(e.target.value)} className="mt-2 w-full rounded-lg border border-white/20 bg-transparent p-3"/></label>{error&&<p role="alert" className="text-sm text-red-400">{error}</p>}<button disabled={busy} className="rounded-lg bg-cyan-500 px-4 py-2 font-medium text-black disabled:opacity-40">{busy?"Signing in…":"Open my rewards"}</button><p className="text-xs text-zinc-500">Invitations expire after 24 hours and work once. Sessions expire after 12 hours.</p></form>;
}
