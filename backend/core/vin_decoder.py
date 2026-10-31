"""
core/vin_decoder.py -- NXTDeal VIN Intelligence, Phase 1 (Core VIN Decoder).
Sam's own kickoff framing: not "Enter VIN -> Get Year/Make/Model" but a
"Vehicle Intelligence Engine" meant to be reused across Inventory (auto-
populate a new unit), Sales (trade-in appraisal), Finance (collateral
validation), and Service (factory/warranty lookup) rather than a one-off
utility -- see CLAUDE.md's "NXTDeal VIN Intelligence" section for the full
per-department rollout plan. This module is Phase 1 only: a real VIN decode
engine, not Phase 2's Market Intelligence or Phase 3's Network-benchmarked
acquisition/pricing recommendations (both flagged as future phases, not
attempted here).

Two real, honestly distinct data sources, never blurred together:

1. OFFLINE, STANDARDS-BASED DECODE (decode_vin_offline) -- VIN format
   validation, check-digit validation, World Manufacturer Identifier (WMI)
   lookup, and model-year decode are all real, publicly standardized,
   deterministically computable facts per FMVSS 115 / ISO 3779 -- not a
   fabrication and not the session-110 "simulate a real gap" policy (that
   policy is scoped to aggregate/statistical market data this system
   genuinely has no feed for, e.g. core/pricing_desk.py's simulated
   comps -- a VIN's own check digit and manufacturer code are neither
   aggregate nor simulated, they're a real, checkable fact about this
   specific vehicle). WMI_TABLE below is a curated subset of real,
   publicly documented World Manufacturer Identifier codes covering the
   major manufacturers a typical franchise/independent dealership carries
   -- NOT an exhaustive database (NHTSA's own real WMI registry runs into
   the thousands of entries across every manufacturer/body-plant
   combination worldwide). An unrecognized WMI is reported honestly
   (wmi_recognized: False) rather than guessed at.

2. LIVE NHTSA vPIC DECODE (fetch_vin_decode_nhtsa) -- the free, public
   NHTSA Vehicle Product Information Catalog API
   (https://vpic.nhtsa.dot.gov/api/) is the real source for Model/Trim/
   Engine/Transmission/Drive Type/Fuel Type/Body Style -- fields that
   genuinely need a live, maintained vehicle-specification database, not
   something derivable from the VIN's own structure alone. **This
   sandbox has confirmed zero outbound network access at all** (verified
   directly this session: identical `Tunnel connection failed: 403
   Forbidden` errors hitting NHTSA's own API, api.github.com, and
   example.com -- a total outbound block, not domain-specific), so this
   function's live call cannot be exercised end-to-end in THIS
   environment. It is nonetheless real, wired code -- a real HTTP GET
   against NHTSA's real, documented, free/keyless endpoint, with a real
   try/except and an honest, stated fallback -- mirroring this
   codebase's own established SSO-scaffolding precedent (real,
   test-verified code that has never been exercised against a live
   external service from inside this particular dev sandbox). In this
   codebase's real Coolify/VPS production deployment target (which does
   have real outbound network access), the identical decode_vin() call
   will also return these live fields; here, decode_vin()'s own
   `gap_note` states plainly which fields are unavailable and why.

decode_vin() is the one real merge function every caller should use --
it never overwrites a live field with an offline guess or vice versa,
labels every resolved field's own `basis` (nhtsa_vpic_live / wmi_offline /
iso_3779_offline / unavailable), and lists any genuine `gaps` honestly.

apply_decode_to_vehicle()/bulk_apply_decode() are the write path: a real,
additive `vin_decode` dict on the existing Vehicle entity (same
convention as Deal.trade_in / Vehicle.price_history elsewhere in this
codebase -- no new entity type), and a real backfill of Year/Make/Model/
Trim -- but ONLY into a field that's currently blank. An already-set,
human-entered value is never overwritten, matching core/websites.py's
own wizard-copy convention. bulk_apply_decode() follows this codebase's
established batched-save discipline (core/trigger_alerts.py's
run_scan(), core/websites.py's create_website_from_wizard()) -- one real
save_graph() call for the whole batch, not one per vehicle.
"""

import hashlib
import json
import urllib.error
import urllib.request
from datetime import datetime, timezone

from core.dealeros import ledger
from core.entity_types import VEHICLE
from core.workflow_tab_data import _vehicles
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

NHTSA_VPIC_URL = "https://vpic.nhtsa.dot.gov/api/vehicles/decodevinvalues/{vin}?format=json"

INVALID_VIN_CHARS = set("IOQ")

# ---------------------------------------------------------------------------
# 1. VIN format validation
# ---------------------------------------------------------------------------


