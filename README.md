# Currency Exchange Data Pipeline
#The video link for the explanation of the project [https://drive.google.com/file/d/11v5D3TfADSf9jgwEJv-8TgOKoMNoM8-I/view?usp=sharing]

A daily data pipeline that loads exchange rates for **UZS, RUB, EUR and GBP** (base **USD**)
from the [Frankfurter API](https://frankfurter.dev) into a SQLite database, following the
**Medallion architecture** (Bronze → Silver → Gold).

Built with Python, SQLite, APScheduler and pytest.

## Architecture

```
Frankfurter API (v2)
        │  extract.py  (requests + tenacity retries)
        ▼
BRONZE  raw_rates          raw JSON per API call, append-only (immutable audit log)
        │  transform_silver.py  (parse, validate, cast, deduplicate, upsert)
        ▼
SILVER  cleaned_rates      one typed, validated row per date + currency pair
        │  transform_gold.py  (dimensions) + SQL view (metrics)
        ▼
GOLD    aggregated_rates   fact view: day-over-day change, 7/30-day averages
        dim_currencies     currency name, symbol, country
        dim_dates          continuous calendar with is_weekday flag
```

### Python vs SQL per layer

| Layer | Object | Implemented as | Why |
|---|---|---|---|
| Bronze | `raw_rates` | Python, append-only table | Stores every API response exactly as received. Triggers block UPDATE/DELETE, so immutability is enforced by the database, not just by convention. |
| Silver | `cleaned_rates` | Python, populated table | Validation rules are easier to express, log and unit-test in Python. Each rejected record is logged with a reason. |
| Gold | `dim_currencies` | Python, from `reference/currencies.csv` | Reference data lives in a file, not in code. |
| Gold | `dim_dates` | Python, generated | Continuous calendar built from the Silver date range. |
| Gold | `aggregated_rates` | **SQL view** | Window functions (`LAG`, `AVG OVER`) are what SQL does best, and a view is always in sync with Silver - no refresh logic needed. |

### Data model (star schema)

```
dim_currencies (currency_code PK) ──1:N── aggregated_rates ──N:1── dim_dates (date PK)
                                  on target_currency          on date
```

`aggregated_rates` columns: `date`, `base_currency`, `target_currency`, `currency_name`,
`is_weekday`, `exchange_rate`, `prev_date`, `prev_rate`, `rate_change_abs`,
`rate_change_pct`, `avg_7_day`, `obs_in_7_day`, `avg_30_day`, `inverse_rate`.

## Repository structure

```
currency-exchange/
├── README.md
├── .env.example                 # template for all settings
├── requirements.txt
├── pipeline/
│   ├── config.py                # reads .env (no hardcoded settings)
│   ├── logger.py                # console + logs/pipeline.log
│   ├── db.py                    # SQLite connection + schema init
│   ├── extract.py               # Frankfurter API calls with retries
│   ├── load_bronze.py           # append-only Bronze writes + incremental helpers
│   ├── transform_silver.py      # parse, validate, deduplicate → Silver
│   ├── transform_gold.py        # dimensions + applies Gold SQL views
│   ├── run_pipeline.py          # orchestrator: daily incremental run / --backfill
│   └── scheduler.py             # APScheduler daily job
├── sql/
│   ├── schema.sql               # Bronze, Silver, dimension tables + triggers
│   └── views/
│       └── gold_aggregated_rates.sql
├── reference/
│   └── currencies.csv           # dim_currencies source data
└── tests/                       # pytest unit tests
```

`data/` (SQLite database) and `logs/` are created automatically and are not committed.

## Setup

Requires **Python 3.10+** and Git.

```bash
git clone https://github.com/Bekzod5506/currency-exchange.git
cd currency-exchange
python -m venv .venv
```

Activate the virtual environment:

```bash
# Windows (PowerShell)
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate
```

> On Windows, if activation fails with "running scripts is disabled", run once:
> `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`

Install dependencies and create your settings file:

```bash
pip install -r requirements.txt
copy .env.example .env      # Windows
cp .env.example .env        # macOS / Linux
```

The database and all tables are created automatically on the first run.

## Configuration (`.env`)

| Variable | Example | Purpose |
|---|---|---|
| `DB_PATH` | `data/currency.db` | SQLite database file |
| `API_BASE_URL` | `https://api.frankfurter.dev/v2` | Frankfurter API |
| `BASE_CURRENCY` | `USD` | Base currency for all rates |
| `TARGET_CURRENCIES` | `UZS,RUB,EUR,GBP` | Comma-separated target currencies |
| `BACKFILL_START_DATE` | `2024-10-01` | First date of the historical load |
| `LOG_LEVEL` | `INFO` | `DEBUG` also shows each skipped non-trading record |
| `SCHEDULE_TIMEZONE` | `Asia/Tashkent` | Timezone for the daily schedule |
| `SCHEDULE_HOUR` / `SCHEDULE_MINUTE` | `7` / `30` | Daily run time (must be before 08:00) |

To add a currency: add its code to `TARGET_CURRENCIES` and a row to `reference/currencies.csv`.

## How to run

All commands are run from the project root with the virtual environment active.
Use `python -m pipeline.<module>` (not `python pipeline/<file>.py`) so package imports work.

### 1. Historical backfill

```bash
python -m pipeline.run_pipeline --backfill
```

Loads every missing date from `BACKFILL_START_DATE` to yesterday (about 2 years, ~730 API
calls, 10-20 minutes) using the dated endpoint in a loop, then refreshes Silver and Gold.
The backfill is **resumable**: dates already in Bronze are skipped, so it can be stopped
with Ctrl+C and restarted safely.

Custom range:

```bash
python -m pipeline.run_pipeline --backfill --start 2026-01-01 --end 2026-03-31
```

### 2. Daily incremental run

```bash
python -m pipeline.run_pipeline
```

Checks the latest date in Bronze and fetches only the dates after it, up to yesterday (UTC),
then refreshes Silver and Gold. Running it twice in a row fetches nothing the second time.
Exit code is `0` on success and `1` if any date failed (failed dates are retried on the next run).

### 3. Scheduler

```bash
python -m pipeline.scheduler            # waits and runs daily at 07:30 Asia/Tashkent
python -m pipeline.scheduler --run-now  # runs once immediately, then keeps the schedule
```

Stop with Ctrl+C. All options: `python -m pipeline.run_pipeline --help`

### 4. Tests

```bash
python -m pytest -v
```

31 tests covering Silver validation (invalid rates, missing fields, non-trading days,
deduplication, broken JSON), date dimension generation, currency reference loading,
Gold view metrics (on a temporary database), and backfill/incremental date planning.

### Querying Gold

```sql
SELECT r.date, c.name, r.exchange_rate, r.rate_change_pct, r.avg_7_day
FROM aggregated_rates r
JOIN dim_currencies c ON c.currency_code = r.target_currency
JOIN dim_dates d      ON d.date = r.date
WHERE r.target_currency = 'UZS' AND d.is_weekday = 1
ORDER BY r.date DESC
LIMIT 10;
```

## Scheduling

**Choice: APScheduler** (over `schedule`), because it supports timezones natively - the job is
defined directly in `Asia/Tashkent` and runs at the right time regardless of the server's timezone.

- Runs daily at **07:30 Tashkent (02:30 UTC)**, 30 minutes before the 08:00 deadline to leave
  time for retries. A warning is logged if the configured time is after 08:00.
- Loads data **up to yesterday (UTC)**. At 02:30 UTC most central banks have not yet published
  today's rate; requesting today would store yesterday's rate under today's date and the real
  rate would never be fetched. So "fresh by 8 AM" means yesterday's final rates are in Gold by 8 AM.
- `max_instances=1` prevents overlapping runs, `coalesce=True` runs once after missed runs
  (the incremental logic catches up all missing dates anyway), `misfire_grace_time=3600`
  still runs the job if the scheduler wakes up late.
- Uses `BackgroundScheduler` with a keep-alive loop, because `BlockingScheduler` does not
  respond to Ctrl+C on Windows.
- **Production note:** the scheduler only runs while its process is running. On a server,
  run it as a service, or skip it and call `python -m pipeline.run_pipeline` from
  Windows Task Scheduler / cron at 07:30.

## Incremental logic and non-trading days

- Before fetching, the pipeline reads `MAX(fetch_date)` from Bronze and fetches only newer dates.
- Each API response is stored in Bronze even for non-trading days, so they are not re-requested.
- If the API returns a different date than requested (fallback to the last trading day),
  the pipeline logs it and Silver skips those records. Nothing fails.
- In practice the v2 blended feed often returns rates dated on weekends too, so the safeguard
  rarely triggers - but it is in place for providers that skip non-trading days.

## Data quality and error handling

- **Retries:** API calls retry up to 4 times with exponential backoff (tenacity) on network
  errors, HTTP 429 and 5xx. 4xx errors (bad request) fail immediately - retrying would not help.
- **Silver validation:** required fields present, valid ISO date, date matches the requested
  date, expected base currency, 3-letter currency code, numeric and finite rate, rate > 0.
  Rejected records are logged as WARNING with the Bronze row id; nothing is silently dropped.
- **Database constraints** back up the Python rules: `CHECK (exchange_rate > 0)` and a
  composite primary key on `(date, base_currency, target_currency)`.
- **Idempotent:** Silver uses an upsert that only updates rows whose rate changed, so re-running
  any step never creates duplicates.
- **Logging:** every step logs what was fetched, how many rows were written, and what was
  skipped or rejected - to the console and to `logs/pipeline.log`.

## Assumptions

- **USD is the base currency**; USD itself is not a target (USD→USD is always 1).
- **Frankfurter v2** is used: the legacy v1 endpoints (`/latest`, `/[date]`) only serve ECB data,
  which does not include UZS or RUB. v2 `/rates` and `/rates?date=` are the equivalents.
- Rates are **daily, mid-market, blended** across providers; no intra-day updates.
- **Bronze is an immutable log**; all corrections happen in Silver.
- Timestamps (`inserted_at`, `load_timestamp`) are stored in **UTC**.
- SQLite has no DECIMAL type, so rates are stored as REAL rounded to 6 decimals.
- `7_day_avg` from the brief is named `avg_7_day`, because SQL identifiers cannot start with a digit.
- The 7-day average covers **7 calendar days** (`RANGE` over `julianday`), not the last 7 rows,
  so gaps in the data do not stretch the window.

## Problems encountered

- **UZS and RUB missing in v1** → switched to the v2 API.
- **Mixed dates in `/latest`**: one response contained EUR/RUB dated tomorrow and GBP/UZS dated
  today (some central banks publish next-day rates). → Each row keeps its own date, and the daily
  run requests explicit dates instead of `latest`.
- **UZS returned as an integer** (`11828` vs `0.877`) → all rates cast to float in Silver.
- **NaN and booleans pass naive checks** (`NaN <= 0` is False; `True` is an int) → explicit checks.
- **Deduplication** → latest Bronze fetch wins (read in id order) + composite primary key + upsert.
- **Scheduler would not stop on Windows** → switched to `BackgroundScheduler`.

