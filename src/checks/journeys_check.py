"""Quality checks on the journey data after staging.

Run from the project folder:
    python -m src.checks.journeys_check
Writes logs/journeys_check_report.txt and prints it.
"""

from pathlib import Path

from src.checks.dock_gaps import DSN, as_table
import psycopg

REPORT = Path(__file__).resolve().parents[2] / "logs" / "journeys_check_report.txt"

CHECKS = {
    "1. Raw vs staged rows per file (rows lost in staging)": """
        SELECT r.file_name, r.row_count AS raw_rows, s.rows_staged,
               r.row_count - s.rows_staged AS dropped
        FROM raw.journey_file r LEFT JOIN staging.journey_file_staged s USING (file_name)
        ORDER BY r.period_start
    """,
    "2. Samples of raw values (to confirm formats)": """
        SELECT rental_id, start_time, end_time, start_station_id, start_station_name,
               duration_text, duration_ms
        FROM raw.journeys LIMIT 5
    """,
    "3. Why raw rows were dropped": """
        SELECT CASE WHEN rental_id IS NULL OR rental_id !~ '^\\d+$' THEN 'bad rental id'
                    WHEN start_time IS NULL OR start_time !~ '^(\\d{4}-\\d{2}-\\d{2}|\\d{2}/\\d{2}/\\d{4}) \\d{2}:\\d{2}'
                         THEN 'bad start time'
                    ELSE 'ok (or duplicate rental id)' END AS reason,
               count(*) AS raw_rows
        FROM raw.journeys GROUP BY 1 ORDER BY 2 DESC
    """,
    "4. Duplicate rental ids in raw": """
        SELECT count(*) AS duplicated_ids, coalesce(sum(n - 1), 0) AS extra_rows
        FROM (SELECT rental_id, count(*) AS n FROM raw.journeys GROUP BY 1 HAVING count(*) > 1) d
    """,
    "5. Station id matching: how journeys link to docks": """
        WITH ids AS (
            SELECT start_station_id AS station_id, count(*) AS journeys
            FROM staging.journeys GROUP BY 1
        )
        SELECT count(*)                                                        AS station_ids,
               sum(journeys)                                                   AS journeys,
               count(*) FILTER (WHERE EXISTS (SELECT 1 FROM staging.dock d
                    WHERE ltrim(d.terminal_name,'0') = ltrim(ids.station_id,'0')))  AS ids_matching_terminal,
               count(*) FILTER (WHERE EXISTS (SELECT 1 FROM staging.dock d
                    WHERE ltrim(replace(d.dock_id,'BikePoints_',''),'0') = ltrim(ids.station_id,'0'))) AS ids_matching_bikepoint_no,
               round(100.0 * (SELECT count(*) FROM staging.journeys WHERE start_dock_id IS NOT NULL)
                     / NULLIF(sum(journeys), 0), 2)                            AS pct_journeys_matched
        FROM ids
    """,
    "6. Name check: does the matched dock have the same name as the journey file?": """
        SELECT count(*) AS checked,
               count(*) FILTER (WHERE lower(regexp_replace(j.start_station_name, '\\s+,', ',', 'g'))
                                    = lower(regexp_replace(d.name, '\\s+,', ',', 'g'))) AS same_name,
               count(*) FILTER (WHERE lower(regexp_replace(j.start_station_name, '\\s+,', ',', 'g'))
                                   <> lower(regexp_replace(d.name, '\\s+,', ',', 'g'))) AS different_name
        FROM (SELECT DISTINCT start_station_id, start_station_name, start_dock_id
              FROM staging.journeys WHERE start_dock_id IS NOT NULL) j
        JOIN staging.dock d ON d.dock_id = j.start_dock_id
    """,
    "7. Examples of different names (top 10 by journeys)": """
        SELECT j.start_station_id, j.start_station_name AS journey_file_name, d.name AS live_api_name,
               count(*) AS journeys
        FROM staging.journeys j JOIN staging.dock d ON d.dock_id = j.start_dock_id
        WHERE lower(regexp_replace(j.start_station_name, '\\s+,', ',', 'g'))
           <> lower(regexp_replace(d.name, '\\s+,', ',', 'g'))
        GROUP BY 1, 2, 3 ORDER BY 4 DESC LIMIT 10
    """,
    "8. Stations in journeys with no live dock (top 10 by journeys)": """
        SELECT start_station_id, start_station_name, count(*) AS journeys,
               min(start_time)::date AS first, max(start_time)::date AS last
        FROM staging.journeys WHERE start_dock_id IS NULL
        GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 10
    """,
    "9. Durations": """
        SELECT count(*) FILTER (WHERE duration_s IS NULL)           AS missing,
               count(*) FILTER (WHERE duration_s < 60)              AS under_1_min,
               count(*) FILTER (WHERE duration_s > 86400)           AS over_1_day,
               round(percentile_cont(0.5) WITHIN GROUP (ORDER BY duration_s)::numeric / 60, 1) AS median_minutes,
               count(*) FILTER (WHERE end_time < start_time)        AS ends_before_start
        FROM staging.journeys
    """,
    "10. Hires outside the period their file says it covers": """
        SELECT f.file_name, f.period_start, f.period_end,
               count(*) FILTER (WHERE (j.start_time AT TIME ZONE 'Europe/London')::date < f.period_start) AS before_period,
               count(*) FILTER (WHERE (j.start_time AT TIME ZONE 'Europe/London')::date > f.period_end)   AS after_period
        FROM staging.journeys j JOIN raw.journey_file f ON f.file_name = j.source_file
        GROUP BY 1, 2, 3
        HAVING count(*) FILTER (WHERE (j.start_time AT TIME ZONE 'Europe/London')::date
                                NOT BETWEEN f.period_start AND f.period_end) > 0
        ORDER BY 2
    """,
    "12. How journeys were matched to docks (start and end)": """
        SELECT 'start' AS side, start_match AS match, count(*) AS journeys,
               round(100.0 * count(*) / sum(count(*)) OVER (), 2) AS pct
        FROM staging.journeys GROUP BY 1, 2
        UNION ALL
        SELECT 'end', end_match, count(*), round(100.0 * count(*) / sum(count(*)) OVER (), 2)
        FROM staging.journeys GROUP BY 1, 2
        ORDER BY 1, 3 DESC
    """,
    "13. Valid trips (1 minute to 1 day, ends after it starts)": """
        SELECT is_valid_trip, count(*) AS journeys,
               round(percentile_cont(0.5) WITHIN GROUP (ORDER BY duration_s)::numeric / 60, 1) AS median_minutes,
               round(avg(duration_s) / 60, 1) AS avg_minutes
        FROM staging.journeys GROUP BY 1 ORDER BY 1
    """,
    "11. Hires per month (UTC)": """
        SELECT date_trunc('month', start_time)::date AS month, count(*) AS hires,
               round(avg(duration_s) / 60, 1) AS avg_minutes
        FROM staging.journeys GROUP BY 1 ORDER BY 1
    """,
}


def main() -> None:
    out = []
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        for title, sql in CHECKS.items():
            try:
                cur.execute(sql)
                out.append(f"## {title}\n{as_table(cur)}\n")
            except Exception as e:
                conn.rollback()
                out.append(f"## {title}\nERROR: {e}\n")
    text = "\n".join(out)
    REPORT.write_text(text, encoding="utf-8")
    print(text)
    print(f"Saved to {REPORT}")


if __name__ == "__main__":
    main()
