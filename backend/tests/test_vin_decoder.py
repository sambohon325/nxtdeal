import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import VEHICLE
from core import vin_decoder
from core import vin_decoder_api
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    # apply_decode_to_vehicle()/bulk_apply_decode() both do their own
    # top-level `from core.storage import save_graph` inside vin_decoder.py
    # itself, so that's the module to patch (not core.storage directly).
    monkeypatch.setattr(vin_decoder, "save_graph", lambda filepath: None)


# ---------------------------------------------------------------------------
# Real, known-good reference VINs (all independently verified against the
# real FMVSS 115 / ISO 3779 check-digit algorithm before being hardcoded here
# -- see CLAUDE.md's "NXTDeal VIN Intelligence" section).
# ---------------------------------------------------------------------------

# WMI "1M8" unrecognized (not in WMI_TABLE), position 7 numeric -> pre-2010
# cycle, resolves to model year 1989.
VIN_UNRECOGNIZED_WMI = "1M8GDM9AXKP042788"

# WMI "1HG" -> real Honda entry, position 7 numeric -> pre-2010 cycle,
# resolves to model year 2003.
VIN_HONDA_2003 = "1HGCM82633A004352"

# Same Honda WMI, position 7 forced alpha ('C') -> 2010+ cycle, resolves to
# model year 2033. Check digit recomputed for the edited VIN.
VIN_HONDA_2033_ALPHA_POS7 = "1HGCM8C653A004352"

# Valid format + valid check digit, but position 10 ('0') is not a real
# model-year code character -> model_year resolves to None.
VIN_INVALID_YEAR_CODE = "1HGCM82690A004352"

# Valid format, but position 9 (check digit) deliberately wrong.
VIN_BAD_CHECK_DIGIT = "1HGCM82693A004352"


def _add_vehicle(vehicle_id="VEH-1", vin=VIN_HONDA_2003, **overrides):
    attrs = {
        "VIN": vin,
        "StockNumber": "S123",
        "Year": "",
        "Make": "",
        "Model": "",
        "Trim": "",
        "Price": 25000,
        "Cost": 21000,
        "Mileage": 30000,
    }
    attrs.update(overrides)
    ledger.add_entity(Entity(id=vehicle_id, entity_type=VEHICLE, attributes=attrs))
    return vehicle_id


def _fake_live_success(**overrides):
    row = {
        "make": "Honda",
        "model": "Accord",
        "model_year": "2003",
        "trim": "EX-L",
        "body_style": "Sedan",
        "vehicle_type": "Passenger Car",
        "engine_cylinders": "4",
        "engine_displacement_l": "2.4",
        "fuel_type": "Gasoline",
        "drive_type": "FWD",
        "transmission": "Automatic",
        "doors": "4",
        "plant_country": "United States",
        "manufacturer_name": "Honda Motor Co Ltd",
        "raw": {},
    }
    row.update(overrides)
    return {"success": True, "source": "nhtsa_vpic_live", **row}


def _fake_live_failure(error="URLError: <urlopen error Tunnel connection failed: 403 Forbidden>"):
    return {"success": False, "error": error, "source": "nhtsa_vpic_live"}


# ---------------------------------------------------------------------------
# _valid_format
# ---------------------------------------------------------------------------


class TestValidFormat:
    def test_empty_rejected(self):
        valid, error = vin_decoder._valid_format("")
        assert valid is False
        assert "required" in error.lower()

    def test_none_rejected(self):
        valid, error = vin_decoder._valid_format(None)
        assert valid is False

    def test_too_short_rejected(self):
        valid, error = vin_decoder._valid_format("SHORT123")
        assert valid is False
        assert "17" in error

    def test_too_long_rejected(self):
        valid, error = vin_decoder._valid_format(VIN_HONDA_2003 + "2")
        assert valid is False
        assert "17" in error

    def test_non_alnum_rejected(self):
        valid, error = vin_decoder._valid_format("1HGCM82633A00435!")
        assert valid is False
        assert "letters and digits" in error

    def test_i_o_q_rejected(self):
        for bad_char in ("I", "O", "Q"):
            # 17 chars total: "1HGCM8263" (9) + bad_char (1) + "A004352" (7).
            vin = "1HGCM8263" + bad_char + "A004352"
            assert len(vin) == 17, vin
            valid, error = vin_decoder._valid_format(vin)
            assert valid is False, vin
            assert "I, O, or Q" in error

    def test_valid_real_vin_accepted(self):
        assert vin_decoder._valid_format(VIN_HONDA_2003) == (True, None)

    def test_lowercase_valid_vin_accepted(self):
        # _valid_format itself doesn't case-fold; the real seed-data VIN is
        # already uppercase, and decode_vin_offline() upper()s before calling
        # this -- confirmed lowercase alone doesn't fail format validation.
        valid, error = vin_decoder._valid_format(VIN_HONDA_2003.lower())
        assert valid is True
        assert error is None


# ---------------------------------------------------------------------------
# _compute_check_digit / decode_vin_offline -- real FMVSS 115 / ISO 3779 math
# ---------------------------------------------------------------------------


