"use client";
import Link from "next/link";
import {useEffect, useState} from "react";
import {useRequireAuth} from "@/lib/auth";
import styles from "../page.module.css";
import {request} from "./api";
import EventProfiles from "./EventProfiles";
import EventJobs from "./EventJobs";

type System = {id: string; name: string; vendor: string; paused?: boolean};
function SystemEvents({systemId, employeeId, initialJob}: {systemId: string; employeeId: string; initialJob: string}) {
  const [stagedJob, setStagedJob] = useState(initialJob);
  return <><EventProfiles systemId={systemId} employeeId={employeeId} onStaged={setStagedJob} /><EventJobs systemId={systemId} stagedJob={stagedJob} /></>;
}
function Workspace({employeeId}: {employeeId: string}) {
  const [systems, setSystems] = useState<System[]>([]);
  const [systemId, setSystemId] = useState("");
  const [requestedJob, setRequestedJob] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    request("/system-map").then(data => {if (active) {
      setSystems(data.systems);
      const query = new URLSearchParams(window.location.search);
      const source = query.get("system"); const job = query.get("job") || "";
      if (source && data.systems.some((item: System) => item.id === source)) {setSystemId(source); setRequestedJob(job.length <= 120 ? job : "");}
    }}).catch(problem => {if (active) setError(problem.message);});
    return () => {active = false;};
  }, []);
  return <main className={styles.page}><Link href="/data-bridge">Back to System Map</Link>
    <p className={styles.kicker}>DEALER DATA BRIDGE</p><h1>ADF creation events</h1>
    <p>Review provider-scoped lead creation facts. Approve a mapping profile, test an authorized file, then review each staged batch before activation. Existing lead values are preserved when linking history.</p>
    <p className={styles.notice}>Human approval required. No vendor writes or communication consent are created.</p>
    {error && <p role="alert" className={styles.error}>{error}</p>}
    <label>Event source system<select value={systemId} onChange={event => {setSystemId(event.target.value); setRequestedJob("");}}><option value="">Select a system</option>{systems.map(system => <option key={system.id} value={system.id}>{system.name} ({system.vendor}){system.paused ? " - paused" : ""}</option>)}</select></label>
    {!systems.length && !error && <p>Add a source in System Map if none is configured.</p>}
    {systemId && <SystemEvents key={systemId} systemId={systemId} employeeId={employeeId} initialJob={requestedJob} />}
  </main>;
}
export default function EventPage() {
  const session = useRequireAuth("ADMIN");
  return session ? <Workspace employeeId={session.employeeId} /> : <main className={styles.page}><p>Checking administrator access...</p></main>;
}