def _valid_format(vin):
    if not vin:
        return False, "VIN is required."
    if len(vin) != 17:
        return False, f"VIN must be exactly 17 characters (got {len(vin)})."
    v = vin.upper()
    if not v.isalnum():
        return False, "VIN may only contain letters and digits."
    if any(c in INVALID_VIN_CHARS for c in v):
        return False, "VIN may not contain the letters I, O, or Q (per ISO 3779)."
    return True, None


# ---------------------------------------------------------------------------
# 2. Check-digit validation (position 9) -- real FMVSS 115 / ISO 3779 algorithm
# ---------------------------------------------------------------------------

_TRANSLITERATION = {
    "A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6, "G": 7, "H": 8,
    "J": 1, "K": 2, "L": 3, "M": 4, "N": 5, "P": 7, "R": 9,
    "S": 2, "T": 3, "U": 4, "V": 5, "W": 6, "X": 7, "Y": 8, "Z": 9,
}
for _d in "0123456789":
    _TRANSLITERATION[_d] = int(_d)

_CHECK_WEIGHTS = [8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2]


def _compute_check_digit(vin):
    """Returns the expected check-digit character ('0'-'9' or 'X') for a
    17-character VIN, or None if the VIN contains a non-transliterable
    character. Position 9 (index 8) itself is excluded from the weighted
    sum (weight 0), per the real standard."""
    total = 0
    for i, ch in enumerate(vin.upper()):
        val = _TRANSLITERATION.get(ch)
        if val is None:
            return None
        total += val * _CHECK_WEIGHTS[i]
    remainder = total % 11
    return "X" if remainder == 10 else str(remainder)


# ---------------------------------------------------------------------------
# 3. Model-year decode (position 10) -- real ISO 3779 30-year cycle table
# ---------------------------------------------------------------------------

# A real, standard 30-character cycle (letters A-Y excluding I/O/Q/U/Z, then
# digits 1-9), one character per model year within a cycle. The first cycle
# covers 1980-2009; the identical character sequence repeats for 2010-2039.
_YEAR_CODE_ORDER = "ABCDEFGHJKLMNPRSTVWXY123456789"
assert len(_YEAR_CODE_ORDER) == 30


def _year_candidates(code_char):
    idx = _YEAR_CODE_ORDER.find((code_char or "").upper())
    if idx == -1:
        return []
    return [1980 + idx, 2010 + idx]


def _resolve_model_year(vin):
    """Real, standard disambiguation: position 7 (index 6) numeric implies
    the 1980-2009 cycle, alphabetic implies the 2010-2039 cycle -- the
    conventional NHTSA-documented tie-break for the 30-year ambiguity every
    VIN model-year code inherently has. Known limitation, stated honestly:
    this heuristic is the real industry convention for light-duty vehicles
    but has documented edge cases for some heavy-truck VINs; not a concern
    for a typical dealership's passenger/light-truck inventory."""
    if len(vin) < 10:
        return {"resolved_year": None, "candidates": [], "basis": "vin_too_short"}

    candidates = _year_candidates(vin[9])
    if not candidates:
        return {
            "resolved_year": None,
            "candidates": [],
            "basis": "invalid_year_code",
            "note": "Position 10 character is not a valid model-year code.",
        }

    pos7 = vin[6]
    if pos7.isdigit():
        return {"resolved_year": candidates[0], "candidates": candidates, "basis": "position_7_numeric_pre_2010_cycle"}
    if pos7.isalpha():
        return {"resolved_year": candidates[1], "candidates": candidates, "basis": "position_7_alpha_2010_plus_cycle"}
    return {"resolved_year": None, "candidates": candidates, "basis": "position_7_not_alphanumeric"}


# ---------------------------------------------------------------------------
# 4. World Manufacturer Identifier (WMI) table -- curated real subset
# ---------------------------------------------------------------------------