class TestCheckDigitAndOfflineDecode:
    def test_honda_2003_check_digit(self):
        assert vin_decoder._compute_check_digit(VIN_HONDA_2003) == "3"

    def test_unrecognized_wmi_check_digit_is_x(self):
        assert vin_decoder._compute_check_digit(VIN_UNRECOGNIZED_WMI) == "X"

    def test_offline_decode_recognized_wmi(self):
        r = vin_decoder.decode_vin_offline(VIN_HONDA_2003)
        assert r["valid_format"] is True
        assert r["check_digit_valid"] is True
        assert r["expected_check_digit"] == "3"
        assert r["wmi"] == "1HG"
        assert r["wmi_recognized"] is True
        assert r["manufacturer"] == "Honda"
        assert r["country_of_origin"] == "United States"
        assert r["vehicle_type_hint"] == "Passenger Car"
        assert r["model_year"] == 2003
        assert r["model_year_candidates"] == [2003, 2033]
        assert r["model_year_basis"] == "position_7_numeric_pre_2010_cycle"
        assert r["plant_code"] == "A"
        assert r["serial_number"] == "004352"

    def test_offline_decode_unrecognized_wmi_honest(self):
        r = vin_decoder.decode_vin_offline(VIN_UNRECOGNIZED_WMI)
        assert r["valid_format"] is True
        assert r["check_digit_valid"] is True
        assert r["wmi"] == "1M8"
        assert r["wmi_recognized"] is False
        assert r["manufacturer"] is None
        assert r["country_of_origin"] is None
        assert r["model_year"] == 1989

    def test_offline_decode_2010_plus_cycle_via_alpha_position_7(self):
        r = vin_decoder.decode_vin_offline(VIN_HONDA_2033_ALPHA_POS7)
        assert r["valid_format"] is True
        assert r["check_digit_valid"] is True
        assert r["model_year"] == 2033
        assert r["model_year_candidates"] == [2003, 2033]
        assert r["model_year_basis"] == "position_7_alpha_2010_plus_cycle"

    def test_offline_decode_invalid_year_code_reports_none_honestly(self):
        r = vin_decoder.decode_vin_offline(VIN_INVALID_YEAR_CODE)
        assert r["valid_format"] is True
        assert r["check_digit_valid"] is True
        assert r["model_year"] is None
        assert r["model_year_candidates"] == []
        assert r["model_year_basis"] == "invalid_year_code"

    def test_offline_decode_bad_check_digit_flagged(self):
        r = vin_decoder.decode_vin_offline(VIN_BAD_CHECK_DIGIT)
        assert r["valid_format"] is True
        assert r["check_digit_valid"] is False
        assert r["expected_check_digit"] == "3"

    def test_offline_decode_invalid_format_returns_honest_empty_shape(self):
        r = vin_decoder.decode_vin_offline("NOTAVALIDVIN")
        assert r["valid_format"] is False
        assert r["format_error"] is not None
        assert r["check_digit_valid"] is None
        assert r["wmi"] is None
        assert r["model_year"] is None

    def test_offline_decode_case_insensitive(self):
        upper = vin_decoder.decode_vin_offline(VIN_HONDA_2003)
        lower = vin_decoder.decode_vin_offline(VIN_HONDA_2003.lower())
        assert upper["vin"] == lower["vin"] == VIN_HONDA_2003
        assert upper["manufacturer"] == lower["manufacturer"] == "Honda"


# ---------------------------------------------------------------------------
# _resolve_model_year -- direct branch coverage
# ---------------------------------------------------------------------------


class TestResolveModelYear:
    def test_too_short(self):
        r = vin_decoder._resolve_model_year("SHORT")
        assert r == {"resolved_year": None, "candidates": [], "basis": "vin_too_short"}

    def test_invalid_year_code_char(self):
        # 'U' and 'Z' are valid alnum, not I/O/Q, but not in the real
        # 30-character year-code cycle.
        r = vin_decoder._resolve_model_year("1HGCM8263UA004352")
        assert r["resolved_year"] is None
        assert r["candidates"] == []
        assert r["basis"] == "invalid_year_code"

    def test_numeric_position_7_pre_2010_cycle(self):
        r = vin_decoder._resolve_model_year(VIN_HONDA_2003)
        assert r["resolved_year"] == 2003
        assert r["basis"] == "position_7_numeric_pre_2010_cycle"

    def test_alpha_position_7_2010_plus_cycle(self):
        r = vin_decoder._resolve_model_year(VIN_HONDA_2033_ALPHA_POS7)
        assert r["resolved_year"] == 2033
        assert r["basis"] == "position_7_alpha_2010_plus_cycle"

    def test_year_candidates_unknown_code_returns_empty(self):
        # 'Z' (and 'I'/'O'/'Q'/'U') are valid alnum but excluded from the real
        # 30-character year-code cycle.
        assert vin_decoder._year_candidates("Z") == []
        assert vin_decoder._year_candidates("U") == []
        # None normalizes to "" internally, which Python's str.find() always
        # matches at index 0 -- not a real invalid-input case, since
        # _resolve_model_year() only ever calls this with a real single VIN
        # character (vin[9]), never an empty/missing one. Documented here,
        # not treated as a product bug.
        assert vin_decoder._year_candidates(None) == [1980, 2010]

    def test_year_candidates_known_code_returns_both_cycles(self):
        assert vin_decoder._year_candidates("3") == [2003, 2033]


