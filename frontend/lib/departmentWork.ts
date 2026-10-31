/** Plain-language introductions shared by every department working page. */
const introductions: Record<string,string> = {
 tasks:"See what needs attention, assign an owner, and track work through completion.",
 prospects:"Review new inquiries, follow up with customers, and move each opportunity forward.",
 contacts:"Find a customer, review their details, and pick up the conversation.",
 customers:"Review customer history and plan the next ownership or retention touchpoint.",
 inventory:"Find vehicles, review availability, and open the unit you need to work on.",
 vehicles:"Find vehicles, review their current status, and open a vehicle record.",
 appointments:"Review upcoming visits and keep each customer’s next step on track.",
 deals:"Review active deals, prepare figures, and keep the handoff moving.",
 reporting:"Review results, compare performance, and investigate the records behind the numbers.",
 alerts:"Review flagged issues and open the records that need attention.",
 compliance:"Review outstanding requirements and resolve the items holding work up.",
 documents:"Find documents, review their status, and open the relevant record.",
 employees:"Find staff records and review the details needed to support your team.",
 users:"Manage employee accounts and review their current access.",
 security:"Review account security and investigate access issues.",
 funding:"Track funding progress and review deals awaiting the next step.",
 titles:"Track title paperwork and resolve missing or outstanding requirements.",
 recon:"Review vehicle preparation and move each unit toward the front line.",
 pipeline:"See where opportunities stand and choose the next customer to follow up with.",
 communications:"Review conversations and keep customer follow-up moving.",
 workflows:"Review the available workflows and start the task you need.",
 scheduling:"Review the schedule and coordinate the next available slot.",
 inspections:"Review inspections and open the vehicles that need attention.",
 parts:"Review parts availability, requests, and orders awaiting action.",
 service:"Review service work and keep customers informed of the next step.",
};
export function departmentWorkDescription(key:string, title:string) {
 return introductions[key] || `Review ${title.toLowerCase()}, find the record you need, and continue your work.`;
}
