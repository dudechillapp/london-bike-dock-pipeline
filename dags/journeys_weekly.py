"""Every Monday at 07:00 London time: check TfL for new journey files and load them.

TfL publishes journey files months late and at irregular times, so a weekly check
is enough. Files already loaded are skipped, so most weeks this does almost nothing.

extract journeys -> stage journeys -> refresh marts -> test
"""

from datetime import timedelta

import pendulum
from airflow.decorators import dag, task

from src.pipeline import alert

default_args = {
    "retries": 2,
    "retry_delay": timedelta(minutes=10),
    "on_failure_callback": alert,
}


@dag(
    schedule="0 7 * * 1",
    start_date=pendulum.datetime(2026, 10, 26, tz="Europe/London"),
    catchup=False,
    max_active_runs=1,
    default_args=default_args,
    tags=["bikes", "weekly"],
    doc_md=__doc__,
)
def journeys_weekly():

    @task
    def extract_journeys():
        import sys
        from src.extract.journeys import main
        sys.argv = ["journeys"]
        main()

    @task
    def stage_journeys():
        from src.pipeline import run_sql_file
        run_sql_file("030_stage_journeys.sql")

    @task
    def refresh_marts():
        from src.pipeline import run_sql_file
        run_sql_file("060_refresh_marts.sql")

    @task
    def test():
        from src.pipeline import run_tests
        run_tests("journeys_*.sql")

    extract_journeys() >> stage_journeys() >> refresh_marts() >> test()


journeys_weekly()
