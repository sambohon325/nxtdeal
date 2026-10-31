"use client";

// Session 76 fifth follow-up. Sam, on the entity-ID links added the previous pass
// (components/MenuDashPanel.tsx's JsonValue, components/DepartmentWorkflowButtons.tsx's
// ValuePreview): "instead of clicking the link and it opening in a new tab - can it pop
// up in a modal when you hover over it, with the option to pop it out into a new window
// or to push into the dash / sub menu area."
//
// "Push into the dash" needs the CURRENT PAGE's own `useMenuDash()` instance -- the
// same hook that already drives the Top Menu / job-workflow / account Dash takeover --
// so a hovered entity link, however deep inside a recursively-rendered JSON tree, can
// open that entity in the exact same docked charcoal panel. Threading `menuDash` down
// as an explicit prop through JsonValue/ObjectListView/EntityEditCard (MenuDashPanel.tsx)
// and ValuePreview/ObjectTable/ListTable/SourceBlock/LiveDataPanel
// (DepartmentWorkflowButtons.tsx) would mean touching every one of those signatures for
// a single callback -- a much larger, riskier change than a small React Context
// provided once per page, right alongside where `menuDash` is already instantiated.
//
// "Pop out into a new window" deliberately does NOT go through this context or
// `menuDash.popOut()` -- see components/EntityHoverLink.tsx's module comment for why.
import { createContext, useContext, type ReactNode } from "react";

export type EntityLinkActions = {
  // Opens `entityId` in the current page's docked Dash takeover -- same charcoal panel
  // the Top Menu / job-workflow / account Dashes already use
  // (components/EntityDashPanel.tsx), replacing whatever Dash is currently open (if
  // any). Exactly "push into the dash / sub menu area."
  openInDash: (entityId: string) => void;
};

const EntityLinkActionsContext = createContext<EntityLinkActions | null>(null);

export function EntityLinkActionsProvider({
  openInDash,
  children,
}: {
  openInDash: (entityId: string) => void;
  children: ReactNode;
}) {
  return (
    <EntityLinkActionsContext.Provider value={{ openInDash }}>
      {children}
    </EntityLinkActionsContext.Provider>
  );
}

// Returns null outside a provider rather than throwing -- components/EntityHoverLink.tsx
// falls back to a plain "pop out only" experience wherever it's used without one (there
// isn't one today, but this keeps the component reusable without a hard dependency).
export function useEntityLinkActions(): EntityLinkActions | null {
  return useContext(EntityLinkActionsContext);
}
