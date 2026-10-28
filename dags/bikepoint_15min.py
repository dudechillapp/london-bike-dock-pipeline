"""Every 15 minutes: pull live dock status, stage it, and test it.

extract -> stage -> test
"""

from datetime import timedelta

import pendulum
from airflow.decorators import dag, task

from src.pipeline import alert

default_args = {
    "retries": 2,
    "retry_delay": timedelta(minutes=1),
    "on_failure_callback": alert,      # runs only when the last retry has failed too
}


@dag(
    schedule="*/15 * * * *",
    start_date=pendulum.datetime(2026, 10, 28, tz="Europe/London"),
    catchup=False,                     # the live API only knows "now": nothing to backfill
    max_active_runs=1,
    dagrun_timeout=timedelta(minutes=10),
    default_args=default_args,
    tags=["bikes", "live"],
    doc_md=__doc__,
)
def bikepoint_15min():

    @task
    def extract():
        from src.extract.bikepoints import main
        main()

    @task
    def stage():
        from src.pipeline import run_sql_file
        run_sql_file("010_stage_dock_status.sql")

    @task
    def test():
        from src.pipeline import run_tests
        run_tests("dock_*.sql")

    extract() >> stage() >> test()


bikepoint_15min()
