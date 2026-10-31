"use client";

// Scoped landing shell (2026-07-25) for BDC and Marketing users. Instead of the full
// multi-department workspace chrome, these roles land straight on a focused surface: BDC on
// the lead queue / follow-up / qualification / handoff views; Marketing on campaigns, the
// library, tools, import, and files. It renders the real purpose-built boards directly
// (no catalog machinery), with a minimal branded header + a left-rail surface switcher.
// A "Full workspace" link is always available — this is the default landing, not a cage.

import { BrandLogo } from "@/components/BrandLogo";
import { useMemo, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { useRequireAuth, clearSession } from "@/lib/auth";
import { BrandRibbon } from "@/components/BrandAngles";
import { BdcBoard, type BdcSection } from "@/components/BdcBoard";
import { CampaignsBoard } from "@/components/CampaignsBoard";
import { CampaignLibraryBoard } from "@/components/CampaignLibraryBoard";
import { CampaignSchedulerBoard } from "@/components/CampaignSchedulerBoard";
import { LeadImportBoard } from "@/components/LeadImportBoard";
import { FileManagerBoard } from "@/components/FileManagerBoard";

type Theme = "dark" | "light";

type Surface = {
  key: string;
  label: string;
  render: (theme: Theme) => ReactNode;
};

const BDC_SURFACES: Surface[] = [
  { key: "queue", label: "Lead Queue", render: () => <BdcBoard section="queue" /> },
  { key: "first_contact", label: "Response Times", render: () => <BdcBoard section="first_contact" /> },
  { key: "qualification", label: "Qualification", render: () => <BdcBoard section="qualification" /> },
  { key: "handoff", label: "Handoffs", render: () => <BdcBoard section="handoff" /> },
  { key: "scorecard", label: "Scorecard", render: () => <BdcBoard section="scorecard" /> },
];

const MARKETING_SURFACES: Surface[] = [
  { key: "campaigns", label: "Campaigns", render: (t) => <CampaignsBoard theme={t} /> },
  { key: "library", label: "Campaign Library", render: (t) => <CampaignLibraryBoard theme={t} /> },
  { key: "tools", label: "Campaign Tools", render: (t) => <CampaignSchedulerBoard theme={t} /> },
  { key: "import", label: "Import", render: (t) => <LeadImportBoard theme={t} /> },
  { key: "files", label: "File Manager", render: (t) => <FileManagerBoard theme={t} /> },
];

export default function FocusPage() {
  const session = useRequireAuth();
  const router = useRouter();
  const [theme, setTheme] = useState<Theme>("dark");

  const role = session?.role ?? "";
  const profile = useMemo<{ title: string; surfaces: Surface[] } | null>(() => {
    if (role === "BDC") return { title: "BDC", surfaces: BDC_SURFACES };
    if (role === "MARKETING") return { title: "Marketing", surfaces: MARKETING_SURFACES };
    return null;
  }, [role]);

  const [active, setActive] = useState<string>(
    role === "BDC" ? "queue" : "campaigns"
  );

  if (!session) return null;

  function signOut() {
    clearSession();
    router.push("/");
  }

  // A role without a focused profile (e.g. ADMIN who navigated here directly) gets a gentle
  // hand-off to the full workspace rather than an empty shell.
  if (!profile) {
    return (
      <div className="h-screen flex flex-col items-center justify-center bg-[#111111] text-white gap-4">
        <div className="text-sm text-zinc-400">The focused view is set up for BDC and Marketing teams.</div>
        <button onClick={() => router.push("/workspace")} className="brand-cta px-4 py-2 text-sm">
          Go to the full workspace
        </button>
      </div>
    );
  }

  const activeSurface = profile.surfaces.find((s) => s.key === active) ?? profile.surfaces[0];

  return (
    <div className="h-screen overflow-hidden bg-[#111111] text-white flex flex-col">
      <header className="border-b border-zinc-900 px-6 py-3 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-3">
          <BrandLogo />
          <span className="text-[10px] uppercase tracking-[0.28em] text-zinc-500">{profile.title}</span>
        </div>
        <div className="flex items-center gap-4 text-[11px] uppercase tracking-wide font-brand">
          <button
            onClick={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
            className="text-zinc-500 hover:text-white"
            title="Toggle theme"
          >
            {theme === "dark" ? "Light" : "Dark"}
          </button>
          <button onClick={() => router.push("/workspace")} className="text-zinc-500 hover:text-white">
            Full workspace
          </button>
          <span className="text-zinc-600">{session.employeeId} · {session.role}</span>
          <button onClick={signOut} className="text-zinc-500 hover:text-white font-bold">Sign Out</button>
        </div>
      </header>

      <BrandRibbon />

      <div className="flex-1 min-h-0 flex overflow-hidden">
        {/* Left-rail surface switcher (bottom bar on phones). */}
        <nav className="hidden md:flex w-48 shrink-0 flex-col border-r border-zinc-900 py-3 gap-0.5">
          {profile.surfaces.map((s) => (
            <button
              key={s.key}
              onClick={() => setActive(s.key)}
              className={
                active === s.key
                  ? "text-left text-[12px] font-brand font-semibold uppercase tracking-wide bg-brand-teal text-black pl-4 pr-3 py-2"
                  : "text-left text-[12px] font-brand font-semibold uppercase tracking-wide text-zinc-400 hover:bg-zinc-900 hover:text-white pl-4 pr-3 py-2 transition"
              }
            >
              {s.label}
            </button>
          ))}
        </nav>

        <main data-appearance={theme} className="flex-1 min-w-0 flex flex-col overflow-auto p-6">
          {activeSurface.render(theme)}
        </main>
      </div>

      {/* Phone: bottom tab bar */}
      <nav className="md:hidden flex border-t border-zinc-900 overflow-x-auto shrink-0">
        {profile.surfaces.map((s) => (
          <button
            key={s.key}
            onClick={() => setActive(s.key)}
            className={
              active === s.key
                ? "flex-1 whitespace-nowrap text-[10px] font-brand font-semibold uppercase tracking-wide bg-brand-teal text-black px-3 py-2"
                : "flex-1 whitespace-nowrap text-[10px] font-brand font-semibold uppercase tracking-wide text-zinc-400 px-3 py-2"
            }
          >
            {s.label}
          </button>
        ))}
      </nav>
    </div>
  );
}
