"use client";

// The gear icon settings menu (session 74). Sam: "we need to have a gear icon on the
// far right at the top - when clicked, it should show user profile settings / password
// administration, notification settings. Under it, depending on your user levels
// rights (show the links to the admin page, readiness, and network, as well as dealer
// administration options... When clicked, all of these will open in the middle -
// expanded (close workspace) like the sub menu options, again, can break out as well."
//
// "Dealer Administration options (entire backend setting, users, data, etc.)" maps
// directly onto the already-built Administration department's Top Menu (Users/
// Security/Systems/Integrations/Vendors/Governance) rather than needing anything new
// -- this menu just opens that department's Dash via the same generic
// menuDash.open(department, itemKey) mechanism DepartmentMenuBar already uses,
// reusable from any page since MenuDashPanel/MenuDashBody are fully generic,
// parameterized by department. Role gating mirrors the REAL, already-enforced
// page-level gates (lib/auth.ts's useRequireAuth): /admin is useRequireAuth("ADMIN")
// (strict, ADMIN-only), /readiness and /network are useRequireAuth() (any
// authenticated role) -- so Administration is ADMIN-only here too, Readiness/Network
// are shown to everyone.
//
// `standalone: true` on every menuDash.open() call here (see lib/useMenuDash.ts) tells
// MenuDashPanel to render its own item-switcher nav, since the current page may have no
// DepartmentMenuBar for whatever department was just opened (e.g. opening
// Administration from /workspace).

import { useEffect, useRef, useState } from "react";
import type { Session } from "@/lib/auth";
import type { MenuDash } from "@/lib/useMenuDash";
import { angledClip } from "@/components/BrandAngles";

function MenuItem({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="w-full text-left px-3 py-1.5 text-sm text-zinc-300 hover:text-white hover:bg-zinc-900 transition"
    >
      {label}
    </button>
  );
}

function SectionLabel({ children }: { children: string }) {
  return (
    <div className="px-3 pt-2 pb-1 text-[10px] font-brand uppercase tracking-wider text-zinc-600">
      {children}
    </div>
  );
}

export function SettingsMenu({ session, menuDash }: { session: Session; menuDash: MenuDash }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClick(event: MouseEvent) {
      if (ref.current && !ref.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  function go(department: string, itemKey: string, kind: "menu" | "account" = "menu") {
    setOpen(false);
    menuDash.open(department, itemKey, kind, true);
  }

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((o) => !o)}
        title="Settings"
        style={angledClip(6)}
        className={
          open
            ? "w-8 h-8 flex items-center justify-center bg-brand-teal text-black transition"
            : "w-8 h-8 flex items-center justify-center bg-zinc-900 text-zinc-400 hover:text-white hover:bg-zinc-800 transition"
        }
      >
        <span className="text-base leading-none">⚙</span>
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-2 w-60 rounded-lg border border-zinc-800 bg-zinc-950 shadow-xl z-50 py-1.5 font-brand">
          <SectionLabel>Account</SectionLabel>
          <MenuItem label="Profile & Password" onClick={() => go("", "profile", "account")} />
          <MenuItem label="Notifications" onClick={() => go("", "notifications", "account")} />

          <div className="border-t border-zinc-900 my-1" />
          <SectionLabel>Platform</SectionLabel>
          {session.role === "ADMIN" && (
            <MenuItem label="Administration" onClick={() => go("Administration", "overview")} />
          )}
          <MenuItem label="Readiness" onClick={() => go("Readiness", "overview")} />
          <MenuItem label="Network" onClick={() => go("Network", "overview")} />
          <MenuItem label="Marketplace" onClick={() => go("Marketplace", "browse")} />
        </div>
      )}
    </div>
  );
}
