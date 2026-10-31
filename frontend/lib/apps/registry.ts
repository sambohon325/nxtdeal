// NXTDeal App Suite registry (2026-07-24).
//
// The suite is a set of mobile-first React web shells that live in the same Next.js
// frontend and map onto hub.dealeros.xyz/<slug> (e.g. hub.dealeros.xyz/salesapp). They are
// deliberately built as SHELLS first — the navigation, auth, and screen scaffolding for the
// whole suite is data-driven from this one file so new apps and screens are cheap to add and
// each screen can be deep-wired to the NXTDeal backend incrementally. Content here is drawn
// from the two product specs (Dealer OS Sales Platform, NXTDeal Service Experience Platform).
//
// Everything a shell needs to render — its identity, accent, audience, and the ordered list of
// tab screens with their placeholder sections — is described declaratively below. The dynamic
// route (app/apps/[slug]/page.tsx) reads this to mount any app; no per-app route code required.

export type AppAudience = "staff" | "customer" | "personal";
export type AppPlatform = "sales" | "service";

// A single card shown inside a screen — a titled block with a one-line summary and, optionally,
// a few example rows/features so the shell communicates intent without being wired to live data.
export type ScreenSection = {
  title: string;
  summary: string;
  items?: string[];
  // A soft "coming from NXTDeal" hint (e.g. which backend module feeds this once wired).
  source?: string;
};

export type AppScreen = {
  key: string;
  label: string;
  icon: string; // emoji used in the bottom tab bar
  heading: string;
  intro: string;
  sections: ScreenSection[];
};

export type AppDef = {
  slug: string; // hub.dealeros.xyz/<slug>
  name: string;
  tagline: string;
  platform: AppPlatform;
  audience: AppAudience;
  icon: string;
  accent: string; // tailwind color token stem, e.g. "indigo" | "teal"
  summary: string;
  // Does this app require a NXTDeal staff login (dealership id + username + password),
  // or is it a customer-facing shell where a lighter/no login applies?
  requiresStaffLogin: boolean;
  screens: AppScreen[];
};

// ---------------------------------------------------------------------------
// SALES PLATFORM
// ---------------------------------------------------------------------------

