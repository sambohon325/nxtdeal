"""Requested product coverage, not claims of vendor access or certification.

Stable IDs preserve existing system records. Aliases help dealers find requested
product names; they never select endpoints, credentials or an adapter implicitly.
"""

CATEGORY_LABELS = {
    "dms": "Franchise DMS", "independent_bhph": "Independent / BHPH DMS",
    "crm": "CRM", "website": "Websites and inventory", "marketing": "Marketing",
    "accounting": "Accounting", "phone": "Phone and messaging",
    "payments_lending": "Payments and processing", "loan_servicing": "Loan servicing",
    "conversational_ai": "BDC and conversational tools", "inventory_valuation": "Inventory and valuation",
    "telematics": "GPS and telematics", "credit_reporting": "Credit reporting",
    "lending_networks": "Lender connections", "fixed_ops": "Service and fixed operations",
    "file": "CSV export",
}

GROUPS = {
    "dms": ["CDK/Fortellis", "Reynolds", "Tekion", "Dealertrack", "DealerBuilt", "Auto/Mate"],
    "independent_bhph": ["DealerCenter", "Frazer", "AutoManager DeskManager", "DealerSocket IDMS",
        "DealerSocket AutoStar", "Wayne Reaves", "Deal Pack", "Carsforsale.com", "Dabadu", "Desk-It",
        "DealerClick", "Auto Master Systems", "Finance Express", "Other independent/BHPH DMS"],
    "crm": ["Elead", "VinSolutions", "DriveCentric", "DealerSocket CRM", "HubSpot", "Salesforce", "Zoho",
        "AutoRaptor", "Selly Automotive", "DealerCenter CRM", "cyclCRM", "Other CRM"],
    "website": ["DealerOn", "Dealer.com", "Dealer Inspire", "AutoRevo", "Dealer Car Search", "Dealer Spike",
        "DealerCenter Web", "Carbase", "Other website/inventory provider"],
    "marketing": ["Google", "Meta", "Microsoft", "Mailchimp", "Fullpath", "AutoHook", "Other marketing platform"],
    "accounting": ["QuickBooks", "Xero", "Sage", "NetSuite", "Other accounting/ERP"],
    "phone": ["Twilio", "RingCentral", "CallRail", "Car Wars", "Convirza", "Podium", "Kenect", "SocketTalk",
        "Other phone/messaging provider"],
    "payments_lending": ["REPAY", "PayNearMe", "Speedpay", "Other loan servicing/payment system"],
    "loan_servicing": ["Megasys", "Nortridge Loan System", "Other loan servicing platform"],
    "conversational_ai": ["Impel", "Matador.ai", "CarNow Conversational AI", "Other BDC/conversational platform"],
    "inventory_valuation": ["vAuto", "MAX Digital", "Laser Appraiser", "Carbly", "Manheim MMR",
        "Kelley Blue Book", "Black Book", "CARFAX", "Other inventory/valuation provider"],
    "telematics": ["Spireon GoldStar", "PassTime GPS", "Procon Analytics", "Other GPS/telematics provider"],
    "credit_reporting": ["Datalinx Metro 2", "Equifax", "Experian", "TransUnion", "DMS bureau reporting module",
        "Other credit reporting provider"],
    "lending_networks": ["RouteOne", "Dealertrack Lender Network", "Other lender connection"],
    "fixed_ops": ["Dealer-FX", "Other fixed operations platform"],
}

ALIASES = {
    "CDK/Fortellis": ["CDK Global", "CDK"],
    "Reynolds": ["Reynolds and Reynolds", "ERA-IGNITE"],
    "Dealertrack": ["Dealertrack DMS"],
    "Deal Pack": ["ABCoA Deal Pack", "Deal Pack (ABCoA)"],
    "Auto Master Systems": ["AMS"],
    "DealerSocket CRM": ["DealerSocket"],
    "Nortridge Loan System": ["NLS", "Nortridge"],
    "Impel": ["SpinCar"],
    "Fullpath": ["AutoLeadStar"],
    "CarNow Conversational AI": ["CarNow"],
    "vAuto": ["Provision", "Conquest"],
    "MAX Digital": ["Max Digital"],
    "Manheim MMR": ["MMR"],
    "Kelley Blue Book": ["KBB"],
    "Spireon GoldStar": ["Spireon", "GoldStar"],
    "PassTime GPS": ["PassTime"],
    "Datalinx Metro 2": ["Datalinx", "Metro 2"],
}

