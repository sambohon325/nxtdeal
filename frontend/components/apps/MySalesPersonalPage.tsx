"use client";
import { useEffect, useState, type FormEvent } from "react";
import { PersonalPage } from "@/components/PersonalPage";
import { type PublicPersonalSite } from "@/lib/websites";
import { personalRequest } from "@/lib/mysalesPersonal";
import styles from "./MySalesPersonal.module.css";
type Draft = {
  headline: string;
  subheadline: string;
  bio: string;
  photo_url: string;
  phone: string;
  email: string;
  calendar_link: string;
  review_link: string;
};
type PageState = { slug: string; draft: Draft; published: boolean };
export function MySalesPersonalPage() {
  const [page, setPage] = useState<PageState | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [message, setMessage] = useState(""),
    [dirty, setDirty] = useState(false),
    [confirm, setConfirm] = useState(false),
    [preview, setPreview] = useState(false);
  useEffect(() => {
    let active = true;
    personalRequest<PageState>("/page")
      .then((p) => {
        if (active) setPage(p);
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, []);
  async function save(e: FormEvent) {
    e.preventDefault();
    if (!page) return;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      setPage(await personalRequest<PageState>("/page", "PUT", page.draft));
      setDirty(false);
      setConfirm(false);
      setMessage("Draft saved. Publish when you’re ready.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function publish(value: boolean) {
    if (!page) return;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      setPage(
        await personalRequest<PageState>("/page/publication", "PUT", {
          published: value,
        }),
      );
      setConfirm(false);
      setMessage(
        value
          ? "Your saved page is now public."
          : "Your page is no longer public.",
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  if (!page)
    return (
      <section className={styles.card}>
        {error ? (
          <p role="alert">{error}</p>
        ) : (
          <p role="status">Loading your page…</p>
        )}
      </section>
    );
  const rendered: PublicPersonalSite = {
    ...page.draft,
    slug: page.slug,
    cta_text: "Contact me",
    featured_vehicles: [],
    branding: { branding_mode: "personal", oem_name: null, oem_logo_url: null },
  };
  const labels: Record<keyof Draft, string> = {
    headline: "Headline",
    subheadline: "Short introduction",
    bio: "About you",
    photo_url: "Photo URL (HTTPS)",
    phone: "Public phone",
    email: "Public email",
    calendar_link: "Booking link (HTTPS)",
    review_link: "Review link (HTTPS)",
  };
  return (
    <section className={styles.card}>
      <h3>My personal page</h3>
      <p className={styles.muted}>
        Your page travels with your account. Only the details you publish below
        are public.
      </p>
      <form onSubmit={save}>
        {(Object.keys(labels) as (keyof Draft)[]).map((key) => (
          <label key={key}>
            {labels[key]}
            {key === "bio" ? (
              <textarea
                rows={4}
                maxLength={3000}
                value={page.draft[key]}
                onChange={(e) => {
                  setPage({
                    ...page,
                    draft: { ...page.draft, [key]: e.target.value },
                  });
                  setDirty(true);
                  setConfirm(false);
                }}
              />
            ) : (
              <input
                type={
                  key === "email"
                    ? "email"
                    : key === "phone"
                      ? "tel"
                      : key.includes("url") || key.includes("link")
                        ? "url"
                        : "text"
                }
                required={key === "headline"}
                maxLength={
                  key === "headline"
                    ? 160
                    : key === "subheadline"
                      ? 200
                      : key === "phone"
                        ? 40
                        : key === "email"
                          ? 254
                          : 1000
                }
                value={page.draft[key]}
                onChange={(e) => {
                  setPage({
                    ...page,
                    draft: { ...page.draft, [key]: e.target.value },
                  });
                  setDirty(true);
                  setConfirm(false);
                }}
              />
            )}
          </label>
        ))}
        <button className={styles.primary} disabled={busy}>
          Save draft
        </button>
      </form>
      <button aria-expanded={preview} onClick={() => setPreview(!preview)}>
        {preview ? "Hide preview" : "Preview page"}
      </button>
      {preview && <PersonalPage site={rendered} />}
      <label>
        <span>
          <input
            type="checkbox"
            checked={confirm}
            onChange={(e) => setConfirm(e.target.checked)}
            style={{
              display: "inline-block",
              width: 22,
              minHeight: 22,
              marginRight: 10,
            }}
          />
          I want the saved page and its contact details to be public.
        </span>
      </label>
      <button
        className={styles.primary}
        disabled={busy || dirty || !confirm}
        onClick={() => publish(true)}
      >
        {page.published ? "Publish saved changes" : "Publish page"}
      </button>
      {dirty && <small>Save your edits before publishing.</small>}
      {page.published && (
        <>
          <a
            href={`/apps/mysales/rep/${page.slug}`}
            target="_blank"
            rel="noopener noreferrer"
          >
            Open public page ↗
          </a>
          <button disabled={busy} onClick={() => publish(false)}>
            Unpublish
          </button>
        </>
      )}
      {message && <p role="status">{message}</p>}
      {error && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}
    </section>
  );
}
