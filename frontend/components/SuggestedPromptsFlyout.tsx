"use client";

import { useState, useRef, useEffect } from "react";

// Suggested-prompt "fan up" flyout (session 47) -- Sam: "can we put that as a prompt
// suggestions that fans up with a little banner that says suggested prompt? the idea
// is to thin out the bottom piece." Replaces the always-visible wrapped chip row with
// a single slim banner button; the actual prompt chips render in an absolutely
// positioned panel above the banner so they never push the input down, and collapse
// again on prompt-select or an outside click.
export function SuggestedPromptsFlyout({
  prompts,
  onSelect,
}: {
  prompts: string[];
  onSelect: (prompt: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;

    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [open]);

  return (
    <div ref={containerRef} className="relative mb-2" data-tour-id="tour-suggested-prompts">
      {open && (
        <div className="absolute bottom-full left-0 right-0 mb-2 bg-zinc-900 border border-zinc-800 rounded-xl p-3 flex flex-wrap gap-2 shadow-xl animate-[fadeIn_0.12s_ease-out]">
          {prompts.map((prompt) => (
            <button
              key={prompt}
              onClick={() => {
                onSelect(prompt);
                setOpen(false);
              }}
              className="text-xs bg-zinc-950 border border-zinc-800 rounded-full px-3 py-1 text-zinc-400 hover:text-white hover:border-[#3FBCC4] transition"
            >
              {prompt}
            </button>
          ))}
        </div>
      )}

      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1.5 text-xs text-zinc-500 hover:text-white transition"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          className={open ? "transition-transform" : "transition-transform rotate-180"}
        >
          <path d="M6 9l6 6 6-6" />
        </svg>
        Suggested prompts
      </button>
    </div>
  );
}
