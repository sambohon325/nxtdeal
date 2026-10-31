"use client";

// useAiEnabled — resolves whether AI should render for the current user (Freemium roadmap,
// 2026-08-03). AI is on unless the dealer admin turned it off dealer-wide OR this user turned it
// off for themselves ("some people just don't want AI in their face"). The dashboards read this to
// decide whether to mount the AI chrome (workspace chat footer, bottom chat bar, AI bot, help/KB
// widgets). Fails OPEN (AI shown) on any error so a transient fetch failure never hides the product
// the user expects.

import { useEffect, useState } from "react";
import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";
import type { MyAiStatus } from "@/lib/aiSpend";

export function useAiEnabled(): { loading: boolean; aiEnabled: boolean; status: MyAiStatus | null } {
  const [status, setStatus] = useState<MyAiStatus | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    fetch(`${API_BASE}/ai-spend/my-status`, { headers: { ...authHeaders() } })
      .then((r) => r.json())
      .then((d) => {
        if (!alive) return;
        if (d && typeof d.ai_enabled === "boolean") setStatus(d as MyAiStatus);
      })
      .catch(() => {})
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, []);

  // Default true (fail open) until we know otherwise.
  const aiEnabled = status ? status.ai_enabled : true;
  return { loading, aiEnabled, status };
}
