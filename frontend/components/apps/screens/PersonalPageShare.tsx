"use client";

import { useEffect, useRef, useState } from "react";
import QRCode from "qrcode";

export function PersonalPageShare({ slug }: { slug: string }) {
  const [url, setUrl] = useState("");
  const [qr, setQr] = useState("");
  const [qrFailed, setQrFailed] = useState(false);
  const [message, setMessage] = useState("");
  const [copying, setCopying] = useState(false);
  const lock = useRef(false);
  useEffect(() => {
    let alive = true;
    const link = new URL(`/rep/${encodeURIComponent(slug)}`, window.location.origin).href;
    setUrl(link); setQr(""); setQrFailed(false); setMessage("");
    QRCode.toDataURL(link, { width: 256, margin: 2 }).then(value => { if (alive) setQr(value); })
      .catch(() => { if (alive) setQrFailed(true); });
    return () => { alive = false; };
  }, [slug]);
  async function copy() {
    if (!url || lock.current) return;
    lock.current = true; setCopying(true); setMessage("");
    try { await navigator.clipboard.writeText(url); setMessage("Page link copied."); }
    catch { setMessage("Copy was unavailable. Select and copy the link below."); }
    finally { lock.current = false; setCopying(false); }
  }
  return <section aria-label="Share published page" className="space-y-3 rounded-lg border border-white/15 p-3">
    <h3 className="text-sm font-medium">Share your published page</h3>
    <p className="text-xs text-zinc-400">Use this link or QR code in your signature or printed materials. Unpublishing makes the page unavailable.</p>
    <label className="block text-sm">Public page link<input readOnly value={url} className="mt-1 block w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white" /></label>
    <button type="button" disabled={!url || copying} onClick={copy} className="text-[var(--app-accent)] disabled:opacity-40">Copy page link</button>
    {message && <p role="status" className="text-sm">{message}</p>}
    {qr ? <div><img src={qr} alt="QR code for your published personal page" width={256} height={256} /><a href={qr} download="nxtdeal-personal-page-qr.png" className="text-sm text-[var(--app-accent)]">Download QR code</a></div>
      : <p role="status" className="text-xs">{qrFailed ? "QR code unavailable. You can still use the page link." : "Preparing QR code…"}</p>}
  </section>;
}
