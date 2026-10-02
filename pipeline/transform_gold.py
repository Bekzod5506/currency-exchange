import csv
from datetime import date, timedelta

from pipeline import config
from pipeline.db import get_connection
from pipeline.logger import get_logger

logger = get_logger(__name__)

###

def load_currency_reference(path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    return [
        {
            "currency_code": r["currency_code"].strip().upper(),
            "name": r["name"].strip(),
            "symbol": r["symbol"].strip() or None,
            "country": r["country"].strip() or None,
        }
        for r in rows
        if r["currency_code"].strip()
    ]

###

def build_date_rows(start: date, end: date) -> list[dict]:
    rows = []
    current = start
    while current <= end:
        rows.append({
            "date": current.isoformat(),
            "year": current.year,
            "month": current.month,
            "day": current.day,
            "is_weekday": 1 if current.weekday() < 5 else 0,
        })
        current += timedelta(days=1)
    return rows

###

def refresh_dim_currencies(conn) -> int:
    rows = load_currency_reference(config.REFERENCE_DIR / "currencies.csv")

    conn.executemany(
        """
        INSERT INTO dim_currencies (currency_code, name, symbol, country)
        VALUES (:currency_code, :name, :symbol, :country)
        ON CONFLICT (currency_code) DO UPDATE SET
            name    = excluded.name,
            symbol  = excluded.symbol,
            country = excluded.country
        """,
        rows,
    )

    known = {r["currency_code"] for r in rows}
    needed = {config.BASE_CURRENCY, *config.TARGET_CURRENCIES}
    missing = needed - known
    if missing:
        logger.warning(
            "dim_currencies: no reference data for %s - add them to reference/currencies.csv",
            sorted(missing),
        )
    return len(rows)

###

def refresh_dim_dates(conn) -> int:
    row = conn.execute(
        "SELECT MIN(date) AS min_d, MAX(date) AS max_d FROM cleaned_rates"
    ).fetchone()

    if row["min_d"] is None:
        logger.warning("dim_dates: Silver is empty, nothing to build")
        return 0

    rows = build_date_rows(
        date.fromisoformat(row["min_d"]), date.fromisoformat(row["max_d"])
    )

    changes_before = conn.total_changes
    conn.executemany(
        "INSERT OR IGNORE INTO dim_dates (date, year, month, day, is_weekday) "
        "VALUES (:date, :year, :month, :day, :is_weekday)",
        rows,
    )
    return conn.total_changes - changes_before

###

def apply_views(conn) -> list[str]:
    applied = []
    for sql_file in sorted(config.VIEWS_DIR.glob("*.sql")):
        conn.executescript(sql_file.read_text(encoding="utf-8"))
        applied.append(sql_file.name)
    return applied

###

def run() -> None:
    conn = get_connection()
    try:
        n_currencies = refresh_dim_currencies(conn)
        n_new_dates = refresh_dim_dates(conn)
        conn.commit()

        views = apply_views(conn)
        n_fact = conn.execute(
            "SELECT COUNT(*) AS n FROM aggregated_rates"
        ).fetchone()["n"]
    finally:
        conn.close()

    logger.info(
        "Gold: %d currencies in dim_currencies | %d new dates in dim_dates | "
        "views applied: %s | %d rows in aggregated_rates",
        n_currencies, n_new_dates, ", ".join(views), n_fact,
    )


###

if __name__ == "__main__":
    run()

    conn = get_connection()
    for r in conn.execute(
        "SELECT * FROM aggregated_rates ORDER BY target_currency, date"
    ):
        print(dict(r))
    conn.close()

