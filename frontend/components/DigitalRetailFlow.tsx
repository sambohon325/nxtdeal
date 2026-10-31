"use client";

// Keep the public entry usable without collecting identity details or promising
// delivery from the former simulated verification flow. Underlying APIs remain.
export function DigitalRetailFlow({ open, onClose }: { open: boolean; onClose: () => void }) {
  if (!open) return null;
  return (
    <section aria-label="Online buying availability" className="rounded-2xl border border-white/10 bg-slate-950/90 p-6 text-white">
      <h2 className="text-xl font-semibold">Online buying is coming soon</h2>
      <p role="status" className="mt-3 text-sm text-zinc-400">
        Secure customer verification is not available yet. Please contact the dealership to continue your purchase.
      </p>
      <button type="button" onClick={onClose} className="mt-4 rounded-lg border border-white/20 px-4 py-2 text-sm">Close</button>
    </section>
  );
}