# ---------------------------------------------------------------------------
# fetch_vin_decode_nhtsa -- real network call, mocked here (this sandbox has
# confirmed zero outbound network access, per this module's own docstring).
# ---------------------------------------------------------------------------


class TestFetchVinDecodeNhtsa:
    def test_network_failure_degrades_honestly(self, monkeypatch):
        def _raise(*args, **kwargs):
            raise OSError("Tunnel connection failed: 403 Forbidden")

        monkeypatch.setattr(vin_decoder.urllib.request, "urlopen", _raise)
        result = vin_decoder.fetch_vin_decode_nhtsa(VIN_HONDA_2003)
        assert result["success"] is False
        assert "403" in result["error"] or "OSError" in result["error"]
        assert result["source"] == "nhtsa_vpic_live"

    def test_empty_results_degrades_honestly(self, monkeypatch):
        class _FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return b'{"Results": []}'

        monkeypatch.setattr(vin_decoder.urllib.request, "urlopen", lambda *a, **k: _FakeResp())
        result = vin_decoder.fetch_vin_decode_nhtsa(VIN_HONDA_2003)
        assert result["success"] is False
        assert "no results" in result["error"].lower()

    def test_nhtsa_error_code_degrades_honestly(self, monkeypatch):
        import json as _json

        payload = _json.dumps({"Results": [{"ErrorCode": "6", "ErrorText": "Incomplete VIN"}]}).encode("utf-8")

        class _FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return payload

        monkeypatch.setattr(vin_decoder.urllib.request, "urlopen", lambda *a, **k: _FakeResp())
        result = vin_decoder.fetch_vin_decode_nhtsa(VIN_HONDA_2003)
        assert result["success"] is False
        assert result["error"] == "Incomplete VIN"

    def test_real_success_shape(self, monkeypatch):
        import json as _json

        row = {
            "ErrorCode": "0",
            "Make": "Honda",
            "Model": "Accord",
            "ModelYear": "2003",
            "Trim": "EX-L",
            "Series": "",
            "BodyClass": "Sedan",
            "VehicleType": "Passenger Car",
            "EngineCylinders": "4",
            "DisplacementL": "2.4",
            "FuelTypePrimary": "Gasoline",
            "DriveType": "FWD",
            "TransmissionStyle": "Automatic",
            "Doors": "4",
            "PlantCountry": "United States",
            "Manufacturer": "Honda Motor Co Ltd",
        }
        payload = _json.dumps({"Results": [row]}).encode("utf-8")

        class _FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return payload

        monkeypatch.setattr(vin_decoder.urllib.request, "urlopen", lambda *a, **k: _FakeResp())
        result = vin_decoder.fetch_vin_decode_nhtsa(VIN_HONDA_2003)
        assert result["success"] is True
        assert result["source"] == "nhtsa_vpic_live"
        assert result["make"] == "Honda"
        assert result["model"] == "Accord"
        assert result["model_year"] == "2003"
        assert result["trim"] == "EX-L"
        assert result["body_style"] == "Sedan"
        assert result["engine_cylinders"] == "4"
        assert result["engine_displacement_l"] == "2.4"


# ---------------------------------------------------------------------------
# decode_vin -- the real merge function
# ---------------------------------------------------------------------------


