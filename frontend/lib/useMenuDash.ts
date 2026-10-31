"use client";

// The Top Menu's "open as its own dash" state (session 60). Sam: "when you click on
// the menu items, they'll open up as their own dashes, but instead of floating on top,
// we need to collapse the middle column into the chat, and the right column to the
// edge, with a little tab icon if you want to reopen it... if you want to pop it out
// into another window you can - both columns return to normal."
//
// Lifted out of components/DepartmentMenuBar.tsx into its own hook because the collapse
// behavior has to reach sibling columns (the chat <section> and the Workspace <aside>)
// elsewhere in app/workspace/page.tsx's JSX tree, not just the menu bar itself -- one
// hook instance per page, passed down to the menu bar, the chat column, the workspace
// column, and the dash panel itself.
import { useRef, useState } from "react";

// `kind` added session 72 (Sam: "instead of poping out as separate windows, can we
// treat [the 4 job-workflow buttons] the same as we do with the sub menu and collapse
// the workspace and fill that entire space? same as the others") -- this same Dash
// takeover now hosts either a Top Menu item ("menu", the original session-60 behavior)
// or a job-workflow window ("workflow", previously its own floating/draggable window
// manager in components/DepartmentWorkflowButtons.tsx). Only one Dash can be open at a
// time either way, which is exactly the point -- "collapse the workspace and fill that
// entire space" only makes sense for one thing at once.
//
// "account" added session 74 (the gear icon settings menu -- Sam: "when clicked, all
// of these will open in the middle - expanded (close workspace) like the sub menu
// options, again, can break out as well"). Unlike "menu"/"workflow", an account Dash
// can be opened from ANY page regardless of that page's own department (e.g. opening
// Administration from /workspace, which has no Administration DepartmentMenuBar of its
// own) -- see `standalone` below.
//
// "entity" added session 76 fifth follow-up (Sam, after the entity-ID links from the
// previous pass: "instead of clicking the link and it opening in a new tab - can it
// pop up in a modal when you hover over it, with the option to pop it out into a new
// window or to push into the dash / sub menu area"). Like "account", an entity Dash
// can be opened from anywhere regardless of the current page's own department --
// `itemKey` holds the entity ID itself rather than a catalog key, and `department` is
// unused (kept "" by convention, same as "account"'s call sites).
export type MenuDashKind = "menu" | "workflow" | "account" | "entity";

export type MenuDashItem = {
  department: string;
  itemKey: string;
  kind: MenuDashKind;
  // True when this Dash was opened from the global gear icon rather than the current
  // page's own DepartmentMenuBar -- there's no local item-switcher nav to rely on, so
  // MenuDashPanel needs to render its own (see `showNav` there).
  standalone?: boolean;
  // Session 76 (chat "deep link to the right dashboard" suggestions): pre-fills
  // MenuDashBody's search box for the few Top Menu items that are actually
  // query-capable today (Operations' "vehicles", any "documents" item) -- e.g.
  // clicking a chat suggestion for a specific VIN lands you already searched for it,
  // not just in the right department. Ignored by every other item.
  initialQuery?: string;
};

export function useMenuDash() {
  const [active, setActive] = useState<MenuDashItem | null>(null);
  const [poppedOut, setPoppedOut] = useState(false);
  const poppedWindowRef = useRef<Window | null>(null);

  function open(
    department: string,
    itemKey: string,
    kind: MenuDashKind = "menu",
    standalone: boolean = false,
    initialQuery?: string
  ) {
    setActive({ department, itemKey, kind, standalone, initialQuery });
    setPoppedOut(false);
  }

  function close() {
    setActive(null);
    setPoppedOut(false);
  }

  // Session 60, same reasoning as components/DepartmentWorkflowButtons.tsx's old
  // popOutWorkflow (session 57, now folded in here): the popped-out window makes its
  // own authenticated fetches off shared localStorage, no BroadcastChannel relay
  // needed. Popping out restores both the chat and Workspace columns in the main
  // window ("both columns return to normal"). Routes to a different pop-out page
  // depending on `kind` -- /panel/menudash for a Top Menu item,
  // /panel/workflow for a job-workflow window, "it stays static, and lets use the same
  // grey ui" only applies to the docked-in-page form; a real popped-out OS window is
  // still freely movable/resizable by the OS itself.
  function popOut() {
    if (!active) return;

    const existing = poppedWindowRef.current;
    if (existing && !existing.closed) {
      existing.focus();
      return;
    }

    const queryParam = active.initialQuery ? `&query=${encodeURIComponent(active.initialQuery)}` : "";

    const url =
      active.kind === "workflow"
        ? `/panel/workflow?department=${encodeURIComponent(active.department)}&key=${encodeURIComponent(active.itemKey)}`
        : active.kind === "account"
        ? `/panel/account?item=${encodeURIComponent(active.itemKey)}`
        : active.kind === "entity"
        ? `/panel/entity?id=${encodeURIComponent(active.itemKey)}`
        : `/panel/menudash?department=${encodeURIComponent(active.department)}&item=${encodeURIComponent(active.itemKey)}${queryParam}`;

    const popup = window.open(url, "dealeros_dash", "width=1100,height=760");

    if (popup) {
      poppedWindowRef.current = popup;
      setPoppedOut(true);
    }
  }

  return {
    active,
    poppedOut,
    open,
    close,
    popOut,
    // True whenever the Dash should take over the chat + Workspace columns in the
    // main window -- false either when nothing is open, or when it's been popped out
    // to its own OS window (in which case both columns show normally again).
    isCollapsing: !!active && !poppedOut,
  };
}

export type MenuDash = ReturnType<typeof useMenuDash>;
