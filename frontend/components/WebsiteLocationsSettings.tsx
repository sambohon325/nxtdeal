"use client";
import { WorkInput, WorkButton } from "./WorkspaceUi";

import { useEffect, useState } from "react";
import { getSession } from "@/lib/auth";
import { addLocation, getSystemConfig, type Location } from "@/lib/systemConfig";

export function WebsiteLocationsSettings() {
  const [locations, setLocations] = useState<Location[]>([]);
  const [name, setName] = useState("");
  const [address, setAddress] = useState("");
  const [busy, setBusy] = useState(false);
  const [ready, setReady] = useState(false);
  const [message, setMessage] = useState("");
  const [canManage, setCanManage] = useState(false);
  useEffect(() => {
    let active = true;
    setCanManage(["ADMIN", "OPERATIONS"].includes(getSession()?.role || ""));
    getSystemConfig().then(result => {
      if (active) { setLocations(result.locations); setReady(true); }
    }).catch(error => { if (active) setMessage(error.message); });
    return () => { active = false; };
  }, []);
  async function saveLocation() {
    if (!name.trim() || busy || !ready) return;
    if (locations.some(location => location.name.toLowerCase() === name.trim().toLowerCase())) {
      setMessage("This location already exists. Manage its details in Administration.");
      return;
    }
    setBusy(true);
    try {
      const result = await addLocation(name.trim(), address.trim());
      setLocations(result.locations);
      setName(""); setAddress("");
      setMessage("Location added to your dealership.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Location could not be added.");
    } finally { setBusy(false); }
  }
  return <section aria-label="Dealership locations">
    <h3>Your locations</h3>
    <p>Shared with Administration. Vehicle locations come from your inventory records and appear on vehicle cards and detail pages.</p>
    <div className="grid gap-3 sm:grid-cols-2">
      {locations.map((location, index) => <div className="rounded-lg border border-zinc-500/30 p-3" key={`${location.name}-${index}`}><strong>{location.name}</strong><p>{location.address}</p>{location.is_primary && <small>Primary location</small>}</div>)}
    </div>
    {ready && !locations.length && <p>No dealership locations added yet.</p>}
    {canManage ? <fieldset disabled={busy || !ready} className="mt-4 grid gap-3 sm:grid-cols-2">
      <label>Location name<WorkInput value={name} onChange={e => setName(e.target.value)} placeholder="North location" /></label>
      <label>Address<WorkInput value={address} onChange={e => setAddress(e.target.value)} placeholder="Street, city, state and ZIP" /></label>
      <div><WorkButton type="button" onClick={saveLocation} disabled={busy || !ready || !name.trim()}>{busy ? "Adding…" : "Add dealership location"}</WorkButton></div>
      <small>Saved immediately to shared dealership settings.</small>
    </fieldset> : <p>An Admin or Operations teammate can add or update shared locations.</p>}
    {message && <p role="status">{message}</p>}
  </section>;
}