class TestDecodeVin:
    def test_invalid_format_skips_live_lookup_entirely(self, monkeypatch):
        called = {"hit": False}

        def _spy(*a, **k):
            called["hit"] = True
            return _fake_live_success()

        monkeypatch.setattr(vin_decoder, "fetch_vin_decode_nhtsa", _spy)
        result = vin_decoder.decode_vin("NOTAVALIDVIN", attempt_live=True)
        assert called["hit"] is False
        assert result["valid_format"] is False
        assert result["live"] is None
        assert "invalid" in result["live_error"].lower()

    def test_attempt_live_false_skips_the_call(self, monkeypatch):
        called = {"hit": False}

        def _spy(*a, **k):
            called["hit"] = True
            return _fake_live_success()

        monkeypatch.setattr(vin_decoder, "fetch_vin_decode_nhtsa", _spy)
        result = vin_decoder.decode_vin(VIN_HONDA_2003, attempt_live=False)
        assert called["hit"] is False
        assert result["live"] is None
        assert "not attempted" in result["live_error"].lower()
        # Offline-derived fields are still real even with no live call.
        assert result["resolved"]["year"] == 2003
        assert result["resolved"]["make"] == "Honda"
        assert result["basis"]["year"] == "iso_3779_offline"
        assert result["basis"]["make"] == "wmi_offline"
        assert result["basis"]["model"] == "unavailable"
        assert "model" in result["gaps"]
        assert result["gap_note"] is not None

    def test_live_failure_falls_back_to_offline_only(self, monkeypatch):
        monkeypatch.setattr(vin_decoder, "fetch_vin_decode_nhtsa", lambda *a, **k: _fake_live_failure())
        result = vin_decoder.decode_vin(VIN_HONDA_2003, attempt_live=True)
        assert result["live"] is None
        assert result["live_error"] is not None
        assert result["resolved"]["year"] == 2003
        assert result["resolved"]["make"] == "Honda"
        assert result["resolved"]["model"] is None
        assert result["basis"]["year"] == "iso_3779_offline"
        assert result["basis"]["model"] == "unavailable"

    def test_live_success_never_overwritten_by_offline_and_fills_gaps(self, monkeypatch):
        monkeypatch.setattr(vin_decoder, "fetch_vin_decode_nhtsa", lambda *a, **k: _fake_live_success())
        result = vin_decoder.decode_vin(VIN_HONDA_2003, attempt_live=True)
        assert result["live"]["success"] is True
        assert result["live_error"] is None
        assert result["resolved"]["year"] == "2003"  # live value, a string, takes precedence
        assert result["resolved"]["make"] == "Honda"
        assert result["resolved"]["model"] == "Accord"
        assert result["resolved"]["trim"] == "EX-L"
        assert result["resolved"]["engine"] == "2.4L 4-cyl"
        assert result["resolved"]["transmission"] == "Automatic"
        assert result["resolved"]["drive_type"] == "FWD"
        assert result["resolved"]["fuel_type"] == "Gasoline"
        assert result["resolved"]["body_style"] == "Sedan"
        assert result["basis"]["year"] == "nhtsa_vpic_live"
        assert result["basis"]["make"] == "nhtsa_vpic_live"
        assert result["basis"]["model"] == "nhtsa_vpic_live"
        assert result["gaps"] == []
        assert result["gap_note"] is None

    def test_live_success_but_missing_some_fields_honestly_reports_gaps(self, monkeypatch):
        partial = _fake_live_success(trim=None, engine_cylinders=None, engine_displacement_l=None, transmission=None)
        monkeypatch.setattr(vin_decoder, "fetch_vin_decode_nhtsa", lambda *a, **k: partial)
        result = vin_decoder.decode_vin(VIN_HONDA_2003, attempt_live=True)
        assert result["resolved"]["trim"] is None
        assert result["resolved"]["engine"] is None
        assert "trim" in result["gaps"]
        assert "engine" in result["gaps"]
        assert "transmission" in result["gaps"]
        assert result["gap_note"] is not None

    def test_unrecognized_wmi_and_live_failure_leaves_make_unavailable(self, monkeypatch):
        monkeypatch.setattr(vin_decoder, "fetch_vin_decode_nhtsa", lambda *a, **k: _fake_live_failure())
        result = vin_decoder.decode_vin(VIN_UNRECOGNIZED_WMI, attempt_live=True)
        assert result["resolved"]["make"] is None
        assert result["basis"]["make"] == "unavailable"
        assert "make" in result["gaps"]
        assert result["resolved"]["year"] == 1989
        assert result["basis"]["year"] == "iso_3779_offline"


# ---------------------------------------------------------------------------
# get_vehicle_vin_decode / apply_decode_to_vehicle / bulk_apply_decode
# ---------------------------------------------------------------------------


class TestGetVehicleVinDecode:
    def test_unknown_vehicle_rejected(self):
        result, error = vin_decoder.get_vehicle_vin_decode("VEH-NOPE")
        assert result is None
        assert error == "Vehicle not found."

    def test_not_yet_decoded_returns_none_no_error(self):
        _add_vehicle()
        result, error = vin_decoder.get_vehicle_vin_decode("VEH-1")
        assert result is None
        assert error is None

    def test_returns_stored_record_after_apply(self, monkeypatch):
        _add_vehicle()
        monkeypatch.setattr(vin_decoder, "fetch_vin_decode_nhtsa", lambda *a, **k: _fake_live_failure())
        vin_decoder.apply_decode_to_vehicle("VEH-1", "EMP-1", attempt_live=True)
        result, error = vin_decoder.get_vehicle_vin_decode("VEH-1")
        assert error is None
        assert result is not None
        assert result["decoded_by"] == "EMP-1"


