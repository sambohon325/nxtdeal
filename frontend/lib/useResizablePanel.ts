"use client";

import { useCallback, useEffect, useRef, useState } from "react";

// Drag-to-resize for the workspace panel (session 41 -- Sam: "make the workspace edge
// adjustable... make it clear that you can drag to adjust it, and everything
// reflexively adjusts between the workspace and the chat area"). The panel is the
// rightmost flex child in `<main className="flex-1 flex ...">` on all four chat-first
// pages, so its right edge sits flush against the viewport edge -- dragging its LEFT
// edge just means "how far from the window's right edge is the mouse", i.e.
// `window.innerWidth - e.clientX`. The chat `<section>` next to it is `flex-1`, so it
// reflows automatically as this width changes; no separate wiring needed for that half.
//
// Persists the chosen width in localStorage (shared across all four pages, one habit
// the user sets once) so it survives navigation/reloads.
export function useResizablePanel(defaultWidth: number, min: number, max: number) {
  const storageKey = "dealeros_workspace_panel_width";

  const [width, setWidth] = useState(defaultWidth);
  const [isDragging, setIsDragging] = useState(false);
  const draggingRef = useRef(false);

  useEffect(() => {
    const stored = window.localStorage.getItem(storageKey);
    if (stored) {
      const parsed = Number(stored);
      if (!Number.isNaN(parsed)) {
        setWidth(Math.min(max, Math.max(min, parsed)));
      }
    }
    // Only read the saved width once on mount -- min/max/defaultWidth are stable
    // per-page constants, not reactive inputs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const onMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      draggingRef.current = true;
      setIsDragging(true);

      const onMouseMove = (moveEvent: MouseEvent) => {
        if (!draggingRef.current) return;
        const next = window.innerWidth - moveEvent.clientX;
        setWidth(Math.min(max, Math.max(min, next)));
      };

      const onMouseUp = () => {
        draggingRef.current = false;
        setIsDragging(false);
        window.removeEventListener("mousemove", onMouseMove);
        window.removeEventListener("mouseup", onMouseUp);
        setWidth((w) => {
          window.localStorage.setItem(storageKey, String(w));
          return w;
        });
      };

      window.addEventListener("mousemove", onMouseMove);
      window.addEventListener("mouseup", onMouseUp);
    },
    [min, max]
  );

  return { width, isDragging, onMouseDown };
}