const SALES_PRO: AppDef = {
  slug: "mysales",
  name: "MySales",
  tagline: "Your career. Your workspace.",
  platform: "sales",
  audience: "personal",
  icon: "🚀",
  accent: "violet",
  requiresStaffLogin: false,
  summary:
    "Your personal contacts, follow-ups, profile page and assistant connections. Optional dealership inventory; no dealership account required to sign in.",
  screens: [
    {
      key: "today",
      label: "Today",
      icon: "📅",
      heading: "Today",
      intro: "Your day at a glance — who to call, what's hot, and what closes.",
      sections: [
        {
          title: "Follow-ups due",
          summary: "Review leads and customers with follow-ups due.",
          items: ["Overdue ups", "Warm leads cooling off", "Delivery + we-owes"],
          source: "leadScoring · customerJourney",
        },
        {
          title: "Pipeline snapshot",
          summary: "Deals in flight, gross forecast, and units to goal for the month.",
          source: "salesOverview",
        },
        {
          title: "Next actions",
          summary: "Review suggested actions before deciding how to follow up.",
          source: "aiAssist",
        },
      ],
    },
    {
      key: "customers",
      label: "Customers",
      icon: "👥",
      heading: "My customers",
      intro: "Every lead and customer you own, with full history and one-tap outreach.",
      sections: [
        {
          title: "Lead inbox",
          summary: "New ups routed to you, deduped against existing customers.",
          source: "leadRecord · upSystem",
        },
        {
          title: "Customer 360",
          summary: "Ownership, equity, service history, and lifetime value on one card.",
          source: "customer360",
        },
        {
          title: "One-tap outreach",
          summary: "Call, text, or email from the app — logged automatically to the ledger.",
          source: "communicationsHub",
        },
      ],
    },
    {
      key: "inventory",
      label: "Inventory",
      icon: "🚗",
      heading: "Inventory",
      intro: "Live lot inventory to search, share, and build a deal from anywhere.",
      sections: [
        {
          title: "Search the lot",
          summary: "Filter by make, model, price, and days-in-stock; see photos and window sticker.",
          source: "inventoryWorkspace",
        },
        {
          title: "Share to customer",
          summary: "Send a vehicle to a customer as a branded link off your personal page.",
          source: "purls",
        },
        {
          title: "Equity & trade",
          summary: "Spot upgrade opportunities from a customer's current payoff vs. book value.",
          source: "equityCenter",
        },
      ],
    },
    {
      key: "brand",
      label: "My Page",
      icon: "🌟",
      heading: "Personal brand page",
      intro: "Write your introduction and contact details for your personal page.",
      sections: [
        {
          title: "Your personal page",
          summary: "A public page customers can save, with your photo, bio, and contact.",
          source: "websites · purls",
        },
        {
          title: "Reviews & referrals",
          summary: "Collect reviews after delivery and track referral leads back to you.",
          source: "socialReputation · loyalty",
        },
        {
          title: "Share kit",
          summary: "QR code and share links for text signatures, socials, and business cards.",
        },
      ],
    },
    {
      key: "coach",
      label: "Conversations",
      icon: "💬",
      heading: "Conversations",
      intro: "Your recent calls and texts in one place.",
      sections: [
        {
          title: "Recent conversations",
          summary: "Review recent call and text activity, direction and status.",
          source: "customerComms",
        },
      ],
    },
    {
      key: "aiconfig",
      label: "AI Setup",
      icon: "⚙️",
      heading: "AI Setup",
      intro: "Manage assistant access through your personal MySales account.",
      sections: [
        { title: "Connections", summary: "Connect a supported assistant after provider setup is verified." },
        { title: "Permissions", summary: "Review exactly which personal records an assistant can access." },
        { title: "Activity", summary: "Review assistant actions and disconnect at any time." },
      ],
    },
    {
      key: "rewards",
      label: "Rewards",
      icon: "🎁",
      heading: "Referrals & rewards",
      intro: "Earn when you bring your store to NXTDeal and recruit other reps.",
      sections: [
        { title: "Refer your dealership", summary: "Get a reward when your store books a NXTDeal demo, and more when it converts.", source: "repReferrals" },
        { title: "Your referral code", summary: "Share it — earn when another salesperson joins MySales with it.", source: "repReferrals" },
        { title: "Rewards tracker", summary: "See what's pending and what you've earned across every referral.", source: "repReferrals" },
      ],
    },
    {
      key: "money",
      label: "Money",
      icon: "💰",
      heading: "My money",
      intro: "Your bank accounts and commissions together, with budgets and spending observations.",
      sections: [
        { title: "Bank accounts", summary: "Connect your bank with Plaid to see balances and spending.", source: "repFinance · plaid" },
        { title: "Budgets", summary: "Set monthly limits by category and track spend automatically.", source: "repFinance" },
        { title: "Commissions", summary: "Track projected, pending, and paid commissions next to your cash.", source: "repFinance" },
        { title: "Budget observations", summary: "Rules-based observations on recorded budgets and cash flow.", source: "repFinance" },
      ],
    },
  ],
};

