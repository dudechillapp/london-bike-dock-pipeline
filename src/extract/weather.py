"""Pull hourly London weather from Open-Meteo into raw.weather_response.

First run: backfills the last 365 days. Later runs: only fetch what's new.
- 'archive'  final values, published about 5 days late
- 'recent'   the last 7 days, to fill the gap until the archive catches up

Times are requested in UTC (GMT), not London time, so the clock change in
spring and autumn never creates a duplicate or a missing hour.

Run from the project folder:
    python -m src.extract.weather
"""

import json
import logging
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import psycopg
import requests
from dotenv import load_dotenv

load_dotenv()

LONDON = {"latitude": 51.5072, "longitude": -0.1276}
HOURLY = "temperature_2m,precipitation,wind_speed_10m"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
RECENT_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_DELAY_DAYS = 6       # archive is about 5 days behind; 6 to be safe
BACKFILL_DAYS = 365

LOG_DIR = Path(__file__).resolve().parents[2] / "logs"
LOG_DIR.mkdir(exist_ok=True)
handlers = [logging.FileHandler(LOG_DIR / "weather.log", encoding="utf-8")]
if sys.stderr is not None:
    handlers.append(logging.StreamHandler())
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    handlers=handlers)
log = logging.getLogger("weather")


def warehouse_dsn() -> str:
    return os.environ["WAREHOUSE_URL"].replace("postgresql+psycopg://", "postgresql://")


def get(url: str, params: dict, retries: int = 4) -> dict:
    """GET with a timeout, retrying with exponential backoff on 429 and 5xx."""
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, timeout=60)
        except requests.RequestException as e:
            log.warning("Attempt %s: network error %s", attempt + 1, e)
        else:
            if r.status_code == 200:
                data = r.json()
                if not data.get("hourly", {}).get("time"):
                    raise ValueError(f"No hourly data in response: {str(data)[:200]}")
                return data
            if r.status_code != 429 and r.status_code < 500:
                raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
            log.warning("Attempt %s: HTTP %s", attempt + 1, r.status_code)
        time.sleep(2 ** attempt)
    raise RuntimeError(f"Open-Meteo still failing after {retries} attempts")


def save(conn, source: str, start: date, end: date, payload: dict) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO raw.weather_response (pulled_at, source, start_date, end_date, payload) "
            "VALUES (%s, %s, %s, %s, %s::jsonb)",
            (datetime.now(timezone.utc), source, start, end, json.dumps(payload)),
        )
    conn.commit()
    log.info("Saved %s weather %s to %s (%s hours)",
             source, start, end, len(payload["hourly"]["time"]))


def main() -> None:
    today = datetime.now(timezone.utc).date()
    try:
        with psycopg.connect(warehouse_dsn()) as conn:
            # 1. Archive: from the day after the last archive pull (or a year ago) up to 6 days ago
            with conn.cursor() as cur:
                cur.execute("SELECT max(end_date) FROM raw.weather_response WHERE source = 'archive'")
                last_end = cur.fetchone()[0]
            start = (last_end + timedelta(days=1)) if last_end else today - timedelta(days=BACKFILL_DAYS)
            end = today - timedelta(days=ARCHIVE_DELAY_DAYS)
            if start <= end:
                data = get(ARCHIVE_URL, {**LONDON, "hourly": HOURLY, "timezone": "GMT",
                                         "start_date": start.isoformat(), "end_date": end.isoformat()})
                save(conn, "archive", start, end, data)
            else:
                log.info("Archive already up to date (last day %s)", last_end)

            # 2. Recent: the last 7 days, until the archive catches up
            data = get(RECENT_URL, {**LONDON, "hourly": HOURLY, "timezone": "GMT",
                                    "past_days": 7, "forecast_days": 1})
            save(conn, "recent", today - timedelta(days=7), today, data)
    except Exception:
        log.exception("Weather run failed")
        raise


if __name__ == "__main__":
    main()