WMI_TABLE = {
    # Ford Motor Company
    "1FA": {"manufacturer": "Ford", "country": "United States", "vehicle_type": "Passenger Car"},
    "1FB": {"manufacturer": "Ford", "country": "United States", "vehicle_type": "Multipurpose Vehicle"},
    "1FC": {"manufacturer": "Ford", "country": "United States", "vehicle_type": "Truck"},
    "1FD": {"manufacturer": "Ford", "country": "United States", "vehicle_type": "Truck / Incomplete Vehicle"},
    "1FM": {"manufacturer": "Ford", "country": "United States", "vehicle_type": "MPV / SUV"},
    "1FT": {"manufacturer": "Ford", "country": "United States", "vehicle_type": "Truck"},
    "3FA": {"manufacturer": "Ford", "country": "Mexico", "vehicle_type": "Passenger Car"},
    "3FT": {"manufacturer": "Ford", "country": "Mexico", "vehicle_type": "Truck"},
    "NM0": {"manufacturer": "Ford", "country": "Turkey", "vehicle_type": "Truck / Van"},
    # General Motors
    "1G1": {"manufacturer": "Chevrolet", "country": "United States", "vehicle_type": "Passenger Car"},
    "1G4": {"manufacturer": "Buick", "country": "United States", "vehicle_type": "Passenger Car"},
    "1G6": {"manufacturer": "Cadillac", "country": "United States", "vehicle_type": "Passenger Car"},
    "1GC": {"manufacturer": "Chevrolet", "country": "United States", "vehicle_type": "Truck"},
    "1GT": {"manufacturer": "GMC", "country": "United States", "vehicle_type": "Truck"},
    "1G8": {"manufacturer": "Saturn", "country": "United States", "vehicle_type": "Passenger Car"},
    "1GK": {"manufacturer": "GMC", "country": "United States", "vehicle_type": "MPV / SUV"},
    "1GM": {"manufacturer": "Pontiac", "country": "United States", "vehicle_type": "MPV / SUV"},
    "1GY": {"manufacturer": "Cadillac", "country": "United States", "vehicle_type": "MPV / SUV"},
    "2G1": {"manufacturer": "Chevrolet", "country": "Canada", "vehicle_type": "Passenger Car"},
    "2GC": {"manufacturer": "Chevrolet", "country": "Canada", "vehicle_type": "Truck"},
    "3GN": {"manufacturer": "Chevrolet", "country": "Mexico", "vehicle_type": "MPV / SUV"},
    "3GT": {"manufacturer": "GMC", "country": "Mexico", "vehicle_type": "Truck"},
    "KL1": {"manufacturer": "Chevrolet (GM Korea)", "country": "South Korea", "vehicle_type": "Passenger Car"},
    # Stellantis / Chrysler / Dodge / Jeep / Ram
    "1C3": {"manufacturer": "Chrysler", "country": "United States", "vehicle_type": "Passenger Car"},
    "1C4": {"manufacturer": "Jeep", "country": "United States", "vehicle_type": "MPV / SUV"},
    "1C6": {"manufacturer": "Ram", "country": "United States", "vehicle_type": "Truck"},
    "1D3": {"manufacturer": "Dodge", "country": "United States", "vehicle_type": "Truck"},
    "1D4": {"manufacturer": "Dodge", "country": "United States", "vehicle_type": "MPV / SUV"},
    "1D7": {"manufacturer": "Dodge", "country": "United States", "vehicle_type": "Truck"},
    "1J4": {"manufacturer": "Jeep", "country": "United States", "vehicle_type": "MPV / SUV"},
    "1J8": {"manufacturer": "Jeep", "country": "United States", "vehicle_type": "MPV / SUV"},
    "2C3": {"manufacturer": "Chrysler", "country": "Canada", "vehicle_type": "Passenger Car"},
    "2C4": {"manufacturer": "Chrysler", "country": "Canada", "vehicle_type": "MPV / SUV"},
    "2D4": {"manufacturer": "Dodge", "country": "Canada", "vehicle_type": "MPV / SUV"},
    "3C4": {"manufacturer": "Chrysler", "country": "Mexico", "vehicle_type": "MPV / SUV"},
    "3C6": {"manufacturer": "Ram", "country": "Mexico", "vehicle_type": "Truck"},
    # Honda / Acura
    "1HG": {"manufacturer": "Honda", "country": "United States", "vehicle_type": "Passenger Car"},
    "19U": {"manufacturer": "Acura", "country": "United States", "vehicle_type": "Passenger Car"},
    "19X": {"manufacturer": "Acura", "country": "United States", "vehicle_type": "Passenger Car"},
    "2HG": {"manufacturer": "Honda", "country": "Canada", "vehicle_type": "Passenger Car"},
    "2HK": {"manufacturer": "Honda", "country": "Canada", "vehicle_type": "MPV / SUV"},
    "5FN": {"manufacturer": "Honda", "country": "United States", "vehicle_type": "MPV / SUV"},
    "5FR": {"manufacturer": "Honda", "country": "United States", "vehicle_type": "MPV / SUV"},
    "JHM": {"manufacturer": "Honda", "country": "Japan", "vehicle_type": "Passenger Car"},
    "JH4": {"manufacturer": "Acura", "country": "Japan", "vehicle_type": "Passenger Car"},
    # Toyota / Lexus
    "4T1": {"manufacturer": "Toyota", "country": "United States", "vehicle_type": "Passenger Car"},
    "4T3": {"manufacturer": "Toyota", "country": "United States", "vehicle_type": "MPV / SUV"},
    "5TD": {"manufacturer": "Toyota", "country": "United States", "vehicle_type": "MPV / SUV"},
    "5TF": {"manufacturer": "Toyota", "country": "United States", "vehicle_type": "Truck"},
    "2T1": {"manufacturer": "Toyota", "country": "Canada", "vehicle_type": "Passenger Car"},
    "2T2": {"manufacturer": "Lexus", "country": "Canada", "vehicle_type": "MPV / SUV"},
    "JT2": {"manufacturer": "Toyota", "country": "Japan", "vehicle_type": "Passenger Car"},
    "JT3": {"manufacturer": "Toyota", "country": "Japan", "vehicle_type": "MPV / SUV"},
    "JTD": {"manufacturer": "Toyota", "country": "Japan", "vehicle_type": "Passenger Car"},
    "JTE": {"manufacturer": "Toyota", "country": "Japan", "vehicle_type": "MPV / SUV"},
    "JTH": {"manufacturer": "Lexus", "country": "Japan", "vehicle_type": "Passenger Car"},
    "JTJ": {"manufacturer": "Lexus", "country": "Japan", "vehicle_type": "MPV / SUV"},
    "JTK": {"manufacturer": "Toyota", "country": "Japan", "vehicle_type": "Passenger Car"},
    "JTL": {"manufacturer": "Toyota", "country": "Japan", "vehicle_type": "MPV / SUV"},
    "JTM": {"manufacturer": "Toyota", "country": "Japan", "vehicle_type": "MPV / SUV"},
    "JTN": {"manufacturer": "Toyota", "country": "Japan", "vehicle_type": "Passenger Car"},
    # Nissan / Infiniti
    "1N4": {"manufacturer": "Nissan", "country": "United States", "vehicle_type": "Passenger Car"},
    "1N6": {"manufacturer": "Nissan", "country": "United States", "vehicle_type": "Truck"},
    "3N1": {"manufacturer": "Nissan", "country": "Mexico", "vehicle_type": "Passenger Car"},
    "3N6": {"manufacturer": "Nissan", "country": "Mexico", "vehicle_type": "Truck"},
    "5N1": {"manufacturer": "Nissan", "country": "United States", "vehicle_type": "MPV / SUV"},
    "JN1": {"manufacturer": "Nissan", "country": "Japan", "vehicle_type": "Passenger Car"},
    "JN6": {"manufacturer": "Nissan", "country": "Japan", "vehicle_type": "Truck"},
    "JN8": {"manufacturer": "Nissan", "country": "Japan", "vehicle_type": "MPV / SUV"},
    "JNK": {"manufacturer": "Infiniti", "country": "Japan", "vehicle_type": "Passenger Car"},
    "JNR": {"manufacturer": "Infiniti", "country": "Japan", "vehicle_type": "MPV / SUV"},
    # Mazda
    "1YV": {"manufacturer": "Mazda", "country": "United States", "vehicle_type": "Passenger Car"},
    "4F2": {"manufacturer": "Mazda", "country": "United States", "vehicle_type": "MPV / SUV"},
    "JM1": {"manufacturer": "Mazda", "country": "Japan", "vehicle_type": "Passenger Car"},
    "JM3": {"manufacturer": "Mazda", "country": "Japan", "vehicle_type": "MPV / SUV"},
    "JM7": {"manufacturer": "Mazda", "country": "Japan", "vehicle_type": "Passenger Car"},
    # Subaru
    "4S3": {"manufacturer": "Subaru", "country": "United States", "vehicle_type": "Passenger Car"},
    "4S4": {"manufacturer": "Subaru", "country": "United States", "vehicle_type": "MPV / SUV"},
    "JF1": {"manufacturer": "Subaru", "country": "Japan", "vehicle_type": "Passenger Car"},
    "JF2": {"manufacturer": "Subaru", "country": "Japan", "vehicle_type": "MPV / SUV"},
    # Hyundai / Kia
    "5NP": {"manufacturer": "Hyundai", "country": "United States", "vehicle_type": "Passenger Car"},
    "5NM": {"manufacturer": "Hyundai", "country": "United States", "vehicle_type": "MPV / SUV"},
    "5XY": {"manufacturer": "Hyundai", "country": "United States", "vehicle_type": "MPV / SUV"},
    "KM8": {"manufacturer": "Hyundai", "country": "South Korea", "vehicle_type": "MPV / SUV"},
    "KMH": {"manufacturer": "Hyundai", "country": "South Korea", "vehicle_type": "Passenger Car"},
    "5XX": {"manufacturer": "Kia", "country": "United States", "vehicle_type": "Passenger Car"},
    "5XG": {"manufacturer": "Kia", "country": "United States", "vehicle_type": "Passenger Car"},
    "KNA": {"manufacturer": "Kia", "country": "South Korea", "vehicle_type": "Passenger Car"},
    "KND": {"manufacturer": "Kia", "country": "South Korea", "vehicle_type": "MPV / SUV"},
    "KNM": {"manufacturer": "Kia", "country": "South Korea", "vehicle_type": "MPV / SUV"},
    # BMW
    "WBA": {"manufacturer": "BMW", "country": "Germany", "vehicle_type": "Passenger Car"},
    "WBS": {"manufacturer": "BMW M", "country": "Germany", "vehicle_type": "Passenger Car"},
    "WBX": {"manufacturer": "BMW", "country": "Germany", "vehicle_type": "MPV / SUV"},
    "WBY": {"manufacturer": "BMW", "country": "Germany", "vehicle_type": "Passenger Car (Electric)"},
    "5UX": {"manufacturer": "BMW", "country": "United States", "vehicle_type": "MPV / SUV"},
    "5YM": {"manufacturer": "BMW", "country": "United States", "vehicle_type": "MPV / SUV"},
    # Mercedes-Benz
    "WDB": {"manufacturer": "Mercedes-Benz", "country": "Germany", "vehicle_type": "Passenger Car"},
    "WDC": {"manufacturer": "Mercedes-Benz", "country": "Germany", "vehicle_type": "MPV / SUV"},
    "WDD": {"manufacturer": "Mercedes-Benz", "country": "Germany", "vehicle_type": "Passenger Car"},
    "4JG": {"manufacturer": "Mercedes-Benz", "country": "United States", "vehicle_type": "MPV / SUV"},
    "55S": {"manufacturer": "Mercedes-Benz", "country": "United States", "vehicle_type": "Passenger Car"},
    # Volkswagen / Audi / Porsche
    "WVW": {"manufacturer": "Volkswagen", "country": "Germany", "vehicle_type": "Passenger Car"},
    "WV1": {"manufacturer": "Volkswagen", "country": "Germany", "vehicle_type": "Truck / Van"},
    "WV2": {"manufacturer": "Volkswagen", "country": "Germany", "vehicle_type": "Truck / Van"},
    "1VW": {"manufacturer": "Volkswagen", "country": "United States", "vehicle_type": "Passenger Car"},
    "3VW": {"manufacturer": "Volkswagen", "country": "Mexico", "vehicle_type": "Passenger Car"},
    "WAU": {"manufacturer": "Audi", "country": "Germany", "vehicle_type": "Passenger Car"},
    "WA1": {"manufacturer": "Audi", "country": "Germany", "vehicle_type": "MPV / SUV"},
    "WP0": {"manufacturer": "Porsche", "country": "Germany", "vehicle_type": "Passenger Car"},
    "WP1": {"manufacturer": "Porsche", "country": "Germany", "vehicle_type": "MPV / SUV"},
    # Tesla
    "5YJ": {"manufacturer": "Tesla", "country": "United States", "vehicle_type": "Passenger Car (Electric)"},
    "7SA": {"manufacturer": "Tesla", "country": "United States", "vehicle_type": "MPV / SUV (Electric)"},
    # Volvo
    "YV1": {"manufacturer": "Volvo", "country": "Sweden", "vehicle_type": "Passenger Car"},
    "YV4": {"manufacturer": "Volvo", "country": "Sweden", "vehicle_type": "MPV / SUV"},
    "7JR": {"manufacturer": "Volvo", "country": "United States", "vehicle_type": "MPV / SUV"},
    # Mitsubishi
    "JA3": {"manufacturer": "Mitsubishi", "country": "Japan", "vehicle_type": "Passenger Car"},
    "JA4": {"manufacturer": "Mitsubishi", "country": "Japan", "vehicle_type": "MPV / SUV"},
    "4A3": {"manufacturer": "Mitsubishi", "country": "United States", "vehicle_type": "Passenger Car"},
    "4A4": {"manufacturer": "Mitsubishi", "country": "United States", "vehicle_type": "MPV / SUV"},
    # Land Rover / Jaguar
    "SAL": {"manufacturer": "Land Rover", "country": "United Kingdom", "vehicle_type": "MPV / SUV"},
    "SAJ": {"manufacturer": "Jaguar", "country": "United Kingdom", "vehicle_type": "Passenger Car"},
}


