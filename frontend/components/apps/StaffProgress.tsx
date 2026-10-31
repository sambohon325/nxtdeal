"use client";

import { useCallback, useEffect, useState } from "react";
import { API_BASE } from "@/lib/api";
import { appAuthHeaders } from "@/lib/appAuth";
import { AppProgress } from "@/components/extras/AppProgress";
import styles from "@/components/lab/DealershipLab.module.css";

// Uses the app's resolved tenant and staff token, without transferring a session
// to another origin or introducing a separate reward profile.
export function StaffProgress() {
  const [profile, setProfile] = useState<{level: number; xp: number; enabled?:boolean} | null>(null);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    const response = await fetch(`${API_BASE}/extras/progress`, {headers: appAuthHeaders()});
    if (!response.ok) throw new Error("Staff progress is unavailable. Check your sign-in and try again.");
    setProfile(await response.json());
    setError("");
  }, []);
  useEffect(() => { load().catch(e => setError(e.message)); }, [load]);
  if(profile?.enabled===false)return null;
  return <section className={`${styles.shell} ${styles.panel} ${styles.staffProgress}`} aria-label="Staff learning progress">
    <h2>Progress &amp; rewards</h2>
    {error && <p role="alert">{error} <button onClick={() => load().catch(e => setError(e.message))}>Retry</button></p>}
    {profile ? <>
      <p>Level {profile.level} · {profile.xp.toLocaleString()} XP</p>
      <p>Shared with your NXTDeal staff profile. Collection, cosmetics and Forecourt Legends are in the main workspace’s Extras.</p>
      <AppProgress onEarned={load} headers={appAuthHeaders}/>
    </> : !error && <p role="status">Loading your progress…</p>}
  </section>;
}
