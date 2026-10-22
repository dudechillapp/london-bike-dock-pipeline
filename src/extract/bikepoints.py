"""Pull the live status of every Santander Cycles dock from the TfL BikePoint API
and store the full response, untouched, in raw.bikepoint_snapshot.

Run from the project folder:
    python -m src.extract.bikepoints
"""

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import psycopg
import requests
from dotenv import load_dotenv

load_dotenv()  # reads DB settings and the optional TfL key from .env

URL = "https://api.tfl.gov.uk/BikePoint"
MIN_EXPECTED_DOCKS = 500  # London has about 800; far fewer means a broken response

# Log to logs/collector.log (kept out of Git) and to the screen when there is one.
# Task Scheduler runs this with pythonw, which has no screen, so the file matters.
LOG_DIR = Path(__file__).resolve().parents[2] / "logs"
LOG_DIR.mkdir(exist_ok=True)
handlers = [logging.FileHandler(LOG_DIR / "collector.log", encoding="utf-8")]
if sys.stderr is not None:
    handlers.append(logging.StreamHandler())
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    handlers=handlers)
log = logging.getLogger("bikepoints")


def warehouse_dsn() -> str:
    """psycopg wants postgresql://..., SQLAlchemy wants postgresql+psycopg://...
    so .env keeps one URL and this converts it."""
    return os.environ["WAREHOUSE_URL"].replace("postgresql+psycopg://", "postgresql://")


def fetch(retries: int = 4) -> list[dict]:
    """Call the API with a timeout, and retry with exponential backoff
    when TfL rate-limits us (429) or has a server error (5xx)."""
    params = {}
    app_key = os.getenv("TFL_APP_KEY")
    if app_key:  # optional: works without a key, a key just raises the rate limit
        params["app_key"] = app_key

    for attempt in range(retries):
        try:
            r = requests.get(URL, params=params, timeout=30)
        except requests.RequestException as e:
            log.warning("Attempt %s: network error %s", attempt + 1, e)
        else:
            if r.status_code == 200:
                docks = r.json()
                if len(docks) < MIN_EXPECTED_DOCKS:
                    raise ValueError(f"Only {len(docks)} docks returned, expected about 800")
                return docks
            if r.status_code != 429 and r.status_code < 500:
                r.raise_for_status()  # a 4xx like 401 won't fix itself, so stop now
            log.warning("Attempt %s: HTTP %s", attempt + 1, r.status_code)
        time.sleep(2 ** attempt)  # wait 1, 2, 4, 8 seconds

    raise RuntimeError(f"TfL API still failing after {retries} attempts")


def load(docks: list[dict], conn: psycopg.Connection) -> datetime:
    """Insert the whole response as one row. Raw data is never edited."""
    pulled_at = datetime.now(timezone.utc)
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO raw.bikepoint_snapshot (pulled_at, payload) VALUES (%s, %s::jsonb)",
            (pulled_at, json.dumps(docks)),
        )
    conn.commit()
    return pulled_at


def main() -> None:
    try:
        docks = fetch()
        with psycopg.connect(warehouse_dsn()) as conn:
            pulled_at = load(docks, conn)
    except Exception:
        log.exception("Collector run failed")  # full error goes into the log file
        raise
    log.info("Saved %s docks at %s", len(docks), pulled_at.isoformat(timespec="seconds"))


if __name__ == "__main__":
    main()