const SALES: AppDef = {
  slug: "salesapp",
  name: "Sales",
  tagline: "The dealership sales floor, mobile",
  platform: "sales",
  audience: "staff",
  icon: "💼",
  accent: "blue",
  requiresStaffLogin: true,
  summary:
    "The dealer-managed sales app: shared pipeline, the up system, desking, and manager approvals — all synced to the single NXTDeal ledger.",
  screens: [
    {
      key: "pipeline",
      label: "Today & follow-ups",
      icon: "📊",
      heading: "Sales pipeline",
      intro: "Every open opportunity across the floor, by stage and by rep.",
      sections: [
        { title: "Stage board", summary: "Ups → working → desked → sold, with aging flags.", source: "salesOverview" },
        { title: "Forecast", summary: "Units and gross to goal for the store and each rep.", source: "readinessForecasts" },
        { title: "Lost-sale recovery", summary: "Review lost opportunities for a possible follow-up.", source: "lostSaleRecovery" },
      ],
    },
    {
      key: "ups",
      label: "Walk-ins & rotation",
      icon: "🙋",
      heading: "Up system",
      intro: "Log walk-ins and web leads and route them to the next rep in rotation.",
      sections: [
        { title: "Log an up", summary: "Capture a walk-in and check existing CRM records.", source: "upSystem" },
        { title: "Rotation", summary: "Fair round-robin with manager overrides and be-backs.", source: "bdc" },
        { title: "Lead routing", summary: "Web and marketplace leads assigned by source and skill.", source: "leadScoring" },
      ],
    },
    {
      key: "inventory",
      label: "Inventory",
      icon: "🚗",
      heading: "Inventory",
      intro: "The full lot with pricing, aging, and merchandising status.",
      sections: [
        { title: "Lot search", summary: "Every unit with photos, cost/price, and days in stock.", source: "inventoryWorkspace" },
        { title: "Pricing desk", summary: "Market-based pricing and price-drop suggestions.", source: "pricingDesk" },
        { title: "Aging & turn", summary: "Units past target age flagged for action.", source: "inventoryAging" },
      ],
    },
    {
      key: "desking",
      label: "Prepare a deal",
      icon: "🧮",
      heading: "Desking",
      intro: "Structure a deal — trade, terms, and F&I — and send for approval.",
      sections: [
        { title: "Deal builder", summary: "Payments, terms, and multiple scenarios side by side.", source: "deals" },
        { title: "Trade & payoff", summary: "Appraise the trade and pull the payoff into the deal.", source: "equityCenter" },
        { title: "Manager approval", summary: "Push for a T.O. and desk approval from the floor.", source: "managerTo · approvalCenter" },
      ],
    },
    {
      key: "messages",
      label: "Messages",
      icon: "💬",
      heading: "Messages",
      intro: "Unified customer conversations — text, email, and internal notes.",
      sections: [
        { title: "Conversations", summary: "One thread per customer across every channel.", source: "unifiedCommunications" },
        { title: "Reply drafts", summary: "Review prepared replies before sending through a connected provider.", source: "aiAssist · emailSms" },
        { title: "Team @mentions", summary: "Loop in a manager or F&I without leaving the thread.", source: "communications" },
      ],
    },
    {
      key: "aiconfig",
      label: "AI Setup",
      icon: "🤖",
      heading: "AI Setup",
      intro: "Choose how AI runs in this app — use your dealership's provider, bring your own key, or prefer on-device models.",
      sections: [
        { title: "Model routing", summary: "Your AI source resolves to on-device, BYOK, or dealer-managed per task.", source: "aiConfig · aiAssist" },
        { title: "On/off toggle", summary: "Turn AI off entirely for yourself.", source: "aiSpend" },
      ],
    },
  ],
};

const RECEPTION: AppDef = {
  slug: "reception",
  name: "Receptionist",
  tagline: "Front desk, meet the whole store",
  platform: "sales",
  audience: "staff",
  icon: "🛎️",
  accent: "amber",
  requiresStaffLogin: true,
  summary:
    "The front-desk app: record visitors, review appointments, find staff, and manage conversations.",
  screens: [
    {
      key: "checkin",
      label: "Check-In",
      icon: "✅",
      heading: "Visitor check-in",
      intro: "Capture who walked in and why, and start the up or appointment.",
      sections: [
        { title: "Greet & log", summary: "Name, reason for visit, and who they're here to see.", source: "checkin · upSystem" },
        { title: "Returning customer", summary: "Look up existing customer records when checking in a visitor.", source: "customer360" },
        { title: "Start an up", summary: "Hand a sales up straight into the rotation.", source: "upSystem" },
      ],
    },
    {
      key: "appointments",
      label: "Appointments",
      icon: "🗓️",
      heading: "Appointments",
      intro: "Today's sales and service appointments and who's arrived.",
      sections: [
        { title: "Today's schedule", summary: "Sales and service appointments in one timeline.", source: "appointments · appointmentScheduling" },
        { title: "Arrival board", summary: "Mark arrivals and alert the assigned employee.", source: "operationsScheduling" },
      ],
    },
    {
      key: "desk",
      label: "Phones",
      icon: "☎️",
      heading: "Front desk phones",
      intro: "Open customer calls and texts in the shared chat window. Live delivery requires a connected phone provider.",
      sections: [
        { title: "Search & dial", summary: "Find a customer in the CRM or dial any number.", source: "customerComms" },
        { title: "Call or text", summary: "Routes through the same chat window as the rest of NXTDeal.", source: "callCenter · communicationsHub" },
        { title: "Recent", summary: "Jump back into recent calls and texts.", source: "conversationIntelligence" },
      ],
    },
    {
      key: "team",
      label: "Team Chat",
      icon: "💬",
      heading: "In-dealership chat",
      intro: "Hand a visitor off to the right person — message any channel or staff member on the floor.",
      sections: [
        { title: "Channels", summary: "Store-wide channels for sales, service, and the front desk.", source: "messaging" },
        { title: "Staff DMs", summary: "Direct-message any employee that their visitor has arrived.", source: "messaging · adminUsers" },
      ],
    },
    {
      key: "directory",
      label: "Directory",
      icon: "📇",
      heading: "Who's in",
      intro: "The whole store's directory and availability, one tap to notify.",
      sections: [
        { title: "Staff directory", summary: "Departments, roles, and who's on the floor now.", source: "adminUsers" },
        { title: "Notify", summary: "Text or page any employee that their visitor is here.", source: "communicationsHub" },
        { title: "Route the visitor", summary: "Point the guest to the right desk or waiting area.", source: "operationsOverview" },
      ],
    },
    {
      key: "away",
      label: "Supervised lobby",
      icon: "🪧",
      heading: "Away from desk",
      intro: "Turn the tablet to face the lobby — visitors record their visit for the floor team.",
      sections: [
        { title: "Self check-in", summary: "The visitor enters their name, number, and who they need.", source: "upSystem" },
        { title: "Floor rotation", summary: "A recorded walk-in is assigned through the sales rotation.", source: "upSystem" },
      ],
    },
    {
      key: "aiconfig",
      label: "AI Setup",
      icon: "🤖",
      heading: "AI Setup",
      intro: "Choose how AI runs in this app — use your dealership's provider, bring your own key, or prefer on-device models.",
      sections: [
        { title: "Model routing", summary: "Your AI source resolves to on-device, BYOK, or dealer-managed per task.", source: "aiConfig · aiAssist" },
        { title: "On/off toggle", summary: "Turn AI off entirely for yourself.", source: "aiSpend" },
      ],
    },
  ],
};

