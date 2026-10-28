"""Every morning at 06:00 London time: refresh the weather and test it.

weather -> stage weather -> weather tests

The marts only change when new journey files arrive, so journeys_weekly refreshes them.
"""

from datetime import timedelta

import pendulum
from airflow.decorators import dag, task

from src.pipeline import alert

default_args = {
    "retries": 3,
    "retry_delay": timedelta(minutes=5),
    "on_failure_callback": alert,
}


@dag(
    schedule="0 6 * * *",
    start_date=pendulum.datetime(2026, 10, 28, tz="Europe/London"),
    catchup=False,
    max_active_runs=1,
    default_args=default_args,
    tags=["bikes", "daily"],
    doc_md=__doc__,
)
def daily_build():

    @task
    def extract_weather():
        import sys
        from src.extract.weather import main
        sys.argv = ["weather"]          # no extra options: just fetch what's new
        main()

    @task
    def stage_weather():
        from src.pipeline import run_sql_file
        run_sql_file("020_stage_weather.sql")

    @task
    def test():
        from src.pipeline import run_tests
        run_tests("weather_*.sql")

    extract_weather() >> stage_weather() >> test()


daily_build()
