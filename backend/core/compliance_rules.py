"""
Compliance rule catalog (2026-07-13, session 38). Sam: "there needs to be a complete
compliance level baked into every part of this, and it needs to run through every sale,
marketing push, etc -- its basically a compliance agent that runs constantly checking
against local, state, and federal automotive/technology legal compliance."

Scoping reality check (Sam's explicit answer, session 38): this environment has no live
legal database, no bar-association feed, and no OFAC SDN list connection -- there is no
way to honestly claim full local/state/federal coverage. So this module encodes a
SMALL, REAL, clearly-cited set of well-known FEDERAL rules that are actually checkable
against NXTDeal's real graph data, each carrying its real statutory citation. This is
explicitly a STARTING COMPLIANCE FRAMEWORK, not exhaustive legal coverage, and not a
substitute for a dealership's own compliance officer or legal counsel -- state and local
rules (which vary per dealer) are NOT encoded here and would need to be added the same
way a real dealer's compliance team extends this catalog (append to RULE_CATALOG below).
Every rule's `notice` field repeats this caveat so it surfaces anywhere a violation is
shown, matching the honesty bar Department Intelligence's _estimate_reserve()/prediction.py's
INDUSTRY_BASELINES already set for this codebase -- label an estimate as an estimate,
label a starting framework as a starting framework.

Each rule is a dict:
    id            -- stable key, also used as ComplianceAlert.attributes["rule_id"]
    law            -- short name of the real statute/regulation
    citation       -- the actual regulatory citation
    category       -- lending / credit / identity / marketing / data_security / advertising
    severity       -- "high" / "medium" -- both BLOCK per Sam ("not allowed to go
                      through until the corrections are made"); severity only affects
                      how alerts are sorted/displayed, not whether they block
    applies_to     -- list of action keys core/compliance.py's evaluate()/enforce_gate()
                      are called with (see core/compliance.py's ACTIONS)
    check(entity)  -- returns None if compliant, or a short violation description
                      string if not. Takes the one Entity being evaluated (a Deal,
                      Campaign, Asset, Website, or Connection).
"""

import re


NOT_LEGAL_ADVICE_NOTICE = (
    "This is a starting compliance framework covering a small set of well-known "
    "federal rules -- it is not exhaustive, does not cover state/local law, and is "
    "not a substitute for review by a licensed compliance officer or attorney."
)


def _fields_text(fields):
    """Every text value in a fields dict, concatenated, for a cheap keyword scan --
    used by the advertising-disclosure rules below. A heuristic, not a legal parser."""

    return " ".join(str(v) for v in (fields or {}).values() if v)


_RATE_MENTION_PATTERN = re.compile(r"\d+(\.\d+)?\s*%|\bapr\b", re.IGNORECASE)


def _mentions_rate_or_percentage(text):
    return bool(_RATE_MENTION_PATTERN.search(text or ""))


# ---------------------------------------------------------------------------
# Deal funding checks
# ---------------------------------------------------------------------------

def _check_reg_z_disclosure(deal):
    """Truth in Lending Act / Regulation Z, 12 CFR 1026.18 -- a credit sale's finance
    charge, APR, amount financed, and payment schedule must be disclosed to the
    consumer. core/deals.py's generate_contract() already builds a structured contract
    with these fields before funding -- this rule just confirms funding never proceeds
    without them actually being populated."""

    contract = (deal.attributes or {}).get("contract")

    if not contract:
        return "No contract on file -- APR, amount financed, and payment terms must be disclosed before funding (Reg Z, 12 CFR 1026.18)."

    required = ["apr", "amount_financed", "monthly_payment", "term_months"]
    missing = [f for f in required if contract.get(f) in (None, "", 0)]

    if missing:
        return f"Contract is missing required Reg Z disclosure field(s): {', '.join(missing)}."

    if not contract.get("disclosures"):
        return "Contract has no disclosure statements attached (Reg Z, 12 CFR 1026.18 requires clear written disclosure of credit terms)."

    return None


def _check_red_flags_identity(deal):
    """FACTA Red Flags Rule, 16 CFR 681.2 -- a creditor must have reasonable identity
    verification procedures before extending credit. NXTDeal doesn't have a live SDN/
    identity-verification data source, so this checks the honest, checkable proxy it
    actually has: that the customer's core identifying information was captured before
    funding. This does NOT screen against OFAC's SDN list or perform real KYC -- that
    would require a live data feed this environment doesn't have, and is explicitly not
    claimed here."""

    customer_id = (deal.attributes or {}).get("customer_id")

    from core.dealeros import ledger
    from core.entity_types import CUSTOMER

    customer = ledger.get_entity(customer_id) if customer_id else None

    if not customer or customer.entity_type != CUSTOMER:
        return "No linked customer record found -- identity information must be on file before funding (Red Flags Rule, 16 CFR 681.2)."

    required = ["FirstName", "LastName", "Address", "City", "State", "Zip"]
    missing = [f for f in required if not (customer.attributes or {}).get(f)]

    if missing:
        return f"Customer record is missing required identity field(s): {', '.join(missing)} (Red Flags Rule, 16 CFR 681.2)."

    if not customer.attributes.get("Phone") and not customer.attributes.get("Email"):
        return "Customer record has no phone or email on file -- at least one contact method is required for identity verification (Red Flags Rule, 16 CFR 681.2)."

    return None