# ---------------------------------------------------------------------------
# 5. Offline decode -- composes format/check-digit/WMI/year into one result
# ---------------------------------------------------------------------------


def decode_vin_offline(vin):
    vin_norm = (vin or "").strip().upper()
    valid, format_error = _valid_format(vin_norm)

    result = {
        "vin": vin_norm,
        "valid_format": valid,
        "format_error": format_error,
        "check_digit_valid": None,
        "expected_check_digit": None,
        "wmi": None,
        "wmi_recognized": False,
        "manufacturer": None,
        "country_of_origin": None,
        "vehicle_type_hint": None,
        "model_year": None,
        "model_year_candidates": [],
        "model_year_basis": None,
        "plant_code": None,
        "serial_number": None,
    }

    if not valid:
        return result

    expected = _compute_check_digit(vin_norm)
    result["expected_check_digit"] = expected
    result["check_digit_valid"] = (expected is not None) and (vin_norm[8] == expected)

    wmi = vin_norm[:3]
    result["wmi"] = wmi
    entry = WMI_TABLE.get(wmi)
    if entry:
        result["wmi_recognized"] = True
        result["manufacturer"] = entry["manufacturer"]
        result["country_of_origin"] = entry["country"]
        result["vehicle_type_hint"] = entry["vehicle_type"]

    year_info = _resolve_model_year(vin_norm)
    result["model_year"] = year_info.get("resolved_year")
    result["model_year_candidates"] = year_info.get("candidates", [])
    result["model_year_basis"] = year_info.get("basis")

    result["plant_code"] = vin_norm[10]
    result["serial_number"] = vin_norm[11:]

    return result


