"use client";
import { WorkField } from "./WorkField";

// Floating "?" help widget (2026-07-13, session 34) — Sam: "each section... should have
// a floating space in the bottom of the workspace that has a question mark icon - and
// pops up a modal with a getting started / ai powered help that can see what is on
// screen and give suggestions." One modal, two tabs: "Getting Started" (static
// department-aware tips + a button to replay the spotlight tour) and "Ask AI" (a small
// chat hitting POST /help/ask, sending the active department plus a short summary of
// whatever's currently loaded in the workspace panel — see lib/useArtifactPanel.ts's
// Artifact union for what `screenContext` is built from on each page).
//
// Recolored yellow (2026-07-13, session 36) — turquoise (#3FBCC4) became the agentic
// bot's color (components/BotWidget.tsx, the square robot-icon button next to Send), so
// this reference/reactive widget moved to yellow (#FBCF09) to stay visually distinct
// from the bot's proactive suggestions.

import { useState } from "react";
import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";
import { angledClip } from "@/components/BrandAngles";

export type ScreenContext = {
  artifact_type: string;
  title: string;
  summary?: string;
} | null;

type Tip = { title: string; description: string };

const GENERAL_TIPS: Tip[] = [
  {
    title: "Ask for anything in chat",
    description:
      "Dashboards, customer/vehicle profiles, campaigns, deals — nearly everything renders in the workspace panel once you ask for it. There's rarely a button to hunt for.",
  },
  {
    title: "Pin what you'll want again",
    description:
      "Once something's open in the panel, click Pin to save a shortcut in the Knowledge sidebar — shared across every NXTDeal page.",
  },
];

const DEPARTMENT_TIPS: Record<string, Tip[]> = {
  Operations: [
    {
      title: "Check team capacity",
      description: 'Ask "who has the highest workload?" or "show current workload."',
    },
    {
      title: "Catch stalled leads",
      description: 'Ask "are there any escalated leads?" to see what needs attention.',
    },
    {
      title: "Review financing decisions",
      description: 'Ask "show deals awaiting financing" to see the F&I queue.',
    },
  ],
  Sales: [
    {
      title: "Sell a car",
      description:
        'Say "sell a car" to open the Deal Desk — build 2-3 pricing scenarios, pick financing, generate the contract, and fund it.',
    },
    {
      title: "Check your numbers",
      description: 'Ask "show sales pipeline" or "who\'s on top of the leaderboard?"',
    },
    {
      title: "Create a marketing asset",
      description: 'Say "design a flyer" to start the asset approval workflow.',
    },
  ],
  Marketing: [
    {
      title: "Build a website",
      description: 'Say "build a website" to start the website/inventory builder.',
    },
    {
      title: "Launch a campaign",
      description: 'Say "let\'s run a retention campaign" to start the campaign engine.',
    },
    {
      title: "Review approvals",
      description: 'Ask "show pending approvals" for assets awaiting sign-off.',
    },
  ],
  Inventory: [
    {
      title: "Find aging inventory",
      description: 'Ask "what inventory is aging?" or "show vehicles over 60 days."',
    },
    {
      title: "Look up a vehicle",
      description: 'Ask for a specific vehicle by ID, e.g. "pull up VEH-00042."',
    },
  ],
  Service: [
    {
      title: "Check today's schedule",
      description: 'Ask "what appointments are scheduled today?"',
    },
    {
      title: "Catch overdue work",
      description: 'Ask "any overdue service orders?" or "show service workload."',
    },
  ],
  Finance: [
    {
      title: "Review financing decisions",
      description: 'Ask "show deals awaiting financing" to see deals needing a decision.',
    },
    {
      title: "Check the pipeline",
      description: 'Ask "show finance pipeline" or "what deals are pending approval?"',
    },
  ],
};

