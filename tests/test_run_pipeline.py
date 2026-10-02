from datetime import date

from pipeline.run_pipeline import date_range, plan_backfill, plan_incremental


def test_date_range_is_inclusive():
    assert date_range(date(2026, 9, 29), date(2026, 10, 1)) == [
        date(2026, 9, 29), date(2026, 9, 30), date(2026, 10, 1),
    ]


def test_date_range_empty_when_reversed():
    assert date_range(date(2026, 10, 2), date(2026, 10, 1)) == []


def test_backfill_skips_already_loaded_dates():
    planned = plan_backfill(date(2026, 9, 25), date(2026, 9, 28), {date(2026, 9, 26)})

    assert date(2026, 9, 26) not in planned
    assert len(planned) == 3


def test_incremental_starts_after_latest_loaded_date():
    planned = plan_incremental(date(2026, 9, 29), date(2026, 10, 1), date(2024, 10, 1))

    assert planned == [date(2026, 9, 30), date(2026, 10, 1)]


def test_incremental_uses_default_start_when_bronze_empty():
    planned = plan_incremental(None, date(2024, 10, 3), date(2024, 10, 1))

    assert planned == [date(2024, 10, 1), date(2024, 10, 2), date(2024, 10, 3)]


def test_incremental_fetches_nothing_when_up_to_date():
    assert plan_incremental(date(2026, 10, 1), date(2026, 10, 1), date(2024, 10, 1)) == []

