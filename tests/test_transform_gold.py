from datetime import date

import pytest

from pipeline import config
from pipeline.db import get_connection, init_db
from pipeline.transform_gold import apply_views, build_date_rows, load_currency_reference

###

def test_date_rows_cover_every_calendar_day():
    rows = build_date_rows(date(2026, 9, 25), date(2026, 10, 1))

    assert len(rows) == 7
    assert rows[0]["date"] == "2026-09-25"
    assert rows[-1]["date"] == "2026-10-01"


def test_weekday_flag():
    rows = {r["date"]: r for r in build_date_rows(date(2026, 9, 25), date(2026, 9, 28))}

    assert rows["2026-09-25"]["is_weekday"] == 1   # Friday
    assert rows["2026-09-26"]["is_weekday"] == 0   # Saturday
    assert rows["2026-09-27"]["is_weekday"] == 0   # Sunday
    assert rows["2026-09-28"]["is_weekday"] == 1   # Monday


def test_date_parts_on_leap_day():
    row = build_date_rows(date(2024, 2, 29), date(2024, 2, 29))[0]

    assert (row["year"], row["month"], row["day"]) == (2024, 2, 29)


def test_no_dates_when_end_before_start():
    assert build_date_rows(date(2026, 10, 2), date(2026, 10, 1)) == []

###

def test_currency_reference_is_cleaned(tmp_path):
    csv_file = tmp_path / "currencies.csv"
    csv_file.write_text(
        "currency_code,name,symbol,country\n"
        " uzs ,Uzbekistani Som,so'm,Uzbekistan\n"
        ",,,\n",
        encoding="utf-8",
    )

    rows = load_currency_reference(csv_file)

    assert rows == [{
        "currency_code": "UZS",
        "name": "Uzbekistani Som",
        "symbol": "so'm",
        "country": "Uzbekistan",
    }]

###

def _gold_rows(tmp_path, monkeypatch, rates):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    init_db()

    conn = get_connection()
    try:
        conn.executemany(
            "INSERT INTO cleaned_rates (date, base_currency, target_currency, exchange_rate) "
            "VALUES (?, 'USD', 'EUR', ?)",
            rates,
        )
        conn.commit()
        apply_views(conn)
        return conn.execute(
            "SELECT date, rate_change_pct, avg_7_day, obs_in_7_day "
            "FROM aggregated_rates ORDER BY date"
        ).fetchall()
    finally:
        conn.close()

###

def test_gold_day_over_day_and_7_day_average(tmp_path, monkeypatch):
    rows = _gold_rows(tmp_path, monkeypatch, [
        ("2026-09-28", 0.80),
        ("2026-09-29", 0.88),
        ("2026-09-30", 0.90),
    ])

    assert rows[0]["rate_change_pct"] is None
    assert rows[1]["rate_change_pct"] == pytest.approx(10.0)
    assert rows[2]["avg_7_day"] == pytest.approx((0.80 + 0.88 + 0.90) / 3)
    assert rows[2]["obs_in_7_day"] == 3


def test_gold_7_day_window_uses_calendar_days(tmp_path, monkeypatch):
    rows = _gold_rows(tmp_path, monkeypatch, [
        ("2026-09-01", 1.0),
        ("2026-09-10", 2.0),
    ])

    assert rows[1]["avg_7_day"] == pytest.approx(2.0)
    assert rows[1]["obs_in_7_day"] == 1

###

