"""Download TfL Santander Cycles journey files and load them into raw.journeys.

TfL publishes one CSV per half month at cycling.data.tfl.gov.uk/usage-stats/,
usually a few months late. By default this loads the newest 12 months available.

Old and new files use different column headers. Each header is mapped to one
set of names, and an unknown header stops the load instead of loading it wrong.

Run from the project folder:
    python -m src.extract.journeys              # newest 12 months
    python -m src.extract.journeys --months 3   # fewer, for a quick test
"""

import argparse
import csv
import logging
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from pathlib import Path

import psycopg
import requests
from dotenv import load_dotenv

load_dotenv()

BUCKET = "https://s3-eu-west-1.amazonaws.com/cycling.data.tfl.gov.uk/"
FILE_URL = "https://cycling.data.tfl.gov.uk/usage-stats/"
NAME_RE = re.compile(r"^usage-stats/(\d+)JourneyDataExtract(\d{2}[A-Za-z]{3}\d{4})-(\d{2}[A-Za-z]{3}\d{4})\.csv$")

ROOT = Path(__file__).resolve().parents[2]
DOWNLOAD_DIR = ROOT / "data" / "journeys"     # data/ is in .gitignore
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)
handlers = [logging.FileHandler(LOG_DIR / "journeys.log", encoding="utf-8")]
if sys.stderr is not None:
    handlers.append(logging.StreamHandler())
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    handlers=handlers)
log = logging.getLogger("journeys")

# Every header TfL has used, normalised (lower case, no spaces or brackets) -> our column
HEADER_MAP = {
    # newer format (from about late 2022)
    "number": "rental_id",
    "startdate": "start_time",
    "startstationnumber": "start_station_id",
    "startstation": "start_station_name",
    "enddate": "end_time",
    "endstationnumber": "end_station_id",
    "endstation": "end_station_name",
    "bikenumber": "bike_id",
    "bikemodel": "bike_model",
    "totalduration": "duration_text",
    "totaldurationms": "duration_ms",
    # older format
    "rentalid": "rental_id",
    "duration": "duration_s",
    "bikeid": "bike_id",
    "startstationid": "start_station_id",
    "startstationname": "start_station_name",
    "endstationid": "end_station_id",
    "endstationname": "end_station_name",
}
COLUMNS = ["rental_id", "start_time", "start_station_id", "start_station_name", "end_time",
           "end_station_id", "end_station_name", "bike_id", "bike_model", "duration_text",
           "duration_ms", "duration_s"]


def normalise(header: str) -> str:
    return re.sub(r"[^a-z]", "", header.lower())


def warehouse_dsn() -> str:
    return os.environ["WAREHOUSE_URL"].replace("postgresql+psycopg://", "postgresql://")


def get(url: str, retries: int = 4, **kwargs) -> requests.Response:
    for attempt in range(retries):
        try:
            r = requests.get(url, timeout=120, **kwargs)
            if r.status_code == 200:
                return r
            if r.status_code != 429 and r.status_code < 500:
                r.raise_for_status()
            log.warning("Attempt %s: HTTP %s for %s", attempt + 1, r.status_code, url)
        except requests.RequestException as e:
            log.warning("Attempt %s: %s", attempt + 1, e)
        time.sleep(2 ** attempt)
    raise RuntimeError(f"Still failing after {retries} attempts: {url}")


def list_files() -> list[dict]:
    """Read the bucket listing (S3 XML, 1,000 keys per page) and keep journey CSVs."""
    ns = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
    files, marker = [], ""
    while True:
        xml = get(BUCKET, params={"prefix": "usage-stats/", "marker": marker}).text
        tree = ET.fromstring(xml)
        keys = tree.findall("s3:Contents", ns)
        for c in keys:
            key = c.find("s3:Key", ns).text
            m = NAME_RE.match(key)
            if m:
                files.append({
                    "name": key.split("/", 1)[1],
                    "number": int(m.group(1)),
                    "start": datetime.strptime(m.group(2), "%d%b%Y").date(),
                    "end": datetime.strptime(m.group(3), "%d%b%Y").date(),
                    "size": int(c.find("s3:Size", ns).text),
                })
        if tree.find("s3:IsTruncated", ns).text != "true" or not keys:
            break
        marker = keys[-1].find("s3:Key", ns).text
    return sorted(files, key=lambda f: f["number"])


def download(f: dict) -> Path:
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    path = DOWNLOAD_DIR / f["name"]
    if path.exists() and path.stat().st_size == f["size"]:
        return path
    log.info("Downloading %s (%.0f MB)", f["name"], f["size"] / 1e6)
    r = get(FILE_URL + f["name"], stream=True)
    tmp = path.with_suffix(".part")
    with open(tmp, "wb") as out:
        for chunk in r.iter_content(1 << 20):
            out.write(chunk)
    tmp.replace(path)
    return path


def load_file(conn, f: dict, path: Path) -> int:
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        mapped = [HEADER_MAP.get(normalise(h)) for h in header]
        unknown = [h for h, m in zip(header, mapped) if m is None]
        if unknown:
            raise ValueError(f"{f['name']}: unknown columns {unknown}. Add them to HEADER_MAP.")
        fmt = "new" if "duration_ms" in mapped else "old"
        positions = [mapped.index(c) if c in mapped else None for c in COLUMNS]

        rows = 0
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO raw.journey_file (file_name, period_start, period_end, size_bytes, header, header_format) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (f["name"], f["start"], f["end"], f["size"], ",".join(header), fmt),
            )
            with cur.copy(f"COPY raw.journeys (source_file, {', '.join(COLUMNS)}) FROM STDIN") as copy:
                for line in reader:
                    if not line:
                        continue
                    copy.write_row([f["name"]] + [line[p] if p is not None and p < len(line) else None
                                                  for p in positions])
                    rows += 1
            cur.execute("UPDATE raw.journey_file SET row_count = %s WHERE file_name = %s", (rows, f["name"]))
    conn.commit()   # file record and its rows commit together: all or nothing
    log.info("Loaded %s: %s rows, %s format", f["name"], f"{rows:,}", fmt)
    return rows


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--months", type=int, default=12, help="how many months back from the newest file")
    p.add_argument("--keep", action="store_true", help="keep the CSVs after loading")
    args = p.parse_args()

    try:
        files = list_files()
        newest = max(f["end"] for f in files)
        cutoff = newest - timedelta(days=round(args.months * 30.44))
        wanted = [f for f in files if f["end"] > cutoff]
        log.info("Newest file ends %s. Loading files ending after %s: %s files, %.1f GB",
                 newest, cutoff, len(wanted), sum(f["size"] for f in wanted) / 1e9)

        with psycopg.connect(warehouse_dsn()) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT file_name FROM raw.journey_file")
                done = {r[0] for r in cur.fetchall()}
            for f in wanted:
                if f["name"] in done:
                    log.info("Skipping %s: already loaded", f["name"])
                    continue
                path = download(f)
                load_file(conn, f, path)
                if not args.keep:
                    path.unlink()
        log.info("Finished")
    except Exception:
        log.exception("Journeys run failed")
        raise


if __name__ == "__main__":
    main()
