"use client";

// DemoOverlay (2026-07-24; reworked 2026-07-25) — mounted once in the root layout, invisible unless a
// demo session is active. Sam dropped the auto-navigation "walkthrough" and the per-persona tailoring:
// discovery now happens through the per-dashboard coach-mark tutorial (lib/demoTour.ts, driven by the
// workspace), and this component is simply an AI bot that ANSWERS QUESTIONS — grounded in what the
// visitor is currently looking at (lib/demoScreen.ts). No auto-nav, no narration/TTS, no mode switch,
// no scenarios. Persona is still chosen on the lead form (it sets the backend role/data access), it's
// just no longer used to customize this host. The end-of-demo recommendation + exit remain.

import { useEffect, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useDemoSession, endDemoSession } from "@/lib/demoSession";
import { trackDemoEvent, askDemoGuide, fetchDemoSummary, type DemoSummary } from "@/lib/demo";
import { getDemoScreen } from "@/lib/demoScreen";

type Msg = { role: "you" | "host"; text: string };

export function DemoOverlay() {
  const session = useDemoSession();
  const pathname = usePathname();
  const router = useRouter();

  const [open, setOpen] = useState(true);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [summary, setSummary] = useState<DemoSummary | null>(null);
  const [wrapping, setWrapping] = useState(false);

  const logRef = useRef<HTMLDivElement>(null);

  // Track a page view whenever the route changes during a demo.
  useEffect(() => {
    if (session) trackDemoEvent("page_view", { path: pathname });
  }, [pathname, session]);

  // Keep the conversation scrolled to the latest line.
  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [messages, asking]);

  // Light screenshot/scrape deterrence (invisible).
  useEffect(() => {
    if (!session) return;
    const block = (e: Event) => e.preventDefault();
    document.addEventListener("contextmenu", block);
    document.addEventListener("dragstart", block);
    return () => {
      document.removeEventListener("contextmenu", block);
      document.removeEventListener("dragstart", block);
    };
  }, [session]);

  if (!session) return null;

  async function ask() {
    const q = question.trim();
    if (!q || asking) return;
    setQuestion("");
    setMessages((m) => [...m, { role: "you", text: q }]);
    setAsking(true);
    trackDemoEvent("question", { text: q });

    // Ground the answer in what's on screen right now (lib/demoScreen, published by the workspace).
    const screen = getDemoScreen();
    const payload = screen ? `${q}\n\n[What I'm looking at right now: ${screen}]` : q;

    try {
      const res = await askDemoGuide(payload);
      const line = res.response?.trim() || "I can help with that — try opening the section you're curious about, then ask again.";
      setMessages((m) => [...m, { role: "host", text: line }]);
    } catch {
      setMessages((m) => [
        ...m,
        { role: "host", text: "I couldn't reach the demo data just now. Try again in a moment, or open a section and ask about it." },
      ]);
    } finally {
      setAsking(false);
    }
  }

  async function finish() {
    if (wrapping) return;
    setWrapping(true);
    trackDemoEvent("finish", { path: pathname });
    try {
      setSummary(await fetchDemoSummary(session!.sessionId));
    } catch {
      setSummary({
        session_id: session!.sessionId,
        persona_label: session!.persona.label,
        interests: [],
        intent: "medium",
        score: 0,
        pages_viewed: 0,
        questions_asked: 0,
        recommendation: "You got a feel for how NXTDeal runs the store. A short live demo can go deeper on what matters to your dealership.",
        ctas: [
          { kind: "book", label: "Book a live demo", href: "/contact" },
          { kind: "network", label: "Install NXTDeal Network free", href: "/dealeros-network" },
        ],
      });
    } finally {
      setWrapping(false);
    }
  }

  function exit() {
    trackDemoEvent("exit", { path: pathname });
    endDemoSession();
    router.push("/demo");
  }

  return (
    <>
      {open ? (
        // Opens ABOVE the bottom-right icon row (Help / Knowledge / VIN) so it never covers them.
        <div className="fixed bottom-20 right-4 z-[60] flex w-[22rem] flex-col rounded-2xl border border-white/10 bg-[#141416]/95 font-brand text-white shadow-2xl backdrop-blur-md">
          <div className="flex items-center justify-between rounded-t-2xl border-b border-white/10 bg-white/[0.04] px-4 py-2.5">
            <div>
              <div className="text-sm font-semibold">🤖 AI Demo Host</div>
              <div className="text-[10px] uppercase tracking-wide text-brand-teal">Ask about anything on your screen</div>
            </div>
            <button onClick={() => setOpen(false)} className="text-xs text-zinc-500 hover:text-white" title="Minimize">
              —
            </button>
          </div>

          <div ref={logRef} className="max-h-[24rem] min-h-[8rem] space-y-2.5 overflow-y-auto p-4 text-sm">
            {messages.length === 0 && (
              <div className="rounded-xl border border-brand-teal/25 bg-brand-teal/10 p-3 text-[13px] leading-relaxed text-zinc-100">
                Hi — I&apos;m your demo guide. Click through the dashboards to see what each section does, and
                ask me anything about what&apos;s on screen. I answer from the live demo data.
              </div>
            )}
            {messages.map((m, i) => (
              <div key={i} className={m.role === "you" ? "flex justify-end" : "flex justify-start"}>
                <div
                  className={
                    m.role === "you"
                      ? "max-w-[85%] rounded-xl bg-brand-teal/90 px-3 py-2 text-[13px] leading-relaxed text-black"
                      : "max-w-[90%] rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2 text-[13px] leading-relaxed text-zinc-100"
                  }
                >
                  {m.text}
                </div>
              </div>
            ))}
            {asking && <div className="text-[12px] text-zinc-500">Thinking…</div>}
          </div>

          <div className="border-t border-white/10 p-3">
            <div className="flex gap-2">
              <input
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && ask()}
                placeholder="Ask about this screen…"
                disabled={asking}
                className="flex-1 rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-white placeholder-zinc-500 focus:border-brand-teal focus:outline-none disabled:opacity-60"
              />
              <button
                onClick={ask}
                disabled={asking || !question.trim()}
                className="rounded-lg bg-brand-teal px-3 text-xs font-semibold text-black disabled:opacity-40"
              >
                {asking ? "…" : "Ask"}
              </button>
            </div>
          </div>

          <div className="flex items-center justify-between rounded-b-2xl border-t border-white/10 px-4 py-2">
            <button onClick={exit} className="text-[11px] text-zinc-400 hover:text-[#EE3C25]">
              Exit demo
            </button>
            <button
              onClick={finish}
              disabled={wrapping}
              className="rounded-full bg-white/10 px-3 py-1 text-[11px] font-semibold text-white hover:bg-white/15 disabled:opacity-50"
            >
              {wrapping ? "Summarizing…" : "Finish & get my recommendation"}
            </button>
          </div>
        </div>
      ) : (
        // Minimized: a compact icon that sits to the LEFT of the VIN button (between it and the chat's
        // bot assistant), so it doesn't cover the other corner icons.
        <button
          onClick={() => setOpen(true)}
          title="AI Demo Host"
          className="fixed bottom-4 right-40 z-[60] flex h-11 w-11 items-center justify-center rounded-full bg-brand-teal text-lg shadow-2xl hover:bg-[#2fa9b1]"
        >
          🤖
        </button>
      )}

      {/* End-of-demo AI recommendation + conversion path */}
      {summary && (
        <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm">
          <div className="w-full max-w-lg rounded-2xl border border-white/10 bg-[#141416] p-6 font-brand text-white shadow-2xl">
            <div className="text-[11px] uppercase tracking-[0.2em] text-brand-teal">Your AI demo recap</div>
            <h2 className="mt-1.5 text-xl font-bold">Here&apos;s what I&apos;d recommend</h2>
            <p className="mt-2 text-sm text-zinc-300">{summary.recommendation}</p>

            <div className="mt-4 flex flex-wrap gap-2">
              {summary.interests.map((i) => (
                <span key={i} className="rounded-full bg-white/[0.06] px-2.5 py-1 text-[11px] text-zinc-200">
                  {i}
                </span>
              ))}
              <span
                className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${
                  summary.intent === "high"
                    ? "bg-emerald-500/15 text-emerald-300"
                    : summary.intent === "medium"
                    ? "bg-sky-500/15 text-sky-300"
                    : "bg-white/10 text-zinc-300"
                }`}
              >
                {summary.intent} interest
              </span>
            </div>

            <div className="mt-5 flex flex-col gap-2 sm:flex-row">
              {summary.ctas.map((c) => (
                <a
                  key={c.kind}
                  href={c.href}
                  onClick={() => trackDemoEvent("cta", { kind: c.kind })}
                  className={`flex-1 rounded-full px-4 py-2.5 text-center text-sm font-semibold transition ${
                    c.kind === "book" ? "bg-brand-teal text-black hover:bg-[#2fa9b1]" : "border border-white/15 text-white hover:bg-white/10"
                  }`}
                >
                  {c.label}
                </a>
              ))}
            </div>

            <div className="mt-3 flex items-center justify-between">
              <button onClick={() => setSummary(null)} className="text-[11px] text-zinc-400 hover:text-white">
                ‹ Keep exploring
              </button>
              <button onClick={exit} className="text-[11px] text-zinc-500 hover:text-[#EE3C25]">
                Leave demo
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