const SHOWROOM: AppDef = {
  slug: "showroom",
  name: "Showroom",
  tagline: "Explore the showroom",
  platform: "sales",
  audience: "customer",
  icon: "🏬",
  accent: "emerald",
  requiresStaffLogin: false,
  summary:
    "Explore the showroom. Saved vehicles, online buying, and customer messaging are not available yet; contact the dealership for assistance.",
  screens: [
    {
      key: "browse",
      label: "Browse",
      icon: "🔎",
      heading: "Browse inventory",
      intro: "Search the dealership's live lot with photos, pricing, and payments.",
      sections: [
        { title: "Search & filter", summary: "By budget, body style, and monthly payment.", source: "inventoryWorkspace" },
        { title: "Payment preview", summary: "Estimated payments update as you shop.", source: "deals" },
      ],
    },
    {
      key: "saved",
      label: "Saved",
      icon: "❤️",
      heading: "Saved vehicles",
      intro: "Saving favorites, comparing saved vehicles, and price-drop alerts are not available yet.",
      sections: [
        { title: "Favorites", summary: "Everything you saved, with price-drop alerts.", source: "customerJourney" },
        { title: "Compare", summary: "Line up saved vehicles side by side.", source: "inventorySales" },
      ],
    },
    {
      key: "mydeal",
      label: "My Deal",
      icon: "🤝",
      heading: "My deal",
      intro: "Online buying is not available yet. Contact the dealership to discuss your purchase.",
      sections: [
        { title: "Start a deal", summary: "Pick terms and a trade to open a deal room.", source: "digitalRetail" },
        { title: "Verify it's you", summary: "The same tiered verification used on the public site.", source: "publicRetail" },
        { title: "Financing", summary: "Prequalify and pick a payment before you arrive.", source: "creditApp" },
      ],
    },
    {
      key: "messages",
      label: "Messages",
      icon: "💬",
      heading: "Messages",
      intro: "Customer messaging is not available yet. Please contact the dealership directly.",
      sections: [
        { title: "Chat with the store", summary: "One thread to your rep, synced to their app.", source: "unifiedCommunications" },
        { title: "Appointment", summary: "Book a test drive or delivery time.", source: "appointmentScheduling" },
      ],
    },
    {
      key: "aiconfig",
      label: "AI Assistant",
      icon: "🤖",
      heading: "AI Assistant",
      intro: "AI assistance in this app is managed by your dealership. Contact them for details about the AI provider in use.",
      sections: [],
    },
  ],
};

// ---------------------------------------------------------------------------
// SERVICE EXPERIENCE PLATFORM
// ---------------------------------------------------------------------------

