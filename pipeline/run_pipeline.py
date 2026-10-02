import argparse
import sys
import time
from datetime import date, datetime, timedelta, timezone

from pipeline import config, transform_gold, transform_silver
from pipeline.db import init_db
from pipeline.extract import fetch_for_date
from pipeline.load_bronze import (
    get_latest_fetch_date,
    get_loaded_fetch_dates,
    insert_raw,
)
from pipeline.logger import get_logger

logger = get_logger(__name__)

REQUEST_DELAY_SECONDS = 0.2

###

def utc_today() -> date:
    return datetime.now(timezone.utc).date()


def date_range(start: date, end: date) -> list[date]:
    days = (end - start).days
    return [start + timedelta(days=i) for i in range(days + 1)]


def plan_backfill(start: date, end: date, already_loaded: set[date]) -> list[date]:
    return [d for d in date_range(start, end) if d not in already_loaded]


def plan_incremental(latest_loaded: date | None, end: date, default_start: date) -> list[date]:
    start = latest_loaded + timedelta(days=1) if latest_loaded else default_start
    return date_range(start, end)

###

def fetch_and_load(dates: list[date]) -> tuple[int, int]:
    base = config.BASE_CURRENCY
    loaded, failed = 0, 0

    for i, d in enumerate(dates, start=1):
        try:
            payload = fetch_for_date(d)
        except Exception as exc:
            failed += 1
            logger.error("Failed to fetch %s after retries: %s", d, exc)
            continue

        returned_dates = {row.get("date") for row in payload if isinstance(row, dict)}
        if d.isoformat() not in returned_dates:
            logger.info(
                "No rates published for %s (API returned %s) - non-trading day, "
                "stored in Bronze, Silver will skip",
                d, sorted(returned_dates) or "nothing",
            )

        insert_raw(d, base, payload)
        loaded += 1

        if i % 50 == 0:
            logger.info("Progress: %d/%d dates processed", i, len(dates))
        time.sleep(REQUEST_DELAY_SECONDS)

    return loaded, failed

###

def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Currency exchange pipeline: Frankfurter API -> Bronze -> Silver -> Gold"
    )
    parser.add_argument(
        "--backfill", action="store_true",
        help="Load all missing historical dates instead of the daily incremental run",
    )
    parser.add_argument(
        "--start", type=date.fromisoformat,
        help="Backfill start date YYYY-MM-DD (default: BACKFILL_START_DATE in .env)",
    )
    parser.add_argument(
        "--end", type=date.fromisoformat,
        help="Last date to load YYYY-MM-DD (default: yesterday, UTC)",
    )
    return parser.parse_args(argv)

###

def main(argv=None) -> int:
    args = parse_args(argv)
    init_db()

    base = config.BASE_CURRENCY
    end = args.end or (utc_today() - timedelta(days=1))
    default_start = date.fromisoformat(config.BACKFILL_START_DATE)

    if args.backfill:
        start = args.start or default_start
        dates = plan_backfill(start, end, get_loaded_fetch_dates(base))
        mode = "backfill"
    else:
        dates = plan_incremental(get_latest_fetch_date(base), end, default_start)
        mode = "incremental"

    logger.info("Pipeline start (%s): %d dates to fetch, up to %s", mode, len(dates), end)

    loaded, failed = fetch_and_load(dates)
    transform_silver.run()
    transform_gold.run()

    logger.info(
        "Pipeline finished (%s): %d dates loaded to Bronze, %d failed",
        mode, loaded, failed,
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

###

