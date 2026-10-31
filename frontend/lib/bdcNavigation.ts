// Route person-level response work to BDC; Marketing retains demand planning and campaigns.
export function bdcDestination(department: string, key: string): string | null {
  const marketing: Record<string,string> = {conversations:"conversations",pipeline:"today",opportunities:"today",lead_import:"import"};
  const sales: Record<string,string> = {segments:"segments",sequences:"followups",communications:"conversations",tasks:"tasks",appointments:"appointments"};
  return (department === "Marketing" ? marketing : department === "Sales" ? sales : {})[key] || null;
}
