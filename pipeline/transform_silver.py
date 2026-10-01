import json
import math
from datetime import date

from pipeline.db import get_connection
from pipeline.logger import get_logger

logger = get_logger(__name__)

RATE_DECIMALS = 6

###

def validate_record(record, fetch_date: str, expected_base: str):
    if not isinstance(record, dict):
        return None, "record is not an object"

    for field in ("date", "base", "quote", "rate"):
        if record.get(field) in (None, ""):
            return None, f"missing {field}"

    try:
        rate_date = date.fromisoformat(str(record["date"]))
    except ValueError:
        return None, f"invalid date {record['date']!r}"

    if rate_date.isoformat() != fetch_date:
        return None, f"non-trading day: requested {fetch_date}, got {rate_date}"
    base = str(record["base"]).strip().upper()
    if base != expected_base:
        return None, f"unexpected base {base}, expected {expected_base}"

    quote = str(record["quote"]).strip().upper()
    if len(quote) != 3 or not quote.isalpha():
        return None, f"invalid currency code {quote!r}"

    rate = record["rate"]
    if isinstance(rate, bool) or not isinstance(rate, (int, float)):
        return None, f"non-numeric rate {rate!r}"
    if not math.isfinite(rate):
        return None, f"non-finite rate {rate!r}"
    if rate <= 0:
        return None, f"rate must be > 0, got {rate}"

    clean_row = {
        "date": rate_date.isoformat(),
        "base_currency": base,
        "target_currency": quote,
        "exchange_rate": round(float(rate), RATE_DECIMALS),
    }
    return clean_row, None

    
###

def clean_payload(raw_json: str, fetch_date: str, expected_base: str):
    try:
        records = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        return [], [f"invalid JSON: {exc}"]

    if not isinstance(records, list):
        return [], ["payload is not a list"]

    clean_rows, rejects = [], []
    for record in records:
        row, reason = validate_record(record, fetch_date, expected_base)
        if row is not None:
            clean_rows.append(row)
        else:
            rejects.append(reason)
    return clean_rows, rejects

###

def deduplicate(rows: list[dict]) -> list[dict]:
    unique = {}
    for row in rows:
        key = (row["date"], row["base_currency"], row["target_currency"])
        unique[key] = row
    return list(unique.values())

###

def run() -> int:
    conn = get_connection()
    try:
        bronze_rows = conn.execute(
            "SELECT id, fetch_date, base_currency, raw_json "
            "FROM raw_rates ORDER BY id"
        ).fetchall()

        all_clean = []
        non_trading = 0
        invalid = 0

        for b in bronze_rows:
            clean, rejects = clean_payload(
                b["raw_json"], b["fetch_date"], b["base_currency"]
            )
            all_clean.extend(clean)

            for reason in rejects:
                if reason.startswith("non-trading day"):
                    non_trading += 1
                    logger.debug("Silver skip (bronze id=%d): %s", b["id"], reason)
                else:
                    invalid += 1
                    logger.warning("Silver reject (bronze id=%d): %s", b["id"], reason)
        unique_rows = deduplicate(all_clean)
        duplicates = len(all_clean) - len(unique_rows)

        changes_before = conn.total_changes
        conn.executemany(
            """
            INSERT INTO cleaned_rates
                (date, base_currency, target_currency, exchange_rate)
            VALUES
                (:date, :base_currency, :target_currency, :exchange_rate)
            ON CONFLICT (date, base_currency, target_currency) DO UPDATE SET
                exchange_rate  = excluded.exchange_rate,
                load_timestamp = datetime('now')
            WHERE cleaned_rates.exchange_rate <> excluded.exchange_rate
            """,
            unique_rows,
        )
        conn.commit()
        written = conn.total_changes - changes_before
    finally:
        conn.close()

    logger.info(
        "Silver: %d bronze rows read | %d valid records | %d duplicates removed | "
        "%d non-trading skipped | %d invalid rejected | %d rows inserted/updated",
        len(bronze_rows), len(all_clean), duplicates,
        non_trading, invalid, written,
    )
    return written

###

if __name__ == "__main__":
    run()

    conn = get_connection()
    for r in conn.execute(
        "SELECT * FROM cleaned_rates ORDER BY date, target_currency"
    ):
        print(dict(r))
    conn.close()