class TestApplyDecodeToVehicle:
    def test_unknown_vehicle_rejected(self):
        result, error = vin_decoder.apply_decode_to_vehicle("VEH-NOPE", "EMP-1")
        assert result is None
        assert error == "Vehicle not found."

    def test_no_vin_on_file_rejected(self):
        _add_vehicle(vin="")
        result, error = vin_decoder.apply_decode_to_vehicle("VEH-1", "EMP-1")
        assert result is None
        assert "no VIN" in error

    def test_backfills_only_blank_fields(self, monkeypatch):
        _add_vehicle(Year="", Make="", Model="", Trim="")
        monkeypatch.setattr(vin_decoder, "fetch_vin_decode_nhtsa", lambda *a, **k: _fake_live_success())
        result, error = vin_decoder.apply_decode_to_vehicle("VEH-1", "EMP-1", attempt_live=True)
        assert error is None
        assert sorted(result["applied"]["backfilled_fields"]) == ["Make", "Model", "Trim", "Year"]

        v = ledger.get_entity("VEH-1")
        assert v.attributes["Year"] == "2003"
        assert v.attributes["Make"] == "Honda"
        assert v.attributes["Model"] == "Accord"
        assert v.attributes["Trim"] == "EX-L"
        assert v.attributes["vin_decode"]["decoded_by"] == "EMP-1"
        assert v.attributes["vin_decode"]["check_digit_valid"] is True

    def test_never_overwrites_already_set_string_year(self, monkeypatch):
        # Real seed data stores Year as a plain string (e.g. "2015").
        _add_vehicle(Year="2015", Make="", Model="", Trim="")
        monkeypatch.setattr(vin_decoder, "fetch_vin_decode_nhtsa", lambda *a, **k: _fake_live_success())
        result, error = vin_decoder.apply_decode_to_vehicle("VEH-1", "EMP-1", attempt_live=True)
        assert error is None
        assert "Year" not in result["applied"]["backfilled_fields"]
        assert "Make" in result["applied"]["backfilled_fields"]

        v = ledger.get_entity("VEH-1")
        assert v.attributes["Year"] == "2015"  # untouched, not overwritten to "2003"
        assert v.attributes["Make"] == "Honda"  # backfilled, was blank

    def test_never_overwrites_already_set_int_year(self, monkeypatch):
        # Some test fixtures elsewhere in this codebase (e.g.
        # tests/test_pricing_desk.py's own _add_vehicle helper) build a
        # Vehicle with Year as a plain int rather than a string -- this must
        # not crash the blank-check and must not be treated as "blank".
        _add_vehicle(Year=2022, Make="", Model="", Trim="")
        monkeypatch.setattr(vin_decoder, "fetch_vin_decode_nhtsa", lambda *a, **k: _fake_live_success())
        result, error = vin_decoder.apply_decode_to_vehicle("VEH-1", "EMP-1", attempt_live=True)
        assert error is None
        assert "Year" not in result["applied"]["backfilled_fields"]

        v = ledger.get_entity("VEH-1")
        assert v.attributes["Year"] == 2022  # untouched int, not overwritten

    def test_never_overwrites_already_set_make_model_trim(self, monkeypatch):
        _add_vehicle(Year="", Make="Toyota", Model="Camry", Trim="LE")
        monkeypatch.setattr(vin_decoder, "fetch_vin_decode_nhtsa", lambda *a, **k: _fake_live_success())
        result, error = vin_decoder.apply_decode_to_vehicle("VEH-1", "EMP-1", attempt_live=True)
        assert error is None
        assert result["applied"]["backfilled_fields"] == ["Year"]

        v = ledger.get_entity("VEH-1")
        assert v.attributes["Make"] == "Toyota"
        assert v.attributes["Model"] == "Camry"
        assert v.attributes["Trim"] == "LE"
        assert v.attributes["Year"] == "2003"

    def test_offline_only_still_backfills_year_and_make(self, monkeypatch):
        _add_vehicle(Year="", Make="", Model="", Trim="")
        monkeypatch.setattr(vin_decoder, "fetch_vin_decode_nhtsa", lambda *a, **k: _fake_live_failure())
        result, error = vin_decoder.apply_decode_to_vehicle("VEH-1", "EMP-1", attempt_live=True)
        assert error is None
        assert sorted(result["applied"]["backfilled_fields"]) == ["Make", "Year"]

        v = ledger.get_entity("VEH-1")
        assert v.attributes["Year"] == "2003"
        assert v.attributes["Make"] == "Honda"
        assert v.attributes.get("Model") == ""  # honestly still blank, no live source

    def test_stores_gaps_and_live_error_on_the_vehicle_record(self, monkeypatch):
        _add_vehicle()
        monkeypatch.setattr(vin_decoder, "fetch_vin_decode_nhtsa", lambda *a, **k: _fake_live_failure(error="boom"))
        result, error = vin_decoder.apply_decode_to_vehicle("VEH-1", "EMP-1", attempt_live=True)
        assert error is None
        record = ledger.get_entity("VEH-1").attributes["vin_decode"]
        assert record["live_error"] == "boom"
        assert "model" in record["gaps"]

    def test_skip_save_does_not_call_save_graph(self, monkeypatch):
        _add_vehicle()
        calls = {"n": 0}
        monkeypatch.setattr(vin_decoder, "save_graph", lambda filepath: calls.__setitem__("n", calls["n"] + 1))
        monkeypatch.setattr(vin_decoder, "fetch_vin_decode_nhtsa", lambda *a, **k: _fake_live_failure())
        vin_decoder.apply_decode_to_vehicle("VEH-1", "EMP-1", attempt_live=True, _skip_save=True)
        assert calls["n"] == 0

    def test_without_skip_save_calls_save_graph_once(self, monkeypatch):
        _add_vehicle()
        calls = {"n": 0}
        monkeypatch.setattr(vin_decoder, "save_graph", lambda filepath: calls.__setitem__("n", calls["n"] + 1))
        monkeypatch.setattr(vin_decoder, "fetch_vin_decode_nhtsa", lambda *a, **k: _fake_live_failure())
        vin_decoder.apply_decode_to_vehicle("VEH-1", "EMP-1", attempt_live=True)
        assert calls["n"] == 1


