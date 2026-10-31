"use client";

// Floating getting-started tutorial (2026-07-13, session 34) — Sam: "a floating getting
// started tutorial where it walks you through with highlights and arrows like we did for
// the previous sales design reference." Generic, step-driven spotlight overlay: each step names a
// `data-tour-id` attribute already present somewhere on the page, this component finds
// that element, cuts a highlighted "hole" around it in a dimmed overlay, and shows an
// arrow-pointing callout with a title/description next to it. Pages don't hardcode any
// positioning math — they just tag the elements they want highlighted and hand this
// component an ordered `steps` array (see lib/tourSteps.ts).
//
// Deliberately NOT built with an SVG mask (cross-browser mask-composite quirks) — the
// "hole" is four plain dark divs surrounding the target's bounding rect instead, which is
// simple, cheap to recompute on resize/scroll, and never fights browser support.

import { useEffect, useLayoutEffect, useState, type CSSProperties } from "react";

export type TourStep = {
  targetId: string; // matches a data-tour-id="..." attribute somewhere on the page
  title: string;
  description: string;
  placement?: "top" | "bottom" | "left" | "right";
};

const PADDING = 8;

function getRect(targetId: string): DOMRect | null {
  if (typeof document === "undefined") return null;

  const el = document.querySelector(`[data-tour-id="${targetId}"]`);

  if (!el) return null;

  return el.getBoundingClientRect();
}

export function OnboardingTour({
  steps,
  active,
  onComplete,
  onSkip,
}: {
  steps: TourStep[];
  active: boolean;
  onComplete: () => void;
  onSkip: () => void;
}) {
  const [stepIndex, setStepIndex] = useState(0);
  const [rect, setRect] = useState<DOMRect | null>(null);
  const [notFoundStreak, setNotFoundStreak] = useState(0);

  const step = steps[stepIndex];

  useEffect(() => {
    if (active) {
      setStepIndex(0);
      // Reset the not-found streak too — this instance is reused across department tours, and a
      // stale streak from a prior (all-missing) tour could otherwise auto-complete the next one.
      setNotFoundStreak(0);
    }
  }, [active]);

  useLayoutEffect(() => {
    if (!active || !step) return;

    function update() {
      const found = getRect(step.targetId);
      setRect(found);
    }

    update();

    window.addEventListener("resize", update);
    window.addEventListener("scroll", update, true);

    // A short retry loop covers steps whose target only exists after a re-render this
    // same tick (e.g. a tab switch triggered by the previous step).
    const retry = setTimeout(update, 150);

    return () => {
      window.removeEventListener("resize", update);
      window.removeEventListener("scroll", update, true);
      clearTimeout(retry);
    };
  }, [active, step]);

  // If a step's target genuinely isn't on the page (e.g. a step tagged for a tab the
  // user isn't on), don't strand the tour — skip forward automatically. The streak
  // guard prevents an infinite loop if every remaining step is missing.
  useEffect(() => {
    if (!active || !step) return;
    if (rect) {
      setNotFoundStreak(0);
      return;
    }

    if (notFoundStreak > steps.length) {
      onComplete();
      return;
    }

    const timer = setTimeout(() => {
      if (stepIndex < steps.length - 1) {
        setStepIndex((i) => i + 1);
        setNotFoundStreak((n) => n + 1);
      } else {
        onComplete();
      }
    }, 400);

    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rect, active, step, stepIndex]);

  if (!active || !step || !rect) return null;

  const isLast = stepIndex === steps.length - 1;
  const placement = step.placement ?? "bottom";

  const top = rect.top - PADDING;
  const left = rect.left - PADDING;
  const width = rect.width + PADDING * 2;
  const height = rect.height + PADDING * 2;

  // Callout position — a simple offset from the highlighted box based on placement,
  // clamped so it never runs off-screen.
  const calloutWidth = 320;
  let calloutTop = top + height + 16;
  let calloutLeft = left;

  if (placement === "top") {
    calloutTop = top - 16;
  } else if (placement === "left") {
    calloutTop = top;
    calloutLeft = left - calloutWidth - 16;
  } else if (placement === "right") {
    calloutTop = top;
    calloutLeft = left + width + 16;
  }

  calloutLeft = Math.max(16, Math.min(calloutLeft, window.innerWidth - calloutWidth - 16));

  const calloutStyle: CSSProperties =
    placement === "top"
      ? { left: calloutLeft, bottom: window.innerHeight - calloutTop, width: calloutWidth }
      : { top: calloutTop, left: calloutLeft, width: calloutWidth };

  return (
    <div className="fixed inset-0 z-[200]" role="dialog" aria-modal="true">
      {/* Four dimmed panels surrounding the spotlight rect -- the "hole" is just the
          uncovered gap between them, not an actual cutout element. */}
      <div className="fixed bg-black/70 pointer-events-none" style={{ top: 0, left: 0, right: 0, height: Math.max(0, top) }} />
      <div className="fixed bg-black/70 pointer-events-none" style={{ top: top + height, left: 0, right: 0, bottom: 0 }} />
      <div className="fixed bg-black/70 pointer-events-none" style={{ top, left: 0, width: Math.max(0, left), height }} />
      <div className="fixed bg-black/70 pointer-events-none" style={{ top, left: left + width, right: 0, height }} />

      {/* Highlight ring around the spotlighted element */}
      <div
        className="fixed rounded-lg pointer-events-none"
        style={{
          top,
          left,
          width,
          height,
          boxShadow: "0 0 0 3px #3FBCC4, 0 0 24px rgba(70, 192, 200, 0.5)",
        }}
      />

      {/* Callout */}
      <div
        className="fixed bg-zinc-900 border border-[#3FBCC4]/40 rounded-xl p-4 shadow-2xl"
        style={calloutStyle}
      >
        <div className="flex items-center justify-between mb-2">
          <div className="text-[10px] uppercase tracking-wider text-zinc-500">
            Step {stepIndex + 1} of {steps.length}
          </div>
          <button
            onClick={onSkip}
            className="text-xs text-zinc-500 hover:text-white transition"
          >
            Skip tour
          </button>
        </div>

        <div className="font-medium text-sm mb-1">{step.title}</div>
        <div className="text-xs text-zinc-400 mb-3">{step.description}</div>

        <div className="flex items-center justify-between">
          <div className="flex gap-1">
            {steps.map((_, i) => (
              <div
                key={i}
                className={
                  i === stepIndex
                    ? "w-1.5 h-1.5 rounded-full bg-[#3FBCC4]"
                    : "w-1.5 h-1.5 rounded-full bg-zinc-700"
                }
              />
            ))}
          </div>

          <div className="flex gap-2">
            {stepIndex > 0 && (
              <button
                onClick={() => setStepIndex((i) => i - 1)}
                className="text-xs px-3 py-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 transition"
              >
                Back
              </button>
            )}
            <button
              onClick={() => (isLast ? onComplete() : setStepIndex((i) => i + 1))}
              className="text-xs px-3 py-1.5 rounded-lg bg-[#3FBCC4] text-black hover:bg-[#5cd0d8] transition"
            >
              {isLast ? "Done" : "Next"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

const TOUR_SEEN_PREFIX = "dealeros_tour_seen_";

export function hasTourBeenSeen(key: string): boolean {
  if (typeof window === "undefined") return true;
  return window.localStorage.getItem(TOUR_SEEN_PREFIX + key) === "1";
}

export function markTourSeen(key: string) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(TOUR_SEEN_PREFIX + key, "1");
}