const SERVICE_CUSTOMER: AppDef = {
  slug: "mygarage",
  name: "My Garage",
  tagline: "Your vehicles, service & showroom — one app",
  platform: "service",
  audience: "customer",
  icon: "🚗",
  accent: "teal",
  requiresStaffLogin: false,
  summary:
    "Customer service access is coming soon. For booking, vehicle updates, approvals, or messages, please contact the dealership.",
  screens: [
    {key: "offers", label: "Offers & coupons", icon: "◇", heading: "Offers & coupons", intro: "Current dealership events, service savings and featured inventory.", sections: []},
    { key: "rewards", label: "Rewards & Benefits", icon: "🎁", heading: "Rewards & Benefits", intro: "Your points and available rewards, together.", sections: [] },
    {
      key: "vehicles",
      label: "My Vehicles",
      icon: "🚙",
      heading: "My vehicles",
      intro: "Your garage — service, equity, and what your car is worth today.",
      sections: [
        { title: "Garage", summary: "Your vehicles, mileage, and warranty status.", source: "vehicleLifecycle" },
        { title: "Equity & trade-in value", summary: "What you owe vs. what your car is worth right now, and today's trade offer.", source: "equityCenter" },
        { title: "Service history", summary: "Past ROs and what's due next.", source: "repairOrders" },
        { title: "Recalls & recommendations", summary: "Review open recalls and maintenance recommendations.", source: "warrantyDesk" },
      ],
    },
    {
      key: "book",
      label: "Book service",
      icon: "📆",
      heading: "Book service",
      intro: "Online service booking is not available yet. Please contact the service desk to arrange an appointment.",
      sections: [
        { title: "Choose service", summary: "Menu pricing for common jobs and custom concerns.", source: "serviceOverview" },
        { title: "Pick a time", summary: "Live advisor and bay availability.", source: "appointmentScheduling" },
        { title: "Transport", summary: "Waiter, loaner, shuttle, or pickup & delivery.", source: "loanerShuttle" },
      ],
    },
    {
      key: "approvals",
      label: "Approvals",
      icon: "✍️",
      heading: "Approvals",
      intro: "Review and approve recommended work with photos and video.",
      sections: [
        { title: "Digital inspection", summary: "Tech photos/video with green-yellow-red findings.", source: "vehicleInspection" },
        { title: "Approve or defer", summary: "One-tap approve line items; defer the rest.", source: "repairOrders" },
        { title: "Pay", summary: "Pay the RO from your phone before pickup.", source: "payments" },
      ],
    },
    {
      key: "status",
      label: "Status",
      icon: "📍",
      heading: "Live status",
      intro: "Track your vehicle from check-in to ready-for-pickup in real time.",
      sections: [
        { title: "Where's my car", summary: "Stage-by-stage progress with ETA.", source: "shopControl" },
        { title: "Advisor updates", summary: "Push updates as the job moves.", source: "serviceCustomers" },
      ],
    },
    {
      key: "showroom",
      label: "Showroom",
      icon: "🏬",
      heading: "In stock now",
      intro: "Browse the dealership's live inventory — your next vehicle, whenever you're ready.",
      sections: [
        { title: "Browse inventory", summary: "Everything in stock, with pricing and payments.", source: "inventoryWorkspace" },
        { title: "Start a deal", summary: "Build and finance online from your phone.", source: "digitalRetail" },
      ],
    },
    {
      key: "alerts",
      label: "Alerts",
      icon: "🔔",
      heading: "Vehicle alerts",
      intro: "Saved searches, price-drop alerts, and new-arrival notifications are not available yet.",
      sections: [
        { title: "Saved searches", summary: "Make, model, price, and body style you want next.", source: "customerJourney" },
        { title: "Price-drop & new-arrival alerts", summary: "Get notified when a match arrives or a price drops.", source: "inventoryAging" },
      ],
    },
    {
      key: "messages",
      label: "Messages",
      icon: "💬",
      heading: "Messages",
      intro: "Customer messaging is not available yet. Please contact your advisor or salesperson directly.",
      sections: [
        { title: "Chat with your advisor", summary: "One thread, synced to the advisor's app.", source: "unifiedCommunications" },
      ],
    },
    {
      key: "aiconfig",
      label: "AI Assistant",
      icon: "🤖",
      heading: "AI Assistant",
      intro: "AI assistance in this app is managed by your dealership. Contact them for details about the AI provider in use.",
      sections: [],
    },
  ],
};

