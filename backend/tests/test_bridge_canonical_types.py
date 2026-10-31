import pytest
from core.bridge_contracts import transform, validate_mapping_spec, timestamp
from core.bridge_connectors import parse_csv


def field(source, op="text"):
    return {"source": source, "transform": op}


def test_integer_canonical_fields_are_typed_even_with_text_mapping():
    values = transform("Vehicle", {"vin": field("vin"), "year": field("year")}, {"vin": "1HGCM82633A004352", "year": "2026"})
    assert values["year"] == 2026 and type(values["year"]) is int
    values = transform("CollectionCase", {"account_id": field("account"), "status": field("status"), "days_past_due": field("days")}, {"account": "account-1", "status": "open", "days": "30"})
    assert values["days_past_due"] == 30


@pytest.mark.parametrize("year", ["next year", "2026.0", "1e3", "999", "10000", "１２３４", "9" * 500])
def test_invalid_year_never_enters_legacy_vehicle_projection(year):
    with pytest.raises(ValueError): transform("Vehicle", {"vin": field("vin"), "year": field("year")}, {"vin": "1HGCM82633A004352", "year": year})


@pytest.mark.parametrize("email", ["@", "name@", "@host", "name@@host", "a b@example.com", "a@example.com\r\nBcc:other@example.com"])
def test_email_shape_rejects_empty_or_multiline_addresses(email):
    with pytest.raises(ValueError): transform("Customer", {"email": field("email")}, {"email": email})


def test_wrong_transform_type_is_rejected_at_proposal_validation():
    with pytest.raises(ValueError): validate_mapping_spec("email", field("email", "integer"))
    with pytest.raises(ValueError): validate_mapping_spec("first_name", field("x" * 121))
    with pytest.raises(ValueError): transform("Part", {"quantity": field("quantity", "integer")}, {"quantity": "2147483648"})


def test_time_values_normalize_in_v2_without_reinterpreting_v1():
    mapping = {"starts_at": field("time")}
    first = {"time": "2026-01-01T10:00:00-06:00"}
    second = {"time": "2026-01-01T16:00:00Z"}
    assert transform("Appointment", mapping, first) == transform("Appointment", mapping, second)
    assert transform("Appointment", mapping, first, version=1)["starts_at"] == first["time"]
    assert transform("Part", {"quantity": field("quantity")}, {"quantity": "5"}, version=1)["quantity"] == "5"
    with pytest.raises(ValueError): transform("Appointment", mapping, first, version=99)


@pytest.mark.parametrize("value", ["0001-01-01T00:00:00+01:00", "9999-12-31T23:59:59-01:00"])
def test_source_timestamp_must_be_representable_in_utc_before_staging(value):
    with pytest.raises(ValueError, match="supported UTC range"):
        timestamp(value)
    with pytest.raises(ValueError, match="supported UTC range"):
        parse_csv(f"external_id,modified_at,name\n1,{value},Synthetic\n")


@pytest.mark.parametrize("value", [None, True, "x" * 65, "private data mistaken for timestamp"])
def test_invalid_timestamp_error_does_not_echo_raw_source_values(value):
    with pytest.raises(ValueError) as error:
        timestamp(value)
    assert "private data" not in str(error.value)