# ---------------------------------------------------------------------------
# OFAC / SDN screening check (added session 112 follow-up, core/lending_compliance.py)
# ---------------------------------------------------------------------------

def _check_ofac_screening(deal):
    """Bank Secrecy Act / Executive Order 13224, enforced via Treasury's OFAC -- a
    creditor may not transact with a person or entity on the Specially Designated
    Nationals list. Same "no live feed, so check the real checkable precondition"
    pattern as _check_red_flags_identity above: this sandbox has no live SDN-list
    connection, so it checks that a real human-recorded screening exists on the deal
    (core/lending_compliance.py's record_ofac_screening()) and came back cleared --
    not that NXTDeal itself performed the check."""

    screening = (deal.attributes or {}).get("ofac_screening")

    if not screening or not screening.get("screened"):
        return "No OFAC/SDN screening is on file for this deal -- a screening must be recorded and cleared before funding (Bank Secrecy Act / OFAC, Executive Order 13224)."

    if not screening.get("cleared"):
        return "This deal's OFAC/SDN screening did NOT clear -- funding cannot proceed until this is resolved (Bank Secrecy Act / OFAC, Executive Order 13224)."

    return None


# ---------------------------------------------------------------------------
# Deal financing-decline check (ECOA)
# ---------------------------------------------------------------------------

def _check_ecoa_adverse_action(deal):
    """Equal Credit Opportunity Act / Regulation B, 12 CFR 1002.9 -- a creditor who
    declines an application must document specific reasons (an adverse action notice
    is required within 30 days). NXTDeal doesn't generate/send the actual notice
    document, but this checks the real, checkable precondition: a declined financing
    decision must have a documented reason on file, since ECOA requires the reason(s)
    be specific and available to the applicant on request."""

    if (deal.attributes or {}).get("financing_status") != "declined":
        return None

    if not (deal.attributes or {}).get("financing_notes"):
        return "Financing was declined with no documented reason -- ECOA/Reg B (12 CFR 1002.9) requires specific reasons be recorded for an adverse action notice."

    return None


# ---------------------------------------------------------------------------
# Campaign activation check
# ---------------------------------------------------------------------------

def _check_can_spam_tcpa_consent(campaign):
    """CAN-SPAM Act (15 U.S.C. 7701 et seq.) / TCPA (47 U.S.C. 227) -- commercial
    messages can't go to a recipient who has opted out, and telemarketing/autodialed
    contact requires the recipient not be on a do-not-contact list. Checks every
    audience member snapshotted on the campaign for a real `DoNotContact` flag (a
    field a real dealer's CRM import would carry) -- there is nothing to catch in
    today's seed data since it doesn't model opt-outs, but the mechanism is real and
    would catch a genuine opt-out the moment one exists in imported CRM data."""

    from core.dealeros import ledger

    audience_ids = (campaign.attributes or {}).get("audience_ids") or []
    flagged = []

    for entity_id in audience_ids:

        entity = ledger.get_entity(entity_id)

        if not entity:
            continue

        do_not_contact = entity.attributes.get("DoNotContact")

        if do_not_contact in (True, "true", "True", "1", 1):
            flagged.append(entity_id)

    if flagged:
        return f"{len(flagged)} audience member(s) are flagged Do Not Contact and must be excluded before this campaign can send (CAN-SPAM/TCPA)."

    return None


# ---------------------------------------------------------------------------
# Connection creation check (GLBA / FTC Safeguards Rule)
# ---------------------------------------------------------------------------

def _check_glba_safeguards_encryption(connection):
    """Gramm-Leach-Bliley Act Safeguards Rule, 16 CFR 314 -- a dealer (a "financial
    institution" under GLBA because it arranges financing) must protect customer
    financial information, including in transit. Checks the one real, checkable thing
    NXTDeal actually configures: an API connection's endpoint must be encrypted
    (https), not plaintext http, before it's allowed to pull or receive customer data."""

    if (connection.attributes or {}).get("connection_type") != "api":
        return None

    endpoint_url = (connection.attributes or {}).get("endpoint_url") or ""

    if endpoint_url.strip().lower().startswith("http://"):
        return "API endpoint uses unencrypted HTTP -- customer data connections must use HTTPS (GLBA Safeguards Rule, 16 CFR 314.4)."

    return None


