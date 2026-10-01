import json
from datetime import date

from pipeline.db import get_connection
from pipeline.logger import get_logger

logger = get_logger(__name__)

###

def insert_raw(fetch_date: date, base_currency: str, payload: list[dict]) -> int:
    raw_json = json.dumps(payload, ensure_ascii=False)

    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO raw_rates (fetch_date, base_currency, raw_json) "
            "VALUES (?, ?, ?)",
            (fetch_date.isoformat(), base_currency, raw_json),
        )
        conn.commit()
        row_id = cursor.lastrowid
    finally:
        conn.close()

    logger.info(
        "Bronze: inserted raw_rates id=%d fetch_date=%s (%d rate rows in payload)",
        row_id, fetch_date, len(payload),
    )
    return row_id

###

def get_latest_fetch_date(base_currency: str) -> date | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT MAX(fetch_date) AS max_date FROM raw_rates "
            "WHERE base_currency = ?",
            (base_currency,),
        ).fetchone()
    finally:
        conn.close()

    if row["max_date"] is None:
        return None
    return date.fromisoformat(row["max_date"])

###

def get_loaded_fetch_dates(base_currency: str) -> set[date]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT DISTINCT fetch_date FROM raw_rates WHERE base_currency = ?",
            (base_currency,),
        ).fetchall()
    finally:
        conn.close()

    return {date.fromisoformat(r["fetch_date"]) for r in rows}

###

if __name__ == "__main__":
    import sqlite3

    from pipeline import config
    from pipeline.extract import fetch_for_date

    test_date = date(2026, 9, 26)
    base = config.BASE_CURRENCY

    if test_date in get_loaded_fetch_dates(base):
        print(f"{test_date} already in Bronze, skipping insert")
    else:
        insert_raw(test_date, base, fetch_for_date(test_date))

    print("Latest fetch_date in Bronze:", get_latest_fetch_date(base))

    conn = get_connection()
    try:
        conn.execute("DELETE FROM raw_rates")
        print("ERROR: delete was allowed!")
    except sqlite3.DatabaseError as exc:
        print("Immutability check passed:", exc)
    finally:
        conn.close()