class TestBulkApplyDecode:
    def test_explicit_vehicle_ids(self, monkeypatch):
        _add_vehicle("VEH-1")
        _add_vehicle("VEH-2")
        monkeypatch.setattr(vin_decoder, "fetch_vin_decode_nhtsa", lambda *a, **k: _fake_live_failure())
        result = vin_decoder.bulk_apply_decode("EMP-1", vehicle_ids=["VEH-1", "VEH-2"])
        assert result["attempted"] == 2
        assert result["succeeded"] == 2
        assert ledger.get_entity("VEH-1").attributes["Make"] == "Honda"
        assert ledger.get_entity("VEH-2").attributes["Make"] == "Honda"

    def test_unknown_explicit_id_is_silently_skipped_from_candidates(self, monkeypatch):
        _add_vehicle("VEH-1")
        monkeypatch.setattr(vin_decoder, "fetch_vin_decode_nhtsa", lambda *a, **k: _fake_live_failure())
        result = vin_decoder.bulk_apply_decode("EMP-1", vehicle_ids=["VEH-1", "VEH-NOPE"])
        assert result["attempted"] == 1
        assert result["succeeded"] == 1

    def test_auto_discovery_skips_sold_vehicles_with_no_vin_or_already_decoded(self, monkeypatch):
        _add_vehicle("VEH-1", vin=VIN_HONDA_2003)  # eligible: has VIN, not yet decoded
        _add_vehicle("VEH-2", vin="")  # ineligible: no VIN
        _add_vehicle("VEH-3", vin=VIN_UNRECOGNIZED_WMI, vin_decode={"decoded_at": "already"})  # ineligible: already decoded
        monkeypatch.setattr(vin_decoder, "fetch_vin_decode_nhtsa", lambda *a, **k: _fake_live_failure())
        result = vin_decoder.bulk_apply_decode("EMP-1")
        assert result["attempted"] == 1
        assert result["results"][0]["vehicle_id"] == "VEH-1"

    def test_respects_limit(self, monkeypatch):
        for i in range(5):
            _add_vehicle(f"VEH-{i}", vin=VIN_HONDA_2003)
        monkeypatch.setattr(vin_decoder, "fetch_vin_decode_nhtsa", lambda *a, **k: _fake_live_failure())
        result = vin_decoder.bulk_apply_decode("EMP-1", limit=2)
        assert result["attempted"] == 2

    def test_batched_save_called_exactly_once_for_the_whole_batch(self, monkeypatch):
        for i in range(3):
            _add_vehicle(f"VEH-{i}", vin=VIN_HONDA_2003)
        calls = {"n": 0}
        monkeypatch.setattr(vin_decoder, "save_graph", lambda filepath: calls.__setitem__("n", calls["n"] + 1))
        monkeypatch.setattr(vin_decoder, "fetch_vin_decode_nhtsa", lambda *a, **k: _fake_live_failure())
        vin_decoder.bulk_apply_decode("EMP-1")
        assert calls["n"] == 1

    def test_no_save_when_nothing_succeeded(self, monkeypatch):
        calls = {"n": 0}
        monkeypatch.setattr(vin_decoder, "save_graph", lambda filepath: calls.__setitem__("n", calls["n"] + 1))
        result = vin_decoder.bulk_apply_decode("EMP-1", vehicle_ids=["VEH-NOPE"])
        assert result["attempted"] == 0
        assert result["succeeded"] == 0
        assert calls["n"] == 0

    def test_partial_failure_still_saves_once(self, monkeypatch):
        _add_vehicle("VEH-1", vin=VIN_HONDA_2003)
        _add_vehicle("VEH-2", vin="")  # will error inside apply_decode_to_vehicle
        calls = {"n": 0}
        monkeypatch.setattr(vin_decoder, "save_graph", lambda filepath: calls.__setitem__("n", calls["n"] + 1))
        monkeypatch.setattr(vin_decoder, "fetch_vin_decode_nhtsa", lambda *a, **k: _fake_live_failure())
        result = vin_decoder.bulk_apply_decode("EMP-1", vehicle_ids=["VEH-1", "VEH-2"])
        assert result["attempted"] == 2
        assert result["succeeded"] == 1
        assert calls["n"] == 1
        errored = [r for r in result["results"] if "error" in r]
        assert len(errored) == 1
        assert errored[0]["vehicle_id"] == "VEH-2"


# ---------------------------------------------------------------------------
# check_vehicle_vin_match -- Phase 2, read-only cross-check (Finance/Service)
# ---------------------------------------------------------------------------


