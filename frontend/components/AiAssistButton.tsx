"use client";
import { WorkField } from "./WorkField";

// Reusable inline "✨ AI Assist" control (2026-07-23) -- Sam: "convert it into a
// contextual AI Writing Assistant UI pattern embedded directly into all text
// areas." One small trigger + popover that any text field can drop next to its
// input: generate / rewrite / shorten / expand / change-tone / fix-grammar, then
// Replace or Insert the result. Talks to lib/aiAssist.ts (POST /ai-assist).
//
// Deliberately self-contained and presentational: it owns no field state. The
// host passes the field's current `value` and an `onApply(newText)` callback, so
// the same component works for a controlled <input>, a <textarea>, or a
// contentEditable node. Rolling it out to a new field is one <AiAssistButton />.

import { useEffect, useRef, useState } from "react";
import {
  assist,
  AI_ASSIST_TONES,
  type AiAssistAction,
  type AiAssistTone,
} from "@/lib/aiAssist";

type Theme = "dark" | "light";

type Props = {
  // Current field text. Used as the input for the transform actions and shown to
  // the user as "what we're improving".
  value: string;
  // Called with the chosen result. `mode` tells the host whether the user asked
  // to replace the whole field or insert at the end (host decides how to splice).
  onApply: (text: string, mode: "replace" | "insert") => void;
  // What this field is (label / campaign goal). Powers `generate` and is passed
  // as extra guidance on the transform actions so copy stays on-topic.
  context?: string;
  theme?: Theme;
  className?: string;
  // A short human name for the field, shown in the generate prompt placeholder.
  fieldLabel?: string;
};

type ActionDef = {
  key: AiAssistAction;
  label: string;
  // Transform actions need existing text; generate/tone do not (generate writes
  // fresh, retone still needs text but is grouped under the tone control).
  needsText: boolean;
};

const TRANSFORMS: ActionDef[] = [
  { key: "rewrite", label: "Rewrite", needsText: true },
  { key: "shorten", label: "Shorten", needsText: true },
  { key: "expand", label: "Expand", needsText: true },
  { key: "grammar", label: "Fix grammar", needsText: true },
];

function cx(theme: Theme, dark: string, light: string) {
  return theme === "dark" ? dark : light;
}