const KIOSK: AppDef = {
  slug: "kiosk",
  name: "Service Kiosk",
  tagline: "Self check-in for the service drive",
  platform: "service",
  audience: "customer",
  icon: "🖥️",
  accent: "cyan",
  requiresStaffLogin: false,
  summary:
    "Service-drive check-in using the private code from an appointment link. Ask the service desk for walk-in assistance.",
  screens: [
    {
      key: "checkin",
      label: "Check-In",
      icon: "✅",
      heading: "Self check-in",
      intro: "Enter your private appointment code to review and confirm your check-in.",
      sections: [
        { title: "Find appointment", summary: "Use the private check-in code from your appointment link.", source: "appointmentScheduling" },
        { title: "Confirm check-in", summary: "Choose waiting or drop-off and add contact details and notes.", source: "appointmentScheduling" },
        { title: "Walk-in assistance", summary: "Please see the service desk if you do not have an appointment code.", source: "serviceOverview" },
      ],
    },
    {
      key: "queue",
      label: "Waiting",
      icon: "⏳",
      heading: "Your appointment status",
      intro: "Use your private check-in code to review your appointment. Ask the service desk about your wait.",
      sections: [
        { title: "Your place in line", summary: "Live queue position and estimated wait.", source: "shopControl" },
        { title: "Advisor assignment", summary: "Matched to an available advisor and notified.", source: "operationsScheduling" },
      ],
    },
    {
      key: "amenities",
      label: "Lobby",
      icon: "☕",
      heading: "While you wait",
      intro: "Amenities, Wi-Fi, and status while you're in the lounge.",
      sections: [
        { title: "Amenities", summary: "Wi-Fi, coffee, and shuttle info.", },
        { title: "Status handoff", summary: "Continue tracking on your phone.", source: "serviceCustomers" },
      ],
    },
    {
      key: "aiconfig",
      label: "AI Assistant",
      icon: "🤖",
      heading: "AI Assistant",
      intro: "AI assistance in this app is managed by your dealership. Contact them for details about the AI provider in use.",
      sections: [],
    },
  ],
};

const SERVICE_OPS: AppDef = {
  slug: "serviceops",
  name: "Service Operations",
  tagline: "Advisor, technician, and manager — one app",
  platform: "service",
  audience: "staff",
  icon: "🛠️",
  accent: "slate",
  requiresStaffLogin: true,
  summary:
    "The staff service app with role modes for advisor, technician, and manager: run the RO board, do digital inspections, and manage the shop from the drive.",
  screens: [
    {
      key: "roboard",
      label: "Repair orders",
      icon: "📋",
      heading: "Repair order board",
      intro: "Every open RO by stage — the advisor's command center.",
      sections: [
        { title: "Open ROs", summary: "Check-in → dispatched → in progress → ready.", source: "repairOrders · shopControl" },
        { title: "Estimates & approvals", summary: "Build estimates and send for customer approval.", source: "vehicleInspection" },
        { title: "Status push", summary: "One tap keeps the customer app updated.", source: "serviceCustomers" },
      ],
    },
    {
      key: "inspections",
      label: "Inspections",
      icon: "📷",
      heading: "Digital inspections",
      intro: "The technician's inspection surface — photos, video, and findings.",
      sections: [
        { title: "Multi-point inspection", summary: "Green-yellow-red with photo/video evidence.", source: "vehicleInspection" },
        { title: "Recommendations", summary: "Attach jobs and parts to each finding.", source: "partsDesk" },
        { title: "Send to advisor", summary: "Push completed inspection back to the RO.", source: "repairOrders" },
      ],
    },
    {
      key: "techs",
      label: "Technician workload",
      icon: "🔩",
      heading: "Technician dispatch",
      intro: "Assign work, track flag hours, and watch bay throughput.",
      sections: [
        { title: "Dispatch", summary: "Assign ROs to techs by skill and load.", source: "shopControl" },
        { title: "Flag hours", summary: "Clock jobs and track efficiency vs. book time.", source: "repairOrders" },
        { title: "Parts status", summary: "See parts availability blocking a job.", source: "partsDesk" },
      ],
    },
    {
      key: "manager",
      label: "Service overview",
      icon: "📈",
      heading: "Manager view",
      intro: "Shop KPIs, effective labor rate, and CSI at a glance.",
      sections: [
        { title: "Shop KPIs", summary: "Hours per RO, ELR, and gross by advisor.", source: "serviceOverview · reportDashboard" },
        { title: "Throughput", summary: "Bay utilization and today's promised times.", source: "shopControl" },
        { title: "CSI & alerts", summary: "Customer satisfaction and jobs at risk.", source: "operationsAlerts" },
      ],
    },
    {
      key: "aiconfig",
      label: "AI Setup",
      icon: "🤖",
      heading: "AI Setup",
      intro: "Choose how AI runs in this app — use your dealership's provider, bring your own key, or prefer on-device models.",
      sections: [
        { title: "Model routing", summary: "Your AI source resolves to on-device, BYOK, or dealer-managed per task.", source: "aiConfig · aiAssist" },
        { title: "On/off toggle", summary: "Turn AI off entirely for yourself.", source: "aiSpend" },
      ],
    },
  ],
};