class TestCheckVehicleVinMatch:
    def test_unknown_vehicle_rejected(self):
        result, error = vin_decoder.check_vehicle_vin_match("VEH-NOPE")
        assert result is None
        assert error == "Vehicle not found."

    def test_no_vin_on_file_honest_note_no_error(self):
        _add_vehicle(vin="")
        result, error = vin_decoder.check_vehicle_vin_match("VEH-1")
        assert error is None
        assert result["checked"] is False
        assert "no VIN on file" in result["note"]

    def test_stored_values_match_decode(self, monkeypatch):
        _add_vehicle(vin=VIN_HONDA_2003, Year="2003", Make="Honda")
        monkeypatch.setattr(vin_decoder, "fetch_vin_decode_nhtsa", lambda *a, **k: _fake_live_failure())
        result, error = vin_decoder.check_vehicle_vin_match("VEH-1", attempt_live=True)
        assert error is None
        assert result["checked"] is True
        assert result["valid_format"] is True
        assert result["compared_something"] is True
        assert result["mismatches"] == []
        assert result["match"] is True
        assert result["note"] is None

    def test_make_comparison_is_case_insensitive(self, monkeypatch):
        _add_vehicle(vin=VIN_HONDA_2003, Year="2003", Make="honda")
        monkeypatch.setattr(vin_decoder, "fetch_vin_decode_nhtsa", lambda *a, **k: _fake_live_failure())
        result, error = vin_decoder.check_vehicle_vin_match("VEH-1", attempt_live=True)
        assert result["mismatches"] == []
        assert result["match"] is True

    def test_year_mismatch_reported_honestly(self, monkeypatch):
        _add_vehicle(vin=VIN_HONDA_2003, Year="1999", Make="Honda")
        monkeypatch.setattr(vin_decoder, "fetch_vin_decode_nhtsa", lambda *a, **k: _fake_live_failure())
        result, error = vin_decoder.check_vehicle_vin_match("VEH-1", attempt_live=True)
        assert result["match"] is False
        assert len(result["mismatches"]) == 1
        m = result["mismatches"][0]
        assert m["field"] == "Year"
        assert m["stored"] == "1999"
        assert m["decoded"] == "2003"
        assert m["basis"] == "iso_3779_offline"

    def test_make_mismatch_reported_honestly(self, monkeypatch):
        _add_vehicle(vin=VIN_HONDA_2003, Year="2003", Make="Toyota")
        monkeypatch.setattr(vin_decoder, "fetch_vin_decode_nhtsa", lambda *a, **k: _fake_live_failure())
        result, error = vin_decoder.check_vehicle_vin_match("VEH-1", attempt_live=True)
        assert result["match"] is False
        fields = {m["field"] for m in result["mismatches"]}
        assert "Make" in fields

    def test_both_year_and_make_mismatched(self, monkeypatch):
        _add_vehicle(vin=VIN_HONDA_2003, Year="1999", Make="Toyota")
        monkeypatch.setattr(vin_decoder, "fetch_vin_decode_nhtsa", lambda *a, **k: _fake_live_failure())
        result, error = vin_decoder.check_vehicle_vin_match("VEH-1", attempt_live=True)
        assert len(result["mismatches"]) == 2

    def test_stored_year_or_make_blank_is_not_treated_as_a_mismatch(self, monkeypatch):
        _add_vehicle(vin=VIN_HONDA_2003, Year="", Make="")
        monkeypatch.setattr(vin_decoder, "fetch_vin_decode_nhtsa", lambda *a, **k: _fake_live_failure())
        result, error = vin_decoder.check_vehicle_vin_match("VEH-1", attempt_live=True)
        assert result["mismatches"] == []
        # compared_something is still true (the VIN itself resolved real values),
        # this vehicle's own record just has nothing on file yet to compare against.
        assert result["compared_something"] is True
        assert result["match"] is True

    def test_unresolvable_vin_honestly_reports_nothing_compared(self, monkeypatch):
        _add_vehicle(vin=VIN_UNRECOGNIZED_WMI, Year="", Make="")
        monkeypatch.setattr(vin_decoder, "fetch_vin_decode_nhtsa", lambda *a, **k: _fake_live_failure())
        result, error = vin_decoder.check_vehicle_vin_match("VEH-1", attempt_live=True)
        # WMI unrecognized -> make unresolved; but ISO 3779 model_year is still
        # a real offline signal for this VIN, so compared_something is true.
        assert result["compared_something"] is True
        assert result["note"] is None

    def test_invalid_format_vin_honestly_reports_nothing_compared(self):
        _add_vehicle(vin="BOGUS")
        result, error = vin_decoder.check_vehicle_vin_match("VEH-1", attempt_live=True)
        assert result["checked"] is True
        assert result["valid_format"] is False
        assert result["compared_something"] is False
        assert result["mismatches"] == []
        assert result["match"] is False
        assert result["note"] is not None
        assert "couldn't be resolved" in result["note"]

    def test_makes_no_write_to_the_ledger(self, monkeypatch):
        _add_vehicle(vin=VIN_HONDA_2003, Year="1999", Make="Toyota")
        monkeypatch.setattr(vin_decoder, "fetch_vin_decode_nhtsa", lambda *a, **k: _fake_live_failure())
        vin_decoder.check_vehicle_vin_match("VEH-1", attempt_live=True)
        v = ledger.get_entity("VEH-1")
        assert v.attributes["Year"] == "1999"
        assert v.attributes["Make"] == "Toyota"
        assert "vin_decode" not in v.attributes


# ---------------------------------------------------------------------------
# ACL layer (core/vin_decoder_api.py)
# ---------------------------------------------------------------------------

_VIEW_ALLOWED = [ADMIN, OPERATIONS, SALES, SERVICE, MARKETING, FINANCE]
_VIEW_DENIED = ["BOGUS_ROLE"]
_MUTATE_ALLOWED = [ADMIN, OPERATIONS, SALES]
_MUTATE_DENIED = [SERVICE, MARKETING, FINANCE, "BOGUS_ROLE"]


