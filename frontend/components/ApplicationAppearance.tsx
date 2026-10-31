"use client";

import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

/** Shared product styling. Dealer-branded customer journeys retain their own design. */
export function ApplicationAppearance({ children }: { children: ReactNode }) {
  const path = usePathname();
  const customerJourney = /^\/(site|pay|checkin|approve|purl)(\/|$)/.test(path);
  return <div className={path === "/" || customerJourney ? "contents" : "nxt-ui"}>{children}</div>;
}
