"use client";
import { WorkField } from "./WorkField";

import { useEffect, useRef, useState } from "react";
import { WorkButton, WorkInput } from "./WorkspaceUi";
import "./HelpWorkspace.css";

import {
  decodeVin,
  searchVehicleByVin,
  type VinDecodeResult,
  type VinInventoryMatch,
  type VinDecodeResolved,
} from "@/lib/vinDecoder";

const FIELD_LABELS: Record<keyof VinDecodeResolved, string> = {
  year: "Year",
  make: "Make",
  model: "Model",
  trim: "Trim",
  engine: "Engine",
  transmission: "Transmission",
  drive_type: "Drive Type",
  fuel_type: "Fuel Type",
  body_style: "Body Style",
};

const BASIS_LABELS: Record<string, string> = {
  nhtsa_vpic_live: "Live (NHTSA)",
  wmi_offline: "Offline (WMI)",
  iso_3779_offline: "Offline (ISO 3779)",
  unavailable: "Not resolved",
};

function vehicleSummary(attrs: Record<string, unknown>): string {
  const year = attrs["Year"] ?? attrs["year"];
  const make = attrs["Make"] ?? attrs["make"];
  const model = attrs["Model"] ?? attrs["model"];
  const parts = [year, make, model].filter((p) => p !== undefined && p !== null && p !== "");
  return parts.length ? parts.join(" ") : "Vehicle";
}

export function VinLookupWidget({menuMode=false,onDismiss}:{menuMode?:boolean;onDismiss?:()=>void}={}) {
 const [open,setOpen]=useState(menuMode),[vin,setVin]=useState(""),[loading,setLoading]=useState(false),[error,setError]=useState(""),[inventoryError,setInventoryError]=useState("");
 const [result,setResult]=useState<VinDecodeResult|null>(null),[matches,setMatches]=useState<VinInventoryMatch[]>([]);const dialog=useRef<HTMLDialogElement>(null);
 useEffect(()=>{if(!open)return;const element=dialog.current;element?.showModal();return()=>element?.close();},[open]);
 function close(){setOpen(false);onDismiss?.();}
 async function lookup(){
 if(loading)return;const cleaned=vin.trim().toUpperCase();setError("");setInventoryError("");setResult(null);setMatches([]);
 if(!/^[A-HJ-NPR-Z0-9]{17}$/.test(cleaned)){setError("Enter a 17-character VIN using letters and numbers. VINs do not contain I, O or Q.");return;}
 setLoading(true);try{const [decoded,inventory]=await Promise.allSettled([decodeVin(cleaned,true),searchVehicleByVin(cleaned)]);
 if(decoded.status==="fulfilled")setResult(decoded.value);else setError(decoded.reason instanceof Error?decoded.reason.message:"VIN decoding could not complete. Try again.");
 if(inventory.status==="fulfilled")setMatches(inventory.value);else setInventoryError("Inventory could not be checked. Search Inventory before adding a vehicle.");
 }finally{setLoading(false);}}
 return <>{!menuMode&&<WorkButton onClick={()=>setOpen(true)}>VIN Lookup</WorkButton>}{open&&<dialog ref={dialog} className="nxt-utility-dialog nxt-workspace-content" aria-labelledby="vin-title" onCancel={e=>{e.preventDefault();close();}}><header><div><h2 id="vin-title">VIN Lookup</h2><p>Decode a vehicle and check your inventory.</p></div><WorkButton onClick={close}>Close</WorkButton></header>
 <form className="vin-form" onSubmit={e=>{e.preventDefault();void lookup();}}><WorkField label="Vehicle identification number (VIN)"><WorkInput autoFocus value={vin} disabled={loading} onChange={e=>{setVin(e.target.value.toUpperCase());setResult(null);setMatches([]);setError("");setInventoryError("");}} placeholder="17-character VIN" maxLength={17} aria-invalid={!!error} aria-describedby={error?"vin-error":undefined}/></WorkField><WorkButton type="submit" variant="primary" disabled={loading||!vin.trim()}>{loading?"Looking up…":"Look up VIN"}</WorkButton></form>
 {error&&<p id="vin-error" role="alert">{error}</p>}{inventoryError&&<p role="alert">{inventoryError}</p>}{loading&&<p role="status">Checking VIN details and inventory…</p>}
 {!result&&!loading&&!error&&<p>Paste the VIN from the vehicle or its paperwork. Results show the source of each field; unavailable information stays blank.</p>}
 {result&&<div className="vin-results"><section><h3>{result.vin}</h3><p>{result.valid_format?"Valid VIN format":"Invalid VIN format"}{result.check_digit_valid!==null&&` · ${result.check_digit_valid?"Check digit valid":"Check digit mismatch"}`}</p>{result.format_error&&<p role="alert">{result.format_error}</p>}</section>
 <section><h3>Inventory match</h3>{inventoryError?<p>Inventory status is unknown.</p>:matches.length?<ul>{matches.map(match=><li key={match.id}>{vehicleSummary(match.attributes)} · {match.id}</li>)}</ul>:<p>No matching vehicle was returned by your inventory search.</p>}</section>
 {result.valid_format&&<section><h3>Vehicle details</h3><dl className="vin-fields">{(Object.keys(FIELD_LABELS) as (keyof VinDecodeResolved)[]).map(key=><div key={key}><dt>{FIELD_LABELS[key]}</dt><dd>{result.resolved[key]||"Not available"}</dd><dd className="help-muted">{BASIS_LABELS[result.basis?.[key]??"unavailable"]}</dd></div>)}</dl></section>}
 {!!result.gaps?.length&&<p>{`${result.gaps.length} fields could not be resolved. Confirm missing details against the vehicle documentation.`}</p>}{result.live_error&&<p>Live provider: {result.live_error}</p>}</div>}</dialog>}</>;
}
