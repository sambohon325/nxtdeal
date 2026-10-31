"use client";
import { useEffect, useState, useRef, type FormEvent } from "react";
import Link from "next/link";
import { MySalesIcon } from "./MySalesIcon";
import {
  personalToken,
  personalRequest,
  personalSignIn,
  personalSignOut,
  personalInventory,
  type PersonalAccount,
  type PersonalRecord,
  type InventoryConnection,
  type RetailVehicle,
} from "@/lib/mysalesPersonal";
import styles from "./MySalesPersonal.module.css";
import { MySalesPersonalPage } from "./MySalesPersonalPage";
import { MySalesAssistants } from "./MySalesAssistants";
import { MySalesEmail } from "./MySalesEmail";
const blank = {
  title: "",
  notes: "",
  email: "",
  phone: "",
  due: "",
  done: false,
  stage: "new",
};
const tabs = [
  ["today", "Today", "calendar"],
  ["contacts", "Contacts", "people"],
  ["inventory", "Inventory", "car"],
  ["more", "More", "settings"],
] as const;
export function MySalesPersonal() {
  const dialog = useRef<HTMLElement>(null);
  const [account, setAccount] = useState<PersonalAccount | null>(null),
    [loading, setLoading] = useState(true),
    [mode, setMode] = useState<"login" | "signup">("login");
  const [name, setName] = useState(""),
    [email, setEmail] = useState(""),
    [password, setPassword] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const [tab, setTab] = useState("today"),
    [recordsUpdated, setRecordsUpdated] = useState<number | null>(null),
    [contacts, setContacts] = useState<PersonalRecord[]>([]),
    [tasks, setTasks] = useState<PersonalRecord[]>([]),
    [query, setQuery] = useState("");
  const [editing, setEditing] = useState<{
    kind: "contacts" | "tasks";
    id?: string;
    data: typeof blank;
  } | null>(null);
  const [connection, setConnection] = useState<InventoryConnection | null>(
      null,
    ),
    [dealer, setDealer] = useState(""),
    [vehicles, setVehicles] = useState<RetailVehicle[]>([]),
    [asOf, setAsOf] = useState(""),
    [inventoryError, setInventoryError] = useState("");
  function clearWorkspace() {
    setRecordsUpdated(null);
    setContacts([]);
    setTasks([]);
    setConnection(null);
    setVehicles([]);
    setAsOf("");
    setInventoryError("");
    setEditing(null);
    setQuery("");
    setDealer("");
    setTab("today");
  }
  useEffect(() => {
    const expired = () => {
      setAccount(null);
      clearWorkspace();
      setError("Your session ended. Sign in again.");
    };
    window.addEventListener("mysales-session-expired", expired);
    return () => window.removeEventListener("mysales-session-expired", expired);
  }, []);
  useEffect(() => {
    if (!account) return;
    const params = new URLSearchParams(window.location.search);
    if (params.has("connect") || params.get("view") === "setup")
      setTab("setup");
    else if (params.get("view") === "coach") setTab("coach");
  }, [account]);
  async function loadRecords() {
    const token = personalToken();
    const [c, t] = await Promise.all([
      personalRequest<{ items: PersonalRecord[] }>("/records/contacts"),
      personalRequest<{ items: PersonalRecord[] }>("/records/tasks"),
    ]);
    if (token === personalToken()) {
      setContacts(c.items);
      setTasks(t.items);
      setRecordsUpdated(Date.now());
    }
  }
  useEffect(() => {
    let active = true;
    if (!personalToken()) {
      setLoading(false);
      return;
    }
    personalRequest<PersonalAccount>("/me")
      .then((a) => {
        if (active) setAccount(a);
      })
      .catch((e) => {
        if (active) setError(e.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);
  useEffect(() => {
    if (!account) return;
    let active = true;
    loadRecords().catch((e) => {
      if (active) setError(e.message);
    });
    personalRequest<InventoryConnection | null>("/inventory-connection")
      .then((c) => {
        if (active) setConnection(c);
      })
      .catch((e) => {
        if (active) setInventoryError(e.message);
      });
    return () => {
      active = false;
    };
  }, [account]);
  useEffect(() => {
    if (!editing) return;
    const previous = document.activeElement as HTMLElement | null;
    const handler = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy) setEditing(null);
      if (event.key !== "Tab") return;
      const items = Array.from(
        dialog.current?.querySelectorAll<HTMLElement>(
          "button:not(:disabled),input,select,textarea,a[href]",
        ) || [],
      );
      const first = items[0],
        last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    };
    document.addEventListener("keydown", handler);
    return () => {
      document.removeEventListener("keydown", handler);
      previous?.focus();
    };
  }, [!!editing, busy]);
  async function login(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const signedIn = await personalSignIn(mode, { name, email, password });
      clearWorkspace();
      setAccount(signedIn);
      setPassword("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!editing) return;
    // Native date controls may commit their visible value only at submission.
    const submitted = editing.kind === "tasks"
      ? { ...editing.data, due: String(new FormData(e.currentTarget).get("due") ?? editing.data.due) }
      : editing.data;
    setBusy(true);
    setError("");
    try {
      await personalRequest(
        `/records/${editing.kind}${editing.id ? "/" + editing.id : ""}`,
        editing.id ? "PUT" : "POST",
        submitted,
      );
      await loadRecords();
      setEditing(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function toggle(task: PersonalRecord) {
    setBusy(true);
    try {
      await personalRequest("/records/tasks/" + task.id, "PUT", {
        ...task,
        done: !task.done,
      });
      await loadRecords();
      setError("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function sync(c = connection) {
    if (!c) return;
    setBusy(true);
    setInventoryError("");
    setVehicles([]);
    setAsOf("");
    try {
      const data = await personalInventory(c);
      setVehicles(data.items);
      setAsOf(data.as_of);
    } catch (e) {
      setInventoryError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function connect(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setInventoryError("");
    setVehicles([]);
    setAsOf("");
    try {
      const c = await personalRequest<InventoryConnection>(
        "/inventory-connection",
        "PUT",
        { dealership: dealer },
      );
      setConnection(c);
      await sync(c);
    } catch (e) {
      setInventoryError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function disconnect() {
    setBusy(true);
    try {
      await personalRequest("/inventory-connection", "DELETE");
      setConnection(null);
      setVehicles([]);
      setAsOf("");
      setInventoryError("");
    } catch (e) {
      setInventoryError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const visibleContacts = contacts.filter(contact =>
    `${contact.title} ${contact.email || ""} ${contact.phone || ""}`
      .toLowerCase().includes(query.trim().toLowerCase())
  );
  const now = new Date();
  const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
  const due = tasks.filter((t) => !t.done && (!t.due || t.due <= today));
  if (loading)
    return (
      <main className={styles.root}>
        <p role="status">Opening MySales…</p>
      </main>
    );
  if (!account)
    return (
      <main className={`${styles.root} ${styles.entry}`}>
        <div className={styles.login}>
          <Link href="/apps" className={styles.back}>
            ‹ All apps
          </Link>
          <MySalesIcon name="people" className={styles.heroIcon} />
          <p className={styles.eyebrow}>YOUR CAREER. YOUR WORKSPACE.</p>
          <h1>MySales</h1>
          <p>Your contacts, your follow-ups, wherever you sell.</p>
          <div className={styles.switcher}>
            <button
              type="button"
              aria-pressed={mode === "login"}
              onClick={() => {
                setMode("login");
                setError("");
              }}
            >
              Sign in
            </button>
            <button
              type="button"
              aria-pressed={mode === "signup"}
              onClick={() => {
                setMode("signup");
                setError("");
              }}
            >
              Create account
            </button>
          </div>
          <form onSubmit={login}>
            {mode === "signup" && (
              <label>
                Your name
                <input
                  required
                  autoComplete="name"
                  value={name}
                  maxLength={100}
                  onChange={(e) => setName(e.target.value)}
                />
              </label>
            )}
            <label>
              Email
              <input
                required
                type="email"
                autoComplete="username"
                value={email}
                maxLength={254}
                onChange={(e) => setEmail(e.target.value)}
              />
            </label>
            <label>
              Password
              <input
                required
                type="password"
                autoComplete={
                  mode === "signup" ? "new-password" : "current-password"
                }
                minLength={mode === "signup" ? 12 : 1}
                maxLength={256}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </label>
            {mode === "signup" && (
              <small>
                Use at least 12 characters. No dealership account required.
              </small>
            )}
            {error && (
              <p role="alert" className={styles.error}>
                {error}
              </p>
            )}
            <button className={styles.primary} disabled={busy}>
              {busy
                ? "Please wait…"
                : mode === "signup"
                  ? "Create my account"
                  : "Sign in"}
            </button>
          </form>
          <p className={styles.hint}>
            Inventory connection is optional. Add a NXTDeal dealership after you
            sign in.
          </p>
          <MySalesEmail />
        </div>
      </main>
    );
  return (
    <div className={styles.root}>
      <header className={styles.header}>
        <div>
          <p className={styles.eyebrow}>NXTDEAL</p>
          <h1>MySales</h1>
        </div>
        <button
          onClick={() => setTab("more")}
          aria-label="Your account"
          className={styles.avatar}
        >
          {account.name.slice(0, 1).toUpperCase()}
        </button>
      </header>
      <main className={styles.main}>
        {error && (
          <div role="alert" className={styles.error}>
            {error}
            {!personalToken() && (
              <button
                onClick={() => {
                  setAccount(null);
                  clearWorkspace();
                }}
              >
                Sign in again
              </button>
            )}
          </div>
        )}
        {tab === "today" && (
          <>
            <p className={styles.eyebrow}>MAKE YOUR NEXT MOVE</p>
            <h2>Your day, {account.name.split(" ")[0]}</h2>
            <p className={styles.muted}>Keep the right conversations moving.</p>
            <div className={styles.stats}>
              <div>
                <strong>{due.length}</strong>
                <span>Follow-ups due</span>
              </div>
              <div>
                <strong>
                  {
                    contacts.filter(
                      (c) => !["sold", "closed"].includes(c.stage),
                    ).length
                  }
                </strong>
                <span>Active contacts</span>
              </div>
            </div>
            <div className={styles.actions}>
              <button
                className={styles.primary}
                onClick={() =>
                  setEditing({ kind: "tasks", data: { ...blank } })
                }
              >
                + Add follow-up
              </button>
              <button
                onClick={() =>
                  setEditing({ kind: "contacts", data: { ...blank } })
                }
              >
                + Add contact
              </button>
            </div>
            <h3>Next up</h3>
            {due.length === 0 ? (
              <div className={styles.empty}>
                <MySalesIcon name="check" />
                <h3>You’re caught up</h3>
                <p>Add a follow-up to plan your next conversation.</p>
              </div>
            ) : (
              due.map((t) => (
                <article key={t.id} className={styles.row}>
                  <button
                    className={styles.check}
                    disabled={busy}
                    aria-label={`Complete ${t.title}`}
                    onClick={() => toggle(t)}
                  >
                    <MySalesIcon name="check" />
                  </button>
                  <button
                    className={styles.rowText}
                    onClick={() =>
                      setEditing({ kind: "tasks", id: t.id, data: t })
                    }
                  >
                    <strong>{t.title}</strong>
                    <small>{t.due ? `Due ${t.due}` : "No date set"}</small>
                    {t.notes && <p>{t.notes}</p>}
                  </button>
                </article>
              ))
            )}
            <details>
              <summary>All follow-ups ({tasks.length})</summary>
              {tasks.map((t) => (
                <article className={styles.row} key={t.id}>
                  <button disabled={busy} onClick={() => toggle(t)}>
                    {t.done ? "Reopen" : "Complete"}
                  </button>
                  <button
                    className={styles.rowText}
                    onClick={() =>
                      setEditing({ kind: "tasks", id: t.id, data: t })
                    }
                  >
                    {t.title}
                    <small>
                      {t.done ? "Completed" : t.due || "No date set"}
                    </small>
                  </button>
                </article>
              ))}
            </details>
          </>
        )}
        {tab === "contacts" && (
          <>
            <div className={styles.titleRow}>
              <h2>Your contacts</h2>
              <button
                className={styles.primary}
                onClick={() =>
                  setEditing({ kind: "contacts", data: { ...blank } })
                }
              >
                + Add
              </button>
            </div>
            <p className={styles.muted}>
              Personal contacts you add here stay with your account. Dealership
              records are not imported.
            </p>
            <label>
              Find a contact
              <input
                type="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Name, phone or email"
              />
            </label>
            {visibleContacts.map((c) => (
                <button
                  key={c.id}
                  className={`${styles.row} ${styles.contact}`}
                  onClick={() =>
                    setEditing({ kind: "contacts", id: c.id, data: c })
                  }
                >
                  <span className={styles.avatar}>{c.title.slice(0, 1)}</span>
                  <span className={styles.rowText}>
                    <strong>{c.title}</strong>
                    <small>{c.phone || c.email || "Add contact details"}</small>
                  </span>
                  <span className={styles.badge}>{c.stage}</span>
                </button>
              ))}
            {contacts.length > 0 && visibleContacts.length === 0 && (
              <div role="status" className={styles.empty}>
                <h3>No contacts match your search</h3>
                <p>Try a name, phone number or email, or return to your full list.</p>
                <button className={styles.primary} onClick={() => setQuery("")}>Show all contacts</button>
              </div>
            )}
            {!contacts.length && (
              <div className={styles.empty}>
                <MySalesIcon name="people" />
                <h3>Start with a conversation</h3>
                <p>Add your first contact, then keep notes and a follow-up.</p>
              </div>
            )}
          </>
        )}
        {tab === "inventory" && (
          <>
            <h2>Inventory</h2>
            <p className={styles.muted}>
              Connect a dealership running NXTDeal to browse its shared retail
              inventory. Your personal account stays independent.
            </p>
            {connection ? (
              <section className={styles.card}>
                <p className={styles.eyebrow}>CONNECTED DEALERSHIP</p>
                <h3>{connection.name}</h3>
                <div className={styles.actions}>
                  <button
                    className={styles.primary}
                    disabled={busy}
                    onClick={() => sync()}
                  >
                    {busy ? "Refreshing…" : "Refresh inventory"}
                  </button>
                  <button disabled={busy} onClick={disconnect}>
                    Disconnect
                  </button>
                </div>
              </section>
            ) : (
              <form className={styles.card} onSubmit={connect}>
                <MySalesIcon name="car" className={styles.heroIcon} />
                <h3>Add a dealership when you’re ready</h3>
                <label>
                  Dealership ID
                  <input
                    required
                    maxLength={100}
                    value={dealer}
                    onChange={(e) => setDealer(e.target.value)}
                    placeholder="e.g. DLR-00001"
                    autoCapitalize="none"
                  />
                </label>
                <button className={styles.primary} disabled={busy}>
                  {busy ? "Connecting…" : "Connect inventory"}
                </button>
                <small>
                  This provides shared inventory only, not staff access.
                </small>
              </form>
            )}
            {inventoryError && (
              <p role="alert" className={styles.error}>
                {inventoryError}
              </p>
            )}
            {asOf && (
              <p className={styles.muted}>
                Retrieved {new Date(asOf).toLocaleString()} · up to 100 vehicles
                · refresh for latest availability
              </p>
            )}
            <div className={styles.vehicles}>
              {vehicles.map((v) => (
                <article className={styles.card} key={v.id}>
                  {v.image_url && /^https:\/\//.test(v.image_url) && (
                    <img
                      src={v.image_url}
                      alt=""
                      loading="lazy"
                      referrerPolicy="no-referrer"
                    />
                  )}
                  <h3>{[v.year, v.make, v.model].filter(Boolean).join(" ")}</h3>
                  <p>{v.trim}</p>
                  <strong>
                    {v.price
                      ? `$${Number(v.price).toLocaleString()}`
                      : "Ask dealership for price"}
                  </strong>
                  <small>{v.mileage ? `${v.mileage} miles` : ""}</small>
                </article>
              ))}
            </div>
            {asOf && !vehicles.length && (
              <p>No available vehicles were returned by this dealership.</p>
            )}
          </>
        )}
        {(tab === "coach" || tab === "setup") && (
          <MySalesAssistants
            key={tab}
            view={tab}
            tasks={tasks}
            recordsUpdated={recordsUpdated}
            onSetup={() => setTab("setup")}
          />
        )}
        {tab === "more" && (
          <>
            <h2>Your account</h2>
            <section className={styles.assistantChoices} aria-label="AI tools">
              <button onClick={() => setTab("coach")}>
                <MySalesIcon name="coach" className={styles.inlineIcon} />
                AI Coach<small>Prepare and practice</small>
              </button>
              <button onClick={() => setTab("setup")}>
                <MySalesIcon name="settings" className={styles.inlineIcon} />
                AI Setup<small>Connections and permissions</small>
              </button>
            </section>
            <details>
              <summary>My personal page</summary>
              <MySalesPersonalPage />
            </details>
            <section className={styles.card}>
              <h3>{account.name}</h3>
              <p>{account.email}</p>
              <MySalesEmail verification verified={account.email_verified}
                onVerified={() => setAccount({...account, email_verified: true})} />
              <p className={styles.muted}>
                Your MySales account is personal. Changing or disconnecting a
                dealership does not change your login, contacts or follow-ups.
              </p>
            </section>
            <section className={styles.card}>
              <h3>Dealership workspace</h3>
              <p>
                Staff tools, dealership-owned conversations, commissions and
                earned rewards remain in your dealership workspace. A personal
                MySales login does not grant access to those records.
              </p>
              <Link href="/apps/salesapp">Open dealership Sales →</Link>
            </section>
            <section className={styles.card}>
              <h3>Communication delivery</h3>
              <p>
                Notes and follow-ups do not send email or text messages.
                Account verification and recovery use the email controls above.
              </p>
            </section>
            <button
              disabled={busy}
              onClick={async () => {
                setBusy(true);
                try {
                  await personalSignOut();
                  setError("");
                } catch {
                  setError(
                    "Signed out on this device. The server could not confirm session revocation; the session will expire automatically.",
                  );
                } finally {
                  setAccount(null);
                  clearWorkspace();
                  setBusy(false);
                }
              }}
            >
              Sign out
            </button>
          </>
        )}
        <footer>© 2026 Chronos. All rights reserved.</footer>
      </main>
      <nav className={styles.nav} aria-label="MySales navigation">
        {tabs.map(([key, label, icon]) => (
          <button
            key={key}
            aria-current={
              tab === key ||
              (key === "more" && (tab === "coach" || tab === "setup"))
                ? "page"
                : undefined
            }
            onClick={() => {
              setTab(key);
              setError("");
            }}
          >
            <MySalesIcon name={icon} />
            <span>{label}</span>
          </button>
        ))}
      </nav>
      {editing && (
        <div className={styles.overlay}>
          <section
            ref={dialog}
            role="dialog"
            aria-modal="true"
            aria-label={
              editing.kind === "contacts"
                ? "Contact details"
                : "Follow-up details"
            }
            className={styles.sheet}
          >
            <div className={styles.titleRow}>
              <h2>{editing.kind === "contacts" ? "Contact" : "Follow-up"}</h2>
              <button disabled={busy} onClick={() => setEditing(null)}>
                Cancel
              </button>
            </div>
            <form onSubmit={save}>
              <label>
                {editing.kind === "contacts" ? "Name" : "What’s next?"}
                <input
                  autoFocus
                  required
                  maxLength={160}
                  value={editing.data.title}
                  onChange={(e) =>
                    setEditing({
                      ...editing,
                      data: { ...editing.data, title: e.target.value },
                    })
                  }
                />
              </label>
              {editing.kind === "contacts" ? (
                <>
                  <label>
                    Email
                    <input
                      type="email"
                      maxLength={254}
                      value={editing.data.email}
                      onChange={(e) =>
                        setEditing({
                          ...editing,
                          data: { ...editing.data, email: e.target.value },
                        })
                      }
                    />
                  </label>
                  <label>
                    Phone
                    <input
                      type="tel"
                      maxLength={40}
                      value={editing.data.phone}
                      onChange={(e) =>
                        setEditing({
                          ...editing,
                          data: { ...editing.data, phone: e.target.value },
                        })
                      }
                    />
                  </label>
                  <label>
                    Stage
                    <select
                      value={editing.data.stage}
                      onChange={(e) =>
                        setEditing({
                          ...editing,
                          data: { ...editing.data, stage: e.target.value },
                        })
                      }
                    >
                      {[
                        "new",
                        "contacted",
                        "appointment",
                        "sold",
                        "closed",
                      ].map((s) => (
                        <option key={s}>{s}</option>
                      ))}
                    </select>
                  </label>
                </>
              ) : (
                <label>
                  Due date
                  <input
                    type="date"
                    name="due"
                    value={editing.data.due}
                    onChange={(e) =>
                      setEditing({
                        ...editing,
                        data: { ...editing.data, due: e.target.value },
                      })
                    }
                  />
                </label>
              )}
              <label>
                Notes
                <textarea
                  maxLength={4000}
                  rows={3}
                  value={editing.data.notes}
                  onChange={(e) =>
                    setEditing({
                      ...editing,
                      data: { ...editing.data, notes: e.target.value },
                    })
                  }
                />
              </label>
              {error && (
                <p role="alert" className={styles.error}>
                  {error}
                </p>
              )}
              <button className={styles.primary} disabled={busy}>
                {busy ? "Saving…" : "Save"}
              </button>
            </form>
          </section>
        </div>
      )}
    </div>
  );
}
