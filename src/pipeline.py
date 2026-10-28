"""Small helpers shared by the Airflow DAGs.

- run_sql_file: run one of the numbered files in sql/
- run_tests: run every data quality test in tests/ and fail if any finds a problem
- alert: called by Airflow when a task fails
"""

import logging
import os
from pathlib import Path

import psycopg
import requests

ROOT = Path(__file__).resolve().parents[1]
log = logging.getLogger("pipeline")


def dsn() -> str:
    return os.environ["WAREHOUSE_URL"].replace("postgresql+psycopg://", "postgresql://")


def run_sql_file(name: str) -> None:
    """Run sql/<name>. Autocommit, because the files manage their own BEGIN/COMMIT."""
    sql = (ROOT / "sql" / name).read_text(encoding="utf-8")
    with psycopg.connect(dsn(), autocommit=True) as conn:
        conn.execute(sql)
    log.info("Ran sql/%s", name)


def run_tests(pattern: str = "*.sql") -> None:
    """Each test in tests/ is a query that returns the rows that break a rule.
    0 rows = pass. Any rows = fail, and the first few are logged."""
    failures = []
    with psycopg.connect(dsn()) as conn, conn.cursor() as cur:
        for path in sorted((ROOT / "tests").glob(pattern)):
            cur.execute(path.read_text(encoding="utf-8"))
            rows = cur.fetchmany(5)
            if rows:
                failures.append(path.name)
                log.error("FAIL %s: %s", path.name, rows)
            else:
                log.info("pass %s", path.name)
    if failures:
        raise ValueError(f"{len(failures)} data quality test(s) failed: {', '.join(failures)}")


def alert(context: dict) -> None:
    """Airflow on_failure_callback: log the failure, and push it to a phone if
    ALERT_NTFY_TOPIC is set (free ntfy app)."""
    ti = context["task_instance"]
    message = (f"{ti.dag_id}.{ti.task_id} failed (try {ti.try_number}) "
               f"for {context.get('logical_date')}: {context.get('exception')}")
    (ROOT / "logs").mkdir(exist_ok=True)
    with open(ROOT / "logs" / "alerts.log", "a", encoding="utf-8") as f:
        f.write(message + "\n")
    topic = os.getenv("ALERT_NTFY_TOPIC")
    if topic:
        try:
            requests.post(f"https://ntfy.sh/{topic}", data=message.encode("utf-8"),
                          headers={"Title": "Bike pipeline failed", "Tags": "warning"}, timeout=10)
        except requests.RequestException as e:
            log.warning("Could not send ntfy alert: %s", e)
