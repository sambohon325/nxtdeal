"use client";

// My Garage PII screens behind the identity gate (App Suite roadmap Phase 7). My Garage is
// a no-login customer app; its equity/trade-value and service-history screens show real PII.
// This wraps those screens in the reusable CustomerVerifyGate so the customer must verify
// their identity (the same tiered pattern the start-your-deal-online flow uses) before any
// PII renders — applying the pattern consistently instead of leaving it unique to one screen.

import { type AppDef, type AppScreen } from "@/lib/apps/registry";
import { AppScreenView } from "@/components/apps/AppScreenView";
import { CustomerVerifyGate } from "@/components/apps/CustomerVerifyGate";

// A short description of the protected content per screen, shown in the gate prompt.
const WHAT: Record<string, string> = {
  vehicles: "your equity, trade-in value, and service history",
  approvals: "your inspection photos and repair approvals",
  status: "your live vehicle status and updates",
  alerts: "your saved searches and alerts",
};

export function MyGarageGated({ app, screen }: { app: AppDef; screen: AppScreen }) {
  // AppScreenView renders the screen heading/intro itself once verified; before that the gate
  // is shown on its own (self-explanatory), so no duplicate header here.
  return (
    <CustomerVerifyGate what={WHAT[screen.key] || "your personal information"}>
      <AppScreenView app={app} screen={screen} />
    </CustomerVerifyGate>
  );
}