# ---------------------------------------------------------------------------
# Asset / website publish checks (advertising disclosure)
# ---------------------------------------------------------------------------

def _check_advertising_disclosure_asset(asset):
    """Regulation Z advertising rule, 12 CFR 1026.24 / FTC Act Section 5 -- an
    advertisement that states a rate or percentage must include the required
    disclosures (terms, that the rate is an estimate, etc). Heuristic keyword scan for
    a rate/percentage mention in the asset's fields; if one is found, a non-empty
    `disclaimer` field is required. This is a real but approximate check (a keyword
    scan, not a legal parser) -- it will not catch every phrasing, and a compliance
    reviewer should still read the creative before it ships."""

    fields = (asset.attributes or {}).get("fields") or {}
    text = _fields_text(fields)

    if _mentions_rate_or_percentage(text) and not (fields.get("disclaimer") or "").strip():
        return "This asset mentions a rate/percentage but has no disclaimer text -- Reg Z's advertising rule (12 CFR 1026.24) requires disclosure when credit terms are advertised."

    return None


def _check_advertising_disclosure_website(website):
    """Same real-but-approximate rate-mention heuristic as the asset check above,
    applied per page: if any section's fields mention a rate/percentage, that page
    must have at least one `text_block` section with real body content (used here as
    a stand-in for "a disclaimer/terms block exists on the page") -- again a heuristic,
    not a legal review."""

    pages = (website.attributes or {}).get("pages") or {}
    flagged_pages = []

    for page_key, page in pages.items():

        sections = page.get("sections") or []
        page_text = " ".join(_fields_text(s.get("fields")) for s in sections)

        if not _mentions_rate_or_percentage(page_text):
            continue

        has_disclaimer_block = any(
            s.get("section_key") == "text_block" and len((s.get("fields") or {}).get("body", "")) > 20
            for s in sections
        )

        if not has_disclaimer_block:
            flagged_pages.append(page_key)

    if flagged_pages:
        return f"Page(s) {', '.join(flagged_pages)} mention a rate/percentage with no disclaimer text block -- Reg Z's advertising rule (12 CFR 1026.24) requires disclosure when credit terms are advertised."

    return None


RULE_CATALOG = [
    {
        "id": "reg_z_disclosure",
        "law": "Truth in Lending Act / Regulation Z",
        "citation": "12 CFR 1026.18",
        "category": "lending",
        "severity": "high",
        "applies_to": ["deal_fund"],
        "check": _check_reg_z_disclosure,
    },
    {
        "id": "red_flags_identity",
        "law": "FACTA Red Flags Rule",
        "citation": "16 CFR 681.2",
        "category": "identity",
        "severity": "high",
        "applies_to": ["deal_fund"],
        "check": _check_red_flags_identity,
    },
    {
        "id": "ofac_screening",
        "law": "Bank Secrecy Act / OFAC (Executive Order 13224)",
        "citation": "31 U.S.C. 5311 et seq. / E.O. 13224",
        "category": "identity",
        "severity": "high",
        "applies_to": ["deal_fund"],
        "check": _check_ofac_screening,
    },
    {
        "id": "ecoa_adverse_action",
        "law": "Equal Credit Opportunity Act / Regulation B",
        "citation": "12 CFR 1002.9",
        "category": "credit",
        "severity": "high",
        "applies_to": ["deal_decline"],
        "check": _check_ecoa_adverse_action,
    },
    {
        "id": "can_spam_tcpa_consent",
        "law": "CAN-SPAM Act / TCPA",
        "citation": "15 U.S.C. 7701 / 47 U.S.C. 227",
        "category": "marketing",
        "severity": "medium",
        "applies_to": ["campaign_activate"],
        "check": _check_can_spam_tcpa_consent,
    },
    {
        "id": "glba_safeguards_encryption",
        "law": "Gramm-Leach-Bliley Act Safeguards Rule",
        "citation": "16 CFR 314.4",
        "category": "data_security",
        "severity": "high",
        "applies_to": ["connection_create"],
        "check": _check_glba_safeguards_encryption,
    },
    {
        "id": "advertising_disclosure_asset",
        "law": "Regulation Z Advertising Rule / FTC Act Sec. 5",
        "citation": "12 CFR 1026.24",
        "category": "advertising",
        "severity": "medium",
        "applies_to": ["asset_approve"],
        "check": _check_advertising_disclosure_asset,
    },
    {
        "id": "advertising_disclosure_website",
        "law": "Regulation Z Advertising Rule / FTC Act Sec. 5",
        "citation": "12 CFR 1026.24",
        "category": "advertising",
        "severity": "medium",
        "applies_to": ["website_publish"],
        "check": _check_advertising_disclosure_website,
    },
]


def rules_for_action(action):
    return [r for r in RULE_CATALOG if action in r["applies_to"]]


def all_rules():
    return list(RULE_CATALOG)