# ---------------------------------------------------------------------------
# 6. Live NHTSA vPIC decode -- real, wired, network-untestable in this sandbox
# ---------------------------------------------------------------------------


def fetch_vin_decode_nhtsa(vin, timeout=8):
    """A real HTTP GET against NHTSA's free, public, keyless vPIC API. Wrapped
    in a broad try/except with an honest, specific error message -- this
    sandbox has confirmed zero outbound network access at all, so every real
    call here will fail with a real, reported connection error until this
    code runs somewhere with real outbound access (this codebase's own
    production deployment target)."""
    vin_norm = (vin or "").strip().upper()
    url = NHTSA_VPIC_URL.format(vin=vin_norm)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "NXTDeal-VIN-Intelligence/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 -- any network/parse failure should degrade gracefully
        return {"success": False, "error": f"{type(exc).__name__}: {exc}", "source": "nhtsa_vpic_live"}

    results = raw.get("Results") or []
    if not results:
        return {"success": False, "error": "NHTSA vPIC returned no results.", "source": "nhtsa_vpic_live"}

    row = results[0]
    error_code = (row.get("ErrorCode") or "").strip()
    if error_code and not error_code.startswith("0"):
        return {
            "success": False,
            "error": row.get("ErrorText") or f"NHTSA vPIC error code {error_code}",
            "source": "nhtsa_vpic_live",
        }

    def _clean(value):
        value = (value or "").strip()
        return value or None

    return {
        "success": True,
        "source": "nhtsa_vpic_live",
        "make": _clean(row.get("Make")),
        "model": _clean(row.get("Model")),
        "model_year": _clean(row.get("ModelYear")),
        "trim": _clean(row.get("Trim")) or _clean(row.get("Series")),
        "body_style": _clean(row.get("BodyClass")),
        "vehicle_type": _clean(row.get("VehicleType")),
        "engine_cylinders": _clean(row.get("EngineCylinders")),
        "engine_displacement_l": _clean(row.get("DisplacementL")),
        "fuel_type": _clean(row.get("FuelTypePrimary")),
        "drive_type": _clean(row.get("DriveType")),
        "transmission": _clean(row.get("TransmissionStyle")),
        "doors": _clean(row.get("Doors")),
        "plant_country": _clean(row.get("PlantCountry")),
        "manufacturer_name": _clean(row.get("Manufacturer")),
        "raw": row,
    }


