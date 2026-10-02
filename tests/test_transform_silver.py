import json

import pytest

from pipeline.transform_silver import clean_payload, deduplicate, validate_record

FETCH_DATE = "2026-09-26"
BASE = "USD"


def make_record(**overrides):
    record = {"date": FETCH_DATE, "base": BASE, "quote": "UZS", "rate": 11828}
    record.update(overrides)
    return record

###

def test_valid_record_is_cleaned_and_typed():
    row, reason = validate_record(make_record(), FETCH_DATE, BASE)

    assert reason is None
    assert row == {
        "date": "2026-09-26",
        "base_currency": "USD",
        "target_currency": "UZS",
        "exchange_rate": 11828.0,
    }
    assert isinstance(row["exchange_rate"], float)


def test_currency_codes_are_normalised():
    row, _ = validate_record(make_record(base=" usd ", quote="uzs"), FETCH_DATE, BASE)

    assert row["base_currency"] == "USD"
    assert row["target_currency"] == "UZS"

###

@pytest.mark.parametrize(
    "bad_rate",
    [0, -5, None, "abc", True, float("nan"), float("inf")],
)
def test_invalid_rates_are_rejected(bad_rate):
    row, reason = validate_record(make_record(rate=bad_rate), FETCH_DATE, BASE)

    assert row is None
    assert reason

###

@pytest.mark.parametrize(
    "overrides",
    [
        {"quote": None},
        {"quote": "US"},
        {"quote": "12$"},
        {"base": "EUR"},
        {"date": "2026-13-45"},
    ],
)
def test_invalid_fields_are_rejected(overrides):
    row, reason = validate_record(make_record(**overrides), FETCH_DATE, BASE)

    assert row is None
    assert reason


def test_non_trading_day_is_skipped():
    row, reason = validate_record(make_record(date="2026-09-25"), FETCH_DATE, BASE)

    assert row is None
    assert reason.startswith("non-trading day")

###

def test_clean_payload_keeps_valid_and_reports_invalid():
    raw = json.dumps([make_record(), make_record(quote="EUR", rate=-1)])

    clean, rejects = clean_payload(raw, FETCH_DATE, BASE)

    assert len(clean) == 1
    assert clean[0]["target_currency"] == "UZS"
    assert len(rejects) == 1


def test_clean_payload_handles_broken_json():
    clean, rejects = clean_payload("{not valid json", FETCH_DATE, BASE)

    assert clean == []
    assert rejects[0].startswith("invalid JSON")


def test_deduplicate_keeps_latest_row():
    first = {"date": "2026-09-26", "base_currency": "USD",
             "target_currency": "UZS", "exchange_rate": 11800.0}
    second = {**first, "exchange_rate": 11828.0}

    assert deduplicate([first, second]) == [second]

###