export default function AiAssistButton({
  value,
  onApply,
  context,
  theme = "dark",
  className,
  fieldLabel,
}: Props) {
  const [open, setOpen] = useState(false);
  const [tone, setTone] = useState<AiAssistTone | "">(""); // "" = brand default
  const [genPrompt, setGenPrompt] = useState("");
  const [busy, setBusy] = useState<AiAssistAction | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{ text: string; aiGenerated: boolean; note?: string } | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);

  const hasText = Boolean(value && value.trim());

  // Close on outside click / Escape -- standard popover hygiene, no portal.
  useEffect(() => {
    if (!open) return;
    function onDown(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  async function run(action: AiAssistAction) {
    setBusy(action);
    setError(null);
    setResult(null);
    try {
      const ctxParts = [context, action === "generate" ? genPrompt : ""].filter(
        (p) => p && p.trim()
      );
      const res = await assist(value, action, {
        tone: tone || null,
        context: ctxParts.join(" — ") || null,
      });
      setResult({ text: res.result, aiGenerated: res.ai_generated, note: res.note });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setBusy(null);
    }
  }

  const panelCls = cx(
    theme,
    "border-zinc-700 bg-brand-charcoal text-zinc-200",
    "border-zinc-200 bg-white text-zinc-800"
  );
  const chipCls = cx(
    theme,
    "bg-zinc-800 text-zinc-200 hover:bg-zinc-700 border-zinc-700",
    "bg-zinc-100 text-zinc-700 hover:bg-zinc-200 border-zinc-200"
  );
  const inputCls = cx(
    theme,
    "bg-zinc-900 border-zinc-700 text-zinc-100 placeholder-zinc-500",
    "bg-white border-zinc-300 text-zinc-900 placeholder-zinc-400"
  );

  return (
    <div ref={rootRef} className={`relative inline-block ${className ?? ""}`}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        title="AI Assist"
        className={`inline-flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 rounded border ${chipCls}`}
      >
        <span aria-hidden>✨</span> AI Assist
      </button>

      {open && (
        <div
          className={`absolute right-0 z-50 mt-1 w-72 rounded-lg border shadow-xl p-2.5 space-y-2 ${panelCls}`}
        >
          {/* Tone control -- omitted tone = this dealer's saved brand tone. */}
          <div className="flex items-center gap-1.5">

            <WorkField label="Tone"><select
              value={tone}
              onChange={(e) => setTone(e.target.value as AiAssistTone | "")}
              className={`flex-1 h-7 px-1.5 text-[11px] rounded border ${inputCls}`}
            >
              <option value="">Brand default</option>
              {AI_ASSIST_TONES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select></WorkField>
            {tone && (
              <button
                type="button"
                onClick={() => run("retone")}
                disabled={!hasText || busy !== null}
                title="Rewrite the current text in this tone"
                className={`text-[10px] px-1.5 py-1 rounded border disabled:opacity-40 ${chipCls}`}
              >
                Apply tone
              </button>
            )}
          </div>

          {/* Transform actions -- act on the current field text. */}
          <div className="flex flex-wrap gap-1">
            {TRANSFORMS.map((a) => (
              <button
                key={a.key}
                type="button"
                onClick={() => run(a.key)}
                disabled={(a.needsText && !hasText) || busy !== null}
                className={`text-[11px] px-2 py-1 rounded border disabled:opacity-40 ${chipCls}`}
              >
                {busy === a.key ? "…" : a.label}
              </button>
            ))}
          </div>

          {/* Generate from scratch -- writes fresh copy from the prompt + context. */}
          <div className="space-y-1 pt-1 border-t border-zinc-700/50">

            <WorkField label="Generate new"><textarea
              value={genPrompt}
              onChange={(e) => setGenPrompt(e.target.value)}
              rows={2}
              placeholder={
                fieldLabel
                  ? `Describe the ${fieldLabel.toLowerCase()} you want…`
                  : "Describe what to write…"
              }
              className={`w-full text-[11px] rounded px-2 py-1.5 border resize-none ${inputCls}`}
            /></WorkField>
            <button
              type="button"
              onClick={() => run("generate")}
              disabled={!genPrompt.trim() || busy !== null}
              className={`w-full text-[11px] px-2 py-1 rounded border disabled:opacity-40 ${chipCls}`}
            >
              {busy === "generate" ? "Writing…" : "✨ Generate"}
            </button>
          </div>

          {error && <div className="text-[11px] text-red-400">{error}</div>}

          {result && (
            <div className="space-y-1.5 pt-1 border-t border-zinc-700/50">
              <div className="flex items-center justify-between">
                <span className="text-[10px] uppercase tracking-wide text-zinc-500">Suggestion</span>
                {!result.aiGenerated && (
                  <span
                    title={result.note || "Written with a built-in fallback, not the AI model."}
                    className="text-[9px] px-1.5 py-0.5 rounded-full bg-amber-950/40 text-amber-300"
                  >
                    offline draft
                  </span>
                )}
              </div>
              <div
                className={`max-h-40 overflow-y-auto text-[11px] whitespace-pre-wrap rounded px-2 py-1.5 border ${inputCls}`}
              >
                {result.text}
              </div>
              <div className="flex gap-1">
                <button
                  type="button"
                  onClick={() => {
                    onApply(result.text, "replace");
                    setOpen(false);
                    setResult(null);
                  }}
                  className={`flex-1 text-[11px] px-2 py-1 rounded border ${chipCls}`}
                >
                  Replace
                </button>
                <button
                  type="button"
                  onClick={() => {
                    onApply(result.text, "insert");
                    setOpen(false);
                    setResult(null);
                  }}
                  className={`flex-1 text-[11px] px-2 py-1 rounded border ${chipCls}`}
                >
                  Insert
                </button>
                <button
                  type="button"
                  onClick={() => setResult(null)}
                  className={`text-[11px] px-2 py-1 rounded border ${chipCls}`}
                >
                  Discard
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