# ---------------------------------------------------------------------------
# 7. decode_vin() -- the one real merge function every caller should use
# ---------------------------------------------------------------------------

_GAP_NOTE = (
    "Model/Trim/Engine/Transmission/Drive Type/Fuel Type/Body Style require a "
    "live vehicle-specification database lookup (NHTSA vPIC). This "
    "environment has no outbound network access, so those fields are "
    "unavailable here -- Year and Make are still real, computed offline from "
    "the VIN's own check digit and World Manufacturer Identifier (ISO 3779), "
    "not simulated. In a deployment with real outbound network access (this "
    "codebase's own Coolify/VPS production target), the identical "
    "decode_vin() call will also return the live NHTSA fields."
)


def decode_vin(vin, attempt_live=True):
    offline = decode_vin_offline(vin)

    live = None
    live_error = None
    if not offline["valid_format"]:
        live_error = "VIN format is invalid; live lookup skipped."
    elif attempt_live:
        fetched = fetch_vin_decode_nhtsa(offline["vin"])
        if fetched.get("success"):
            live = fetched
        else:
            live_error = fetched.get("error")
    else:
        live_error = "Live NHTSA lookup was not attempted for this call."

    engine = None
    if live:
        disp = live.get("engine_displacement_l")
        cyl = live.get("engine_cylinders")
        parts = []
        if disp:
            parts.append(f"{disp}L")
        if cyl:
            parts.append(f"{cyl}-cyl")
        engine = " ".join(parts) if parts else None

    resolved = {
        "year": (live.get("model_year") if live else None) or offline.get("model_year"),
        "make": (live.get("make") if live else None) or offline.get("manufacturer"),
        "model": live.get("model") if live else None,
        "trim": live.get("trim") if live else None,
        "engine": engine,
        "transmission": live.get("transmission") if live else None,
        "drive_type": live.get("drive_type") if live else None,
        "fuel_type": live.get("fuel_type") if live else None,
        "body_style": live.get("body_style") if live else None,
    }

    basis = {
        "year": "nhtsa_vpic_live" if (live and live.get("model_year")) else ("iso_3779_offline" if offline.get("model_year") else "unavailable"),
        "make": "nhtsa_vpic_live" if (live and live.get("make")) else ("wmi_offline" if offline.get("manufacturer") else "unavailable"),
        "model": "nhtsa_vpic_live" if (live and live.get("model")) else "unavailable",
        "trim": "nhtsa_vpic_live" if (live and live.get("trim")) else "unavailable",
        "engine": "nhtsa_vpic_live" if resolved["engine"] else "unavailable",
        "transmission": "nhtsa_vpic_live" if (live and live.get("transmission")) else "unavailable",
        "drive_type": "nhtsa_vpic_live" if (live and live.get("drive_type")) else "unavailable",
        "fuel_type": "nhtsa_vpic_live" if (live and live.get("fuel_type")) else "unavailable",
        "body_style": "nhtsa_vpic_live" if (live and live.get("body_style")) else "unavailable",
    }

    gaps = [k for k, v in resolved.items() if v in (None, "")]

    return {
        "vin": offline["vin"],
        "valid_format": offline["valid_format"],
        "format_error": offline["format_error"],
        "check_digit_valid": offline["check_digit_valid"],
        "expected_check_digit": offline["expected_check_digit"],
        "offline": offline,
        "live": live,
        "live_error": live_error,
        "resolved": resolved,
        "basis": basis,
        "gaps": gaps,
        "gap_note": _GAP_NOTE if gaps else None,
    }


