-- =========================
-- GOLD: aggregated_rates (fact view over Silver)
-- =========================
DROP VIEW IF EXISTS aggregated_rates;

CREATE VIEW aggregated_rates AS

---

WITH windowed AS (
    SELECT
        date,
        base_currency,
        target_currency,
        exchange_rate,
        LAG(exchange_rate) OVER w AS prev_rate,
        LAG(date)          OVER w AS prev_date,
        AVG(exchange_rate) OVER (w RANGE BETWEEN 6 PRECEDING AND CURRENT ROW)  AS avg_7_day,
        COUNT(*)           OVER (w RANGE BETWEEN 6 PRECEDING AND CURRENT ROW)  AS obs_in_7_day,
        AVG(exchange_rate) OVER (w RANGE BETWEEN 29 PRECEDING AND CURRENT ROW) AS avg_30_day
    FROM cleaned_rates
    WINDOW w AS (
        PARTITION BY base_currency, target_currency
        ORDER BY julianday(date)
    )
)

---

SELECT
    w.date,
    w.base_currency,
    w.target_currency,
    c.name                                        AS currency_name,
    d.is_weekday,
    w.exchange_rate,
    w.prev_date,
    w.prev_rate,
    ROUND(w.exchange_rate - w.prev_rate, 6)       AS rate_change_abs,
    ROUND((w.exchange_rate - w.prev_rate) * 100.0
          / w.prev_rate, 4)                       AS rate_change_pct,
    ROUND(w.avg_7_day, 6)                         AS avg_7_day,
    w.obs_in_7_day,
    ROUND(w.avg_30_day, 6)                        AS avg_30_day,
    ROUND(1.0 / w.exchange_rate, 10)              AS inverse_rate
FROM windowed AS w
LEFT JOIN dim_currencies AS c ON c.currency_code = w.target_currency
LEFT JOIN dim_dates      AS d ON d.date          = w.date;