export function HelpWidget({
  department,
  screenContext,
  onReplayTour,
  hideAssistant = false,
  menuMode = false,
  onDismiss,
}: {
  department?: string;
  screenContext?: ScreenContext;
  onReplayTour: () => void;
  hideAssistant?: boolean;
  menuMode?: boolean;
  onDismiss?: () => void;
}) {
  const [open, setOpen] = useState(menuMode);
  const [tab, setTab] = useState<"getting-started" | "ask-ai">("getting-started");
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [conversation, setConversation] = useState<{ question: string; answer: string }[]>([]);
  const [askError, setAskError] = useState<string | null>(null);

  const tips = [...(department ? DEPARTMENT_TIPS[department] ?? [] : []), ...GENERAL_TIPS];

  async function askHelp() {
    const q = question.trim();
    if (!q || asking) return;

    setAsking(true);
    setAskError(null);
    setQuestion("");

    try {
      const response = await fetch(`${API_BASE}/help/ask`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...authHeaders(),
        },
        body: JSON.stringify({
          question: q,
          department: department ?? null,
          screen_context: screenContext ?? null,
        }),
      });

      const data = await response.json();

      if (!response.ok || data.error) {
        throw new Error(data.error ?? `Backend returned ${response.status}`);
      }

      setConversation((prev) => [...prev, { question: q, answer: data.response ?? "No response received." }]);
    } catch (error) {
      setAskError(error instanceof Error ? error.message : "Unable to reach NXTDeal backend.");
    } finally {
      setAsking(false);
    }
  }

  return (
    <>
      {!menuMode && <button
        data-tour-id="tour-help-button"
        onClick={() => setOpen(true)}
        title="Help"
        style={angledClip(9)}
        className="fixed bottom-4 right-4 z-40 w-11 h-11 bg-brand-yellow text-black text-lg font-semibold shadow-lg hover:bg-[#f7d43d] transition flex items-center justify-center"
      >
        ?
      </button>}

      {open && (
        <div className="fixed inset-0 z-[150] flex items-center justify-center bg-black/60 p-4">
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl w-full max-w-lg max-h-[80vh] flex flex-col overflow-hidden">
            <div className="flex items-center justify-between p-4 border-b border-zinc-800">
              <div className="font-medium">
                Help{department ? ` — ${department}` : ""}
              </div>
              <button onClick={() => { setOpen(false); onDismiss?.(); }} className="text-zinc-500 hover:text-white transition">
                ✕
              </button>
            </div>

            <div className="flex border-b border-zinc-800">
              <button
                onClick={() => setTab("getting-started")}
                className={
                  tab === "getting-started"
                    ? "flex-1 py-2 text-sm text-[#FBCF09] border-b-2 border-[#FBCF09]"
                    : "flex-1 py-2 text-sm text-zinc-500 hover:text-white transition"
                }
              >
                Getting Started
              </button>
              {!hideAssistant && <button
                onClick={() => setTab("ask-ai")}
                className={
                  tab === "ask-ai"
                    ? "flex-1 py-2 text-sm text-[#FBCF09] border-b-2 border-[#FBCF09]"
                    : "flex-1 py-2 text-sm text-zinc-500 hover:text-white transition"
                }
              >
                Ask AI
              </button>}
            </div>

            <div className="flex-1 overflow-y-auto p-4">
              {tab === "getting-started" ? (
                <div className="space-y-3">
                  <button
                    onClick={() => {
                      setOpen(false); onDismiss?.();
                      onReplayTour();
                    }}
                    className="w-full px-4 py-2 rounded-lg brand-cta text-sm"
                  >
                    {hideAssistant ? "Open screen guide" : "⟳ Replay the guided tour"}
                  </button>

                  {hideAssistant && <p className="text-sm leading-relaxed text-zinc-300">Choose a department to browse its screens. Open a priority card to inspect records, and use Quick Actions for daily work. Apps, VIN Lookup, Help and Notifications are at the upper right. Screen controls are at the bottom of the left navigation. Find Extras & tools and the Knowledge Base in Administration.</p>}
                  {(hideAssistant ? [] : tips).map((tip, i) => (
                    <div key={i} className="bg-zinc-950 border border-zinc-800 rounded-lg p-3">
                      <div className="text-sm font-medium mb-1">{tip.title}</div>
                      <div className="text-xs text-zinc-400">{tip.description}</div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="space-y-3">
                  {conversation.length === 0 && (
                    <div className="text-xs text-zinc-500">
                      Ask about whatever's on your screen right now — NXTDeal AI can see
                      what's currently open in your workspace panel.
                    </div>
                  )}

                  {conversation.map((turn, i) => (
                    <div key={i} className="space-y-1">
                      <div className="text-sm text-zinc-300 font-medium">{turn.question}</div>
                      <div className="text-sm text-zinc-400 whitespace-pre-wrap">{turn.answer}</div>
                    </div>
                  ))}

                  {asking && <div className="text-xs text-zinc-500">Thinking…</div>}
                  {askError && <div className="text-xs text-[#EE3C25]">{askError}</div>}
                </div>
              )}
            </div>

            {tab === "ask-ai" && (
              <div className="p-3 border-t border-zinc-800 flex gap-2">
                <WorkField label="What can I do here?"><input
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") askHelp();
                  }}
                  placeholder="What can I do here?"
                  className="flex-1 h-9 px-3 text-sm rounded bg-zinc-950 border border-zinc-800"
                /></WorkField>
                <button
                  onClick={askHelp}
                  disabled={asking || !question.trim()}
                  className="px-4 py-2 rounded-lg bg-[#FBCF09] text-black hover:bg-[#f7d43d] text-sm disabled:opacity-50"
                >
                  Ask
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}