# ---------------------------------------------------------------------------
# 8. Apply to Vehicle -- a real, additive write, never overwriting real data
# ---------------------------------------------------------------------------


def _now():
    return datetime.now(timezone.utc).isoformat()


def _get_vehicle(vehicle_id):
    v = ledger.get_entity(vehicle_id)
    if not v or v.entity_type != VEHICLE:
        return None
    return v


def get_vehicle_vin_decode(vehicle_id):
    v = _get_vehicle(vehicle_id)
    if not v:
        return None, "Vehicle not found."
    return v.attributes.get("vin_decode"), None


def check_vehicle_vin_match(vehicle_id, attempt_live=True):
    """Phase 2: read-only cross-check, no write anywhere -- decode a
    Vehicle's own on-file VIN and compare the result against its stored
    Year/Make. Reuses decode_vin() directly rather than a second comparison
    engine, so this honors the exact same offline/live basis labeling every
    other consumer of this module already sees.

    Finance (core/asset_management.py's get_collateral_valuation) and
    Service (core/repair_orders.py's get_ro_workspace) both call this
    directly, in-process -- no route of its own is required for either of
    those two consumers, matching how core/asset_management.py already
    reuses core/pricing_desk.py's/core/document_workflows.py's functions
    the same way rather than an HTTP round-trip. A separate
    check_vehicle_vin_match_api() wrapper exists in core/vin_decoder_api.py
    for any other caller (e.g. a dedicated frontend lookup)."""
    v = _get_vehicle(vehicle_id)
    if not v:
        return None, "Vehicle not found."

    vin = (v.attributes.get("VIN") or "").strip()
    if not vin:
        return {
            "vehicle_id": vehicle_id,
            "checked": False,
            "note": "This vehicle has no VIN on file to check.",
        }, None

    decode = decode_vin(vin, attempt_live=attempt_live)

    stored_year = str(v.attributes.get("Year") or "").strip()
    stored_make = str(v.attributes.get("Make") or "").strip()
    decoded_year = decode["resolved"].get("year")
    decoded_make = decode["resolved"].get("make")

    mismatches = []
    if decoded_year and stored_year and str(decoded_year) != stored_year:
        mismatches.append({
            "field": "Year",
            "stored": stored_year,
            "decoded": str(decoded_year),
            "basis": decode["basis"].get("year"),
        })
    if decoded_make and stored_make and decoded_make.strip().lower() != stored_make.strip().lower():
        mismatches.append({
            "field": "Make",
            "stored": stored_make,
            "decoded": decoded_make,
            "basis": decode["basis"].get("make"),
        })

    compared_something = bool(decoded_year) or bool(decoded_make)

    return {
        "vehicle_id": vehicle_id,
        "checked": True,
        "vin": vin,
        "valid_format": decode["valid_format"],
        "format_error": decode["format_error"],
        "check_digit_valid": decode["check_digit_valid"],
        "compared_something": compared_something,
        "mismatches": mismatches,
        "match": bool(decode["valid_format"] and compared_something and not mismatches),
        "note": None if compared_something else (
            "The VIN's own manufacturer/year data couldn't be resolved to "
            "compare against -- see gap_note."
        ),
        "gap_note": decode["gap_note"],
    }, None


