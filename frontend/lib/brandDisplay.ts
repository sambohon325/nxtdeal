/** Presentation alias for the historical built-in tenant; stored records are unchanged. */
export function dealerDisplayName(name: string | null | undefined): string {
  return (name ?? "").replace(/^DealerOS(?=\s*\((?:Primary|Dev)[^)]*\)$|$)/i, "NXTDeal");
}
