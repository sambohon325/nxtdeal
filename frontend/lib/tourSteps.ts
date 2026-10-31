// Shared getting-started tour step lists (2026-07-13, session 34) — see
// components/OnboardingTour.tsx for the spotlight/callout mechanics. Each entry names a
// `data-tour-id` attribute that must already exist somewhere on the target page; the
// tour auto-skips any step whose element isn't found (e.g. a step tagged for a widget a
// simpler page doesn't have), so these lists don't all need to be identical across pages.

import type { TourStep } from "@/components/OnboardingTour";

// The full walkthrough — /workspace is where department tabs, chat, the workspace
// panel, pinned knowledge, and the chat dock all live together, so it gets every step.
export const WORKSPACE_TOUR_STEPS: TourStep[] = [
  {
    targetId: "tour-department-tabs",
    title: "Pick a department",
    description:
      "Operations, Sales, Marketing, Inventory, Service, Finance — switching tabs changes the suggested prompts below to what's relevant to that department. It doesn't restrict what you can ask.",
    placement: "bottom",
  },
  {
    targetId: "tour-chat-input",
    title: "Just ask",
    description:
      "Almost everything in NXTDeal starts here. Type a plain-English question or request — “show sales pipeline,” “sell a car,” “design a flyer” — instead of hunting for a button.",
    placement: "top",
  },
  {
    targetId: "tour-suggested-prompts",
    title: "Not sure what to ask?",
    description:
      "These chips are real, clickable prompts scoped to your current department tab — a quick way to see what NXTDeal can do without guessing at phrasing.",
    placement: "top",
  },
  {
    targetId: "tour-workspace-panel",
    title: "Your workspace",
    description:
      "Whatever you ask for — a dashboard, a customer profile, a deal, a campaign — renders here, live from NXTDeal's graph. Nothing here is a static mockup.",
    placement: "left",
  },
  {
    targetId: "tour-knowledge-sidebar",
    title: "Pin what matters",
    description:
      "Once something's open in the workspace panel, click Pin to save a shortcut back to it here — grouped by tag, and shared across every NXTDeal page.",
    placement: "right",
  },
  {
    targetId: "tour-chat-dock",
    title: "Message your team",
    description:
      "DM a colleague or drop into a department channel without leaving this screen — and share a pinned result straight into the conversation.",
    placement: "top",
  },
  {
    targetId: "tour-help-button",
    title: "Stuck? Ask for help",
    description:
      "This button is always here. It'll walk you through this screen again, or you can ask NXTDeal AI a question — it can already see what's on your screen.",
    placement: "top",
  },
];

// Lighter pages (/admin, /readiness, /network) don't have department tabs or a chat
// dock's worth of messaging chrome — just the chat + workspace panel + help button.
export const SIMPLE_TOUR_STEPS: TourStep[] = [
  {
    targetId: "tour-chat-input",
    title: "Just ask",
    description:
      "Type a plain-English question or request instead of hunting for a button — NXTDeal renders the answer in the panel to the side.",
    placement: "top",
  },
  {
    targetId: "tour-suggested-prompts",
    title: "Not sure what to ask?",
    description: "These chips are real, clickable prompts to get you started.",
    placement: "top",
  },
  {
    targetId: "tour-workspace-panel",
    title: "Your workspace",
    description: "Whatever you ask for renders here, live from NXTDeal's graph.",
    placement: "left",
  },
  {
    targetId: "tour-help-button",
    title: "Stuck? Ask for help",
    description:
      "This button is always here. It'll walk you through this screen again, or you can ask NXTDeal AI a question about whatever's currently on screen.",
    placement: "top",
  },
];

export function tourStorageKey(role: string, page: string): string {
  return `${page}_${role}`;
}