# These are NXTDeal implementation intentions, not vendor-supported objects.
PLANNED_RECORD_TYPES = {
    "dms": ["Customer", "Vehicle", "Deal", "ServiceRecord", "JournalEntry"],
    "independent_bhph": ["Customer", "Vehicle", "FinanceContract", "LoanAccount", "Payment"],
    "crm": ["Customer", "Lead", "Communication", "Consent"],
    "website": ["Vehicle", "InventoryPrice", "Lead"],
    "marketing": ["Campaign", "Consent"], "accounting": ["AccountingAccount", "JournalEntry"],
    "phone": ["Communication", "Consent"], "payments_lending": ["Payment", "LoanAccount"],
    "loan_servicing": ["LoanAccount", "PaymentSchedule", "Payment", "CollectionCase", "Repossession"],
    "conversational_ai": ["Lead", "Communication", "Consent"],
    "inventory_valuation": ["Vehicle", "InventoryPrice"], "telematics": ["Vehicle", "Ownership"],
    "credit_reporting": ["LoanAccount"], "lending_networks": ["Deal", "FinanceContract"],
    "fixed_ops": ["ServiceRecord", "Appointment", "ServiceOperation", "Part"],
}

BOUNDARIES = {
    "telematics": "Read-only device/vehicle association planning. Location-event ingestion needs a dedicated schema and retention review. No locate, starter-interrupt, disable, recovery or other device commands.",
    "credit_reporting": "Read-only reporting-status planning. Bureau files, SSNs and raw credit reports are not accepted by a dedicated connector. No bureau pull, furnishing, dispute or submission actions.",
    "lending_networks": "Read-only source-deal/contract planning. No credit application submission, underwriting decision or lender action.",
    "payments_lending": "Payment observations only. No charge, refund, recurring draft or settlement instruction.",
    "loan_servicing": "Portfolio and schedule observations only. No balance recalculation, collection action or repossession instruction.",
    "conversational_ai": "Source communications and lead observations only. The vendor's AI is not a dependency of NXTDeal's integration agents; no autonomous messaging or enrollment.",
}

PRODUCT_NOTES = {
    "Desk-It": "Dealer-supplied product label; confirm the vendor, exact product and version before selecting an adapter.",
    "cyclCRM": "Dealer-supplied product spelling; confirm the official product and access documentation.",
    "Finance Express": "Confirm the deployed product/version and current access path; no current API availability is assumed.",
    "Fullpath": "Listed once for marketing/CDP planning; conversational use can be represented as a separate dealer system with its own scope.",
    "Deal Pack": "One stable catalog identity; a dealer may add separate DMS and servicing system instances with independent mappings and authorization.",
    "Dealer-FX": "Kept separate from AutoHook; a slash in a supplied software list does not establish shared access or a shared schema.",
    "Dealertrack Lender Network": "A separate product/access scope from the Dealertrack DMS entry.",
    "DMS bureau reporting module": "Name the actual DMS/module in the dealer system name. A DMS license does not establish bureau submission permission.",
}

# Dealer-requested discovery categories, not shared licenses or capabilities.
ADDITIONAL_DISCOVERY_CATEGORIES = {
    "Auto/Mate": ["independent_bhph"],
    "Deal Pack": ["loan_servicing"],
    "Fullpath": ["conversational_ai"],
}

CATALOG = {name: {
    "id": name, "category": category, "category_label": CATEGORY_LABELS[category],
    "discovery_categories": [category, *ADDITIONAL_DISCOVERY_CATEGORIES.get(name, [])],
    "status": "requires_vendor_access", "capabilities": [], "aliases": ALIASES.get(name, []),
    "planned_record_types": PLANNED_RECORD_TYPES[category],
    "planning_only": True, "writeback": "disabled",
    "boundary": BOUNDARIES.get(category, "Read-only source observations first. External writes require a separate operation-specific implementation and authorization."),
    "note": PRODUCT_NOTES.get(name),
    "next_step": "Confirm dealer authorization, exact product/version, vendor documentation and required access or certification; validate a dedicated adapter with authorized samples.",
} for category, names in GROUPS.items() for name in names}

CATALOG["CSV"] = {"id": "CSV", "category": "file", "category_label": CATEGORY_LABELS["file"],
    "discovery_categories": ["file"],
    "status": "available", "capabilities": ["discover", "schema", "sync", "health"],
    "aliases": [], "planned_record_types": [], "planning_only": False, "writeback": "disabled",
    "boundary": "Bounded authorized export intake; approval and activation remain separate human decisions.",
    "note": None, "next_step": "Upload a dealer-authorized export for discovery and review."}
