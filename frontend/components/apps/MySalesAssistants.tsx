"use client";
import { useEffect, useState } from "react";
import { personalRequest, type PersonalRecord } from "@/lib/mysalesPersonal";
import { MySalesIcon } from "./MySalesIcon";
import styles from "./MySalesPersonal.module.css";

type Connection = { id: string; name: string; scopes: string; created: number };
type Status = {
  available: boolean;
  mcp_url: string | null;
  providers: { provider: string; name: string }[];
  connections: Connection[];
  activity: { action: string; at: number }[];
  scope_labels: Record<string, string>;
};
type Consent = {
  name: string;
  provider: string;
  scopes: Record<string, string>;
};
const actions: Record<string, string> = {
  connected: "Account connected",
  disconnected: "Account disconnected",
  mysales_summary: "Read follow-up counts",
  mysales_contacts: "Read personal contacts",
  mysales_followups: "Read personal follow-ups",
  mysales_create_followup: "Created or retrieved a follow-up",
  mysales_inventory_connection: "Read inventory connection",
  mysales_inventory: "Read shared retail inventory",
};

export function MySalesAssistants({
  view,
  tasks,
  recordsUpdated,
  onSetup,
}: {
  view: "coach" | "setup";
  tasks: PersonalRecord[];
  recordsUpdated: number | null;
  onSetup: () => void;
}) {
  const [status, setStatus] = useState<Status | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [message, setMessage] = useState("");
  const [request, setRequest] = useState<Consent | null>(null),
    [handle, setHandle] = useState(""),
    [approved, setApproved] = useState(false),
    [provider, setProvider] = useState("");
  async function load() {
    setStatus(await personalRequest<Status>("/assistants"));
  }
  useEffect(() => {
    let active = true;
    personalRequest<Status>("/assistants")
      .then((s) => {
        if (active) setStatus(s);
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    const h = new URLSearchParams(window.location.search).get("connect");
    if (h && /^[A-Za-z0-9_-]{43}$/.test(h)) {
      setHandle(h);
      personalRequest<Consent>(`/assistants/request/${encodeURIComponent(h)}`)
        .then((r) => {
          if (active) setRequest(r);
        })
        .catch((e) => {
          if (active) setError(e.message);
        });
    }
    return () => {
      active = false;
    };
  }, []);
  async function decide(value: boolean) {
    setBusy(true);
    setError("");
    try {
      const result = await personalRequest<{ redirect: string }>(
        `/assistants/request/${encodeURIComponent(handle)}`,
        "POST",
        { approve: value },
      );
      const target = new URL(result.redirect);
      if (target.protocol !== "https:" || target.username || target.password)
        throw Error("The assistant callback is not secure.");
      window.location.assign(result.redirect);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }
  async function remove(id: string) {
    setBusy(true);
    setError("");
    try {
      await personalRequest(`/assistants/${encodeURIComponent(id)}`, "DELETE");
      await load();
      setMessage(
        "Disconnected. This assistant can no longer access MySales. Information already shared remains subject to the assistant’s data controls.",
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function copy(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setMessage("Copied. Nothing has been sent to an assistant.");
    } catch {
      setError("Copy was unavailable. Select and copy the text below.");
    }
  }
  const prompts = [
    [
      "Plan my day",
      "Use MySales to review my open follow-ups. Help me prioritize them using the recorded due dates. Do not invent urgency, contact history or sales forecasts.",
    ],
    [
      "Prepare for a conversation",
      "Help me prepare for a customer conversation. Ask me which contact to review in MySales. Use only their recorded notes, and distinguish facts from suggestions.",
    ],
    [
      "Draft a follow-up",
      "Help me draft a friendly automotive sales follow-up. Ask which MySales contact and vehicle I mean. Do not claim inventory availability unless it has been verified. Show me the draft; do not send it.",
    ],
    [
      "Practice a conversation",
      "Role-play a customer asking about a vehicle. Ask me for the scenario first, then give constructive feedback. This is practice, not a real customer interaction.",
    ],
  ];
  return (
    <div className={styles.assistantStack}>
      <header className={styles.assistantHeading}>
        <MySalesIcon
          name={view === "coach" ? "coach" : "settings"}
          className={styles.assistantIcon}
        />
        <div>
          <h2>{view === "coach" ? "AI Coach" : "AI Setup"}</h2>
          <p>
            {view === "coach"
              ? "Prepare, practice and follow through with your assistant."
              : "Your assistant. Your account. Your permissions."}
          </p>
        </div>
      </header>
      {error && (
        <p role="alert" className={styles.error}>
          {error}{" "}
          <button
            disabled={busy}
            onClick={() => {
              setError("");
              load().catch((e) => setError(e.message));
            }}
          >
            Retry connection status
          </button>
        </p>
      )}
      {message && <p role="status">{message}</p>}
      {request && (
        <section
          className={styles.card}
          aria-labelledby="assistant-consent-title"
        >
          <h3 id="assistant-consent-title">Connect {request.name}?</h3>
          <p>
            You are authorizing access to this personal MySales account.
            Dealership staff records and private ChatGPT conversations are not
            included.
          </p>
          <ul>
            {Object.entries(request.scopes).map(([key, label]) => (
              <li key={key}>{label}</li>
            ))}
          </ul>
          <p>
            Selected information will be shared with {request.name}. You can
            disconnect in AI Setup. Messages cannot be sent through this
            connection.
          </p>
          <label className={styles.permissionCheck}>
            <input
              type="checkbox"
              checked={approved}
              onChange={(e) => setApproved(e.target.checked)}
            />
            I approve these permissions for {request.name}.
          </label>
          <button
            className={styles.primary}
            disabled={busy || !approved}
            onClick={() => decide(true)}
          >
            Allow connection
          </button>
          <button disabled={busy} onClick={() => decide(false)}>
            Decline
          </button>
        </section>
      )}
      {!status && !error && <p role="status">Checking your connections…</p>}
      {view === "coach" ? (
        <>
          <section className={styles.card}>
            <h3>Your starting point</h3>
            <p>
              {recordsUpdated === null
                ? "Your follow-ups have not loaded yet."
                : `${tasks.filter((t) => !t.done).length} open follow-ups in your personal workspace.`}
            </p>
            <p className={styles.muted}>
              {recordsUpdated !== null &&
                `Records loaded ${new Date(recordsUpdated).toLocaleString()}. `}
              Coaching happens in your connected assistant; no AI analysis has
              run on this screen.
            </p>
            <button onClick={onSetup}>
              <MySalesIcon name="link" className={styles.inlineIcon} />
              {status?.connections.length
                ? "Manage connected assistants"
                : "Set up an assistant"}
            </button>
          </section>
          <div className={styles.assistantStack}>
            {prompts.map(([title, prompt]) => (
              <section className={styles.card} key={title}>
                <h3>{title}</h3>
                <p>{prompt}</p>
                <button onClick={() => copy(prompt)}>Copy request</button>
              </section>
            ))}
          </div>
          <p className={styles.muted}>
            Paste a request into your assistant. Reading MySales records
            requires a working connection and your permission. No customer
            message is sent.
          </p>
        </>
      ) : (
        <>
          <section className={styles.card}>
            <h3>Connect your preferred assistant</h3>
            <p>
              Use your personal MySales sign-in when your assistant asks to
              connect. You do not need a dealership login or an API key.
            </p>
            {!status?.available && (
              <p role="status">
                Connections are not open yet. Provider registration and live
                connection checks are still required.
              </p>
            )}
            <div className={styles.assistantChoices}>
              {[
                ["chatgpt", "ChatGPT"],
                ["claude", "Claude"],
              ].map(([id, label]) => (
                <button
                  key={id}
                  aria-expanded={provider === id}
                  onClick={() => setProvider(provider === id ? "" : id)}
                >
                  <MySalesIcon name="coach" className={styles.inlineIcon} />
                  {label}
                  <small>
                    {status?.available &&
                    status.providers.some((p) => p.provider === id)
                      ? "Setup instructions"
                      : "Not available yet"}
                  </small>
                </button>
              ))}
            </div>
            {provider && (
              <div>
                <h4>{provider === "chatgpt" ? "ChatGPT" : "Claude"} setup</h4>
                <ol>
                  <li>
                    Open your assistant’s app or connector settings. Custom
                    connector setup may require its website and an eligible
                    account.
                  </li>
                  <li>Add the MySales MCP address below when available.</li>
                  <li>Sign in to MySales and review the exact permissions.</li>
                  <li>
                    Return here to check the linked account and connection
                    activity.
                  </li>
                </ol>
                {status?.mcp_url &&
                status.providers.some((p) => p.provider === provider) ? (
                  <>
                    <code className={styles.endpoint}>{status.mcp_url}</code>
                    <button onClick={() => copy(status.mcp_url!)}>
                      Copy connection address
                    </button>
                  </>
                ) : (
                  <p>
                    The connection address will appear after this provider is
                    configured.
                  </p>
                )}
              </div>
            )}
          </section>
          <section className={styles.card}>
            <h3>Connected accounts</h3>
            {status && !status.connections.length && (
              <p>No assistants connected.</p>
            )}
            {status?.connections.map((c) => (
              <article key={c.id}>
                <h4>{c.name}</h4>
                <p>Linked {new Date(c.created * 1000).toLocaleDateString()}</p>
                <ul>
                  {c.scopes.split(" ").map((s) => (
                    <li key={s}>{status.scope_labels[s] || s}</li>
                  ))}
                </ul>
                <button disabled={busy} onClick={() => remove(c.id)}>
                  Disconnect {c.name}
                </button>
              </article>
            ))}
          </section>
          <section className={styles.card}>
            <h3>Recent connection activity</h3>
            {status && !status.activity.length && (
              <p>No recorded activity yet.</p>
            )}
            <ul>
              {status?.activity.map((a, i) => (
                <li key={i}>
                  {actions[a.action] || "Assistant action"} ·{" "}
                  {new Date(a.at * 1000).toLocaleString()}
                </li>
              ))}
            </ul>
            <p className={styles.muted}>
              Activity records action names and times, not the text of your
              customer notes or assistant conversations.
            </p>
          </section>
          <p className={styles.muted}>
            Disconnecting blocks future access. Your assistant controls any
            information you already shared with it. Customer email and SMS
            delivery remain disabled.
          </p>
        </>
      )}
    </div>
  );
}