export const APP_SUITE: AppDef[] = [
  SALES_PRO,
  SALES,
  RECEPTION,
  SHOWROOM,
  SERVICE_CUSTOMER,
  KIOSK,
  SERVICE_OPS,
];

// DevHub: internal work-tracking app (not customer-facing, not in the public launcher).
// Shows the programming schedule, dashboard, and allows team members to update progress.
export const DEV_HUB: AppDef = {
  slug: "devhub",
  name: "DevHub",
  tagline: "Work tracking for the NXTDeal build.",
  platform: "sales",
  audience: "staff",
  icon: "🛠️",
  accent: "slate",
  requiresStaffLogin: true,
  summary:
    "Programming schedule, bug tracker, security issues, and production-bridge roadmap for the NXTDeal team.",
  screens: [
    {
      key: "dashboard",
      label: "Dashboard",
      icon: "📊",
      heading: "Programming Dashboard",
      intro: "Progress across all phases, issues by type and assignee, hours remaining.",
      sections: [
        { title: "Phase progress", summary: "Completion percentage per roadmap phase.", source: "programming_schedule" },
        { title: "Issues by type", summary: "Features, bugs, security issues, tech-debt counts.", source: "programming_schedule" },
        { title: "Work by assignee", summary: "Backend, frontend, devops, and sample-owned items.", source: "programming_schedule" },
      ],
    },
    {
      key: "items",
      label: "All Items",
      icon: "📋",
      heading: "Work Items",
      intro: "Browse and update features, bugs, and security issues across all phases.",
      sections: [
        { title: "Filtered list", summary: "List items by phase, status, priority, or assignee.", source: "programming_schedule" },
        { title: "Progress updates", summary: "Set progress, status, assignee, and log hours.", source: "programming_schedule" },
      ],
    },
    {
      key: "aiconfig",
      label: "AI Setup",
      icon: "🤖",
      heading: "AI Setup",
      intro: "Configure AI provider routing for yourself.",
      sections: [
        { title: "Model routing", summary: "Choose between on-device, BYOK, or dealer-managed AI.", source: "aiConfig" },
        { title: "On/off toggle", summary: "Turn AI off entirely for this app.", source: "aiConfig" },
      ],
    },
  ],
};

export function getApp(slug: string): AppDef | undefined {
  return APP_SUITE.find((a) => a.slug === slug);
}

// DevHub is a staff-only internal tool, not shown in the public companion launcher.
export const DEV_APPS: AppDef[] = [DEV_HUB];

export function getDevApp(slug: string): AppDef | undefined {
  return DEV_APPS.find((a) => a.slug === slug);
}

// All apps share ONE NXTDeal accent, driven by the `--app-accent` CSS variable that AppShell sets
// from the dealer's theme (lib/apps/appTheme.ts). Returning classes that READ that variable means a
// dealer's chosen brand color flows through every screen with zero per-component change — instead
// of the old per-app color. (Kept `accentOf(app)` so every existing call site works unchanged.)
export const APP_ACCENT = {
  bg: "bg-[var(--app-accent)]",
  text: "text-[var(--app-accent)]",
  ring: "ring-[var(--app-accent)]",
  soft: "bg-[color-mix(in_srgb,var(--app-accent)_16%,transparent)]",
  softText: "text-[var(--app-accent)]",
  tabActive: "text-[var(--app-accent)]",
};

export function accentOf(_app?: AppDef) {
  return APP_ACCENT;
}
