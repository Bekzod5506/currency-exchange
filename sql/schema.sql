-- =========================
-- BRONZE: raw API responses (append-only audit log)
-- =========================
CREATE TABLE IF NOT EXISTS raw_rates (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    fetch_date     TEXT NOT NULL,
    base_currency  TEXT NOT NULL,
    raw_json       TEXT NOT NULL,
    inserted_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

-------

CREATE TRIGGER IF NOT EXISTS trg_raw_rates_no_update
BEFORE UPDATE ON raw_rates
BEGIN
    SELECT RAISE(ABORT, 'raw_rates is append-only: UPDATE not allowed');
END;

CREATE TRIGGER IF NOT EXISTS trg_raw_rates_no_delete
BEFORE DELETE ON raw_rates
BEGIN
    SELECT RAISE(ABORT, 'raw_rates is append-only: DELETE not allowed');
END;



-- =========================
-- SILVER: cleaned, validated, typed rates
-- =========================
CREATE TABLE IF NOT EXISTS cleaned_rates (
    date             TEXT NOT NULL,
    base_currency    TEXT NOT NULL,
    target_currency  TEXT NOT NULL,
    exchange_rate    REAL NOT NULL CHECK (exchange_rate > 0),
    load_timestamp   TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (date, base_currency, target_currency)
);


-- =========================
-- GOLD: dimensions
-- =========================
CREATE TABLE IF NOT EXISTS dim_currencies (
    currency_code  TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    symbol         TEXT,
    country        TEXT
);

CREATE TABLE IF NOT EXISTS dim_dates (
    date        TEXT PRIMARY KEY,
    year        INTEGER NOT NULL,
    month       INTEGER NOT NULL,
    day         INTEGER NOT NULL,
    is_weekday  INTEGER NOT NULL CHECK (is_weekday IN (0, 1))
);