def apply_decode_to_vehicle(vehicle_id, employee_id, attempt_live=True, _skip_save=False):
    v = _get_vehicle(vehicle_id)
    if not v:
        return None, "Vehicle not found."

    vin = (v.attributes.get("VIN") or "").strip()
    if not vin:
        return None, "This vehicle has no VIN on file to decode."

    decode = decode_vin(vin, attempt_live=attempt_live)

    record = {
        "decoded_at": _now(),
        "decoded_by": employee_id,
        "check_digit_valid": decode["check_digit_valid"],
        "resolved": decode["resolved"],
        "basis": decode["basis"],
        "gaps": decode["gaps"],
        "live_error": decode["live_error"],
    }

    # Never overwrite an already-set, human-entered value -- only backfill a
    # blank field, same convention core/websites.py's wizard already follows.
    # Real, existing Vehicle.Year values are stored as either a plain string
    # (this codebase's own real seed data, e.g. "2015") or a plain int
    # (several test fixtures elsewhere in this codebase build vehicles with
    # Year=2022 as an int) -- str() first so a "blank or already-set" check
    # never crashes on a non-string attribute value.
    backfilled = []
    if not str(v.attributes.get("Year") or "").strip() and decode["resolved"].get("year"):
        v.attributes["Year"] = str(decode["resolved"]["year"])
        backfilled.append("Year")
    if not str(v.attributes.get("Make") or "").strip() and decode["resolved"].get("make"):
        v.attributes["Make"] = decode["resolved"]["make"]
        backfilled.append("Make")
    if not str(v.attributes.get("Model") or "").strip() and decode["resolved"].get("model"):
        v.attributes["Model"] = decode["resolved"]["model"]
        backfilled.append("Model")
    if not str(v.attributes.get("Trim") or "").strip() and decode["resolved"].get("trim"):
        v.attributes["Trim"] = decode["resolved"]["trim"]
        backfilled.append("Trim")

    record["backfilled_fields"] = backfilled
    v.attributes["vin_decode"] = record

    if not _skip_save:
        save_graph(GRAPH_PATH)

    return {"vehicle_id": vehicle_id, "decode": decode, "applied": record}, None


def bulk_apply_decode(employee_id, vehicle_ids=None, attempt_live=True, limit=100):
    """Decode+apply across several vehicles in one batched call. When
    vehicle_ids is omitted, targets every unsold vehicle with a real VIN on
    file that hasn't been decoded yet (capped at `limit`). One real
    save_graph() call for the whole batch -- not per-vehicle -- same
    discipline core/trigger_alerts.py's run_scan()/core/websites.py's
    create_website_from_wizard() already established, since a naive
    per-vehicle save across dozens of units would be a real, avoidable
    performance cost."""
    if vehicle_ids:
        candidates = [_get_vehicle(vid) for vid in vehicle_ids]
        candidates = [c for c in candidates if c]
    else:
        candidates = [
            v for v in _vehicles()
            if (v.attributes.get("VIN") or "").strip() and not v.attributes.get("vin_decode")
        ][:limit]

    results = []
    any_success = False
    for v in candidates:
        applied, error = apply_decode_to_vehicle(v.id, employee_id, attempt_live=attempt_live, _skip_save=True)
        if error:
            results.append({"vehicle_id": v.id, "error": error})
        else:
            any_success = True
            results.append({
                "vehicle_id": v.id,
                "backfilled_fields": applied["applied"]["backfilled_fields"],
                "check_digit_valid": applied["decode"]["check_digit_valid"],
            })

    if any_success:
        save_graph(GRAPH_PATH)

    return {
        "attempted": len(candidates),
        "succeeded": sum(1 for r in results if "error" not in r),
        "results": results,
        "note": "Batched save -- one save_graph() call for the whole batch, not per-vehicle.",
    }