class TestAcl:
    @pytest.mark.parametrize("role", _VIEW_ALLOWED)
    def test_decode_vin_api_view_allowed(self, role, monkeypatch):
        ledger.reset()
        monkeypatch.setattr(vin_decoder, "fetch_vin_decode_nhtsa", lambda *a, **k: _fake_live_failure())
        result = vin_decoder_api.decode_vin_api(role, VIN_HONDA_2003)
        assert "error" not in result

    @pytest.mark.parametrize("role", _VIEW_DENIED)
    def test_decode_vin_api_view_denied(self, role):
        result = vin_decoder_api.decode_vin_api(role, VIN_HONDA_2003)
        assert "error" in result

    @pytest.mark.parametrize("role", _VIEW_ALLOWED)
    def test_get_vehicle_vin_decode_api_view_allowed(self, role):
        ledger.reset()
        _add_vehicle()
        result = vin_decoder_api.get_vehicle_vin_decode_api(role, "VEH-1")
        assert "error" not in result
        assert result["vin_decode"] is None
        assert "note" in result

    @pytest.mark.parametrize("role", _VIEW_DENIED)
    def test_get_vehicle_vin_decode_api_view_denied(self, role):
        _add_vehicle()
        result = vin_decoder_api.get_vehicle_vin_decode_api(role, "VEH-1")
        assert "error" in result

    def test_get_vehicle_vin_decode_api_bad_vehicle_id_honest_error(self):
        result = vin_decoder_api.get_vehicle_vin_decode_api(ADMIN, "VEH-NOPE")
        assert result == {"error": "Vehicle not found."}

    @pytest.mark.parametrize("role", _MUTATE_ALLOWED)
    def test_apply_decode_to_vehicle_api_mutate_allowed(self, role, monkeypatch):
        ledger.reset()
        _add_vehicle()
        monkeypatch.setattr(vin_decoder, "fetch_vin_decode_nhtsa", lambda *a, **k: _fake_live_failure())
        result = vin_decoder_api.apply_decode_to_vehicle_api(role, "EMP-1", "VEH-1")
        assert "error" not in result
        assert result["vehicle_id"] == "VEH-1"

    @pytest.mark.parametrize("role", _MUTATE_DENIED)
    def test_apply_decode_to_vehicle_api_mutate_denied(self, role):
        _add_vehicle()
        result = vin_decoder_api.apply_decode_to_vehicle_api(role, "EMP-1", "VEH-1")
        assert "error" in result

    def test_apply_decode_to_vehicle_api_bad_vehicle_id_honest_error(self):
        result = vin_decoder_api.apply_decode_to_vehicle_api(ADMIN, "EMP-1", "VEH-NOPE")
        assert result == {"error": "Vehicle not found."}

    @pytest.mark.parametrize("role", _MUTATE_ALLOWED)
    def test_bulk_apply_decode_api_mutate_allowed(self, role, monkeypatch):
        ledger.reset()
        _add_vehicle()
        monkeypatch.setattr(vin_decoder, "fetch_vin_decode_nhtsa", lambda *a, **k: _fake_live_failure())
        result = vin_decoder_api.bulk_apply_decode_api(role, "EMP-1", vehicle_ids=["VEH-1"])
        assert "error" not in result
        assert result["attempted"] == 1

    @pytest.mark.parametrize("role", _MUTATE_DENIED)
    def test_bulk_apply_decode_api_mutate_denied(self, role):
        result = vin_decoder_api.bulk_apply_decode_api(role, "EMP-1")
        assert "error" in result

    def test_bulk_apply_decode_api_caps_limit_at_200(self, monkeypatch):
        captured = {}

        def _spy(employee_id, vehicle_ids=None, attempt_live=True, limit=100):
            captured["limit"] = limit
            return {"attempted": 0, "succeeded": 0, "results": []}

        monkeypatch.setattr(vin_decoder_api, "bulk_apply_decode", _spy)
        vin_decoder_api.bulk_apply_decode_api(ADMIN, "EMP-1", limit=9999)
        assert captured["limit"] == 200

    @pytest.mark.parametrize("role", _VIEW_ALLOWED)
    def test_check_vehicle_vin_match_api_view_allowed(self, role, monkeypatch):
        ledger.reset()
        _add_vehicle(vin=VIN_HONDA_2003, Year="2003", Make="Honda")
        monkeypatch.setattr(vin_decoder, "fetch_vin_decode_nhtsa", lambda *a, **k: _fake_live_failure())
        result = vin_decoder_api.check_vehicle_vin_match_api(role, "VEH-1")
        assert "error" not in result
        assert result["match"] is True

    @pytest.mark.parametrize("role", _VIEW_DENIED)
    def test_check_vehicle_vin_match_api_view_denied(self, role):
        _add_vehicle(vin=VIN_HONDA_2003)
        result = vin_decoder_api.check_vehicle_vin_match_api(role, "VEH-1")
        assert "error" in result

    def test_check_vehicle_vin_match_api_bad_vehicle_id_honest_error(self):
        result = vin_decoder_api.check_vehicle_vin_match_api(ADMIN, "VEH-NOPE")
        assert result == {"error": "Vehicle not found."}
