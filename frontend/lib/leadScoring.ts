// core/lead_scoring.py's client (Marketing Growth Platform kickoff, 2026-07-17) --
// real point-based Lead Scoring off actually-trackable buying-intent signals
// (Started Credit Application, Deal Desked, Test Drive Completed, Appointment
// Attended/Scheduled, Event RSVP, Website Chat Initiated, Trigger Alert Match,
// Communication Logged). Routes live at /lead-scoring/*.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type ScoreBreakdownRow = { reason: string; count: number; points_each: number; points: number };

export type LeadScore = {
  entity_id: string;
  score: number;
  tier: "hot" | "warm" | "cool";
  breakdown: ScoreBreakdownRow[];
  not_yet_tracked: string[];
};

export type LeaderboardEntry = { lead_id: string; pipeline_state: string; source: string | null; score: number; tier: string };

export type Leaderboard = { count: number; by_tier: Record<string, number>; leads: LeaderboardEntry[] };

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

export async function getLeadScore(entityId: string): Promise<LeadScore> {
  const res = await fetch(`${API_BASE}/lead-scoring/${encodeURIComponent(entityId)}`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function getLeadScoringLeaderboard(limit = 50): Promise<Leaderboard> {
  const res = await fetch(`${API_BASE}/lead-scoring/leaderboard?limit=${limit}`, { headers: { ...authHeaders() } });
  return handle(res);
}
