import logging
from datetime import date

import requests
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from pipeline import config
from pipeline.logger import get_logger

logger = get_logger(__name__)

TIMEOUT_SECONDS = 30

###

def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, (requests.ConnectionError, requests.Timeout)):
        return True
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        status = exc.response.status_code
        return status == 429 or status >= 500
    return False

###

@retry(
    retry=retry_if_exception(_is_retryable),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def _get_json(url: str, params: dict):
    response = requests.get(url, params=params, timeout=TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.json()

###

def fetch_rates(
    rate_date: date | None = None,
    base: str | None = None,
    targets: list[str] | None = None,
) -> list[dict]:
    base = base or config.BASE_CURRENCY
    targets = targets or config.TARGET_CURRENCIES

    params = {"base": base, "quotes": ",".join(targets)}
    if rate_date is not None:
        params["date"] = rate_date.isoformat()

    label = rate_date.isoformat() if rate_date else "latest"
    url = f"{config.API_BASE_URL}/rates"

    logger.info("Fetching %s rates: base=%s quotes=%s", label, base, params["quotes"])
    data = _get_json(url, params)

    if not isinstance(data, list):
        raise ValueError(f"Unexpected API response for {label}: {data!r}")

    logger.info("Received %d rate rows for %s", len(data), label)
    return data

###

def fetch_latest() -> list[dict]:
    return fetch_rates()


def fetch_for_date(rate_date: date) -> list[dict]:
    return fetch_rates(rate_date=rate_date)

###

if __name__ == "__main__":
    for row in fetch_latest():
        print(row)
    for row in fetch_for_date(date(2026, 9, 26)):
        print(row)