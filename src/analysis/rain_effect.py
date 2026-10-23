"""KPI from the project brief: Rain effect.
How much do hires drop in rainy hours (> 0.5 mm) compared with dry hours?

The fair comparison is like with like: the same hour of the day, in the same
month, on the same kind of day. Otherwise rain looks worse than it is, because
it rains more in winter and at night, when fewer people ride anyway.

Run from the project folder:
    python -m src.analysis.rain_effect
Writes logs/rain_effect_report.txt and prints it.
"""

from pathlib import Path

import psycopg

from src.checks.dock_gaps import DSN, as_table

REPORT = Path(__file__).resolve().parents[2] / "logs" / "rain_effect_report.txt"

ANALYSES = {
    "1. How many rainy and dry hours there are": """
        SELECT is_working_day, is_rain, count(*) AS hours, sum(hires) AS hires,
               round(avg(hires), 1) AS avg_hires_per_hour
        FROM marts.hires_weather GROUP BY 1, 2 ORDER BY 1 DESC, 2
    """,
    "2. Naive comparison: all rainy hours vs all dry hours (misleading on purpose)": """
        SELECT round(avg(hires) FILTER (WHERE NOT is_rain), 1) AS dry_avg,
               round(avg(hires) FILTER (WHERE is_rain), 1)     AS rain_avg,
               round(100 * (1 - avg(hires) FILTER (WHERE is_rain)
                              / avg(hires) FILTER (WHERE NOT is_rain)), 1) AS drop_pct
        FROM marts.hires_weather
    """,
    "3. Fair comparison: same month, same hour, same kind of day": """
        WITH cells AS (
            SELECT month, hour_of_day, is_working_day,
                   avg(hires) FILTER (WHERE NOT is_rain) AS dry_avg,
                   avg(hires) FILTER (WHERE is_rain)     AS rain_avg,
                   count(*)   FILTER (WHERE is_rain)     AS rain_hours
            FROM marts.hires_weather
            GROUP BY 1, 2, 3
        )
        SELECT is_working_day,
               count(*) AS comparisons,
               sum(rain_hours) AS rainy_hours_used,
               -- weight each comparison by how many rainy hours it has
               round(100 * (1 - sum(rain_avg * rain_hours) / sum(dry_avg * rain_hours)), 1) AS drop_pct
        FROM cells
        WHERE rain_hours >= 3 AND dry_avg > 0
        GROUP BY 1 ORDER BY 1 DESC
    """,
    "4. Rain effect by hour of the day, working days (fair comparison)": """
        WITH cells AS (
            SELECT month, hour_of_day,
                   avg(hires) FILTER (WHERE NOT is_rain) AS dry_avg,
                   avg(hires) FILTER (WHERE is_rain)     AS rain_avg,
                   count(*)   FILTER (WHERE is_rain)     AS rain_hours
            FROM marts.hires_weather
            WHERE is_working_day
            GROUP BY 1, 2
        )
        SELECT hour_of_day,
               sum(rain_hours) AS rainy_hours,
               round(sum(dry_avg * rain_hours) / sum(rain_hours)) AS dry_avg_hires,
               round(sum(rain_avg * rain_hours) / sum(rain_hours)) AS rain_avg_hires,
               round(100 * (1 - sum(rain_avg * rain_hours) / sum(dry_avg * rain_hours)), 1) AS drop_pct
        FROM cells
        WHERE rain_hours >= 1 AND dry_avg > 0
        GROUP BY 1 ORDER BY 1
    """,
    "5. Does heavier rain cut more? (working days, 07:00-19:59, vs dry same month and hour)": """
        WITH dry AS (
            SELECT month, hour_of_day, avg(hires) AS dry_avg
            FROM marts.hires_weather
            WHERE is_working_day AND precipitation_mm = 0
            GROUP BY 1, 2
        )
        SELECT CASE WHEN h.precipitation_mm = 0     THEN '0 mm (dry)'
                    WHEN h.precipitation_mm <= 0.5  THEN '0.1-0.5 mm (drizzle)'
                    WHEN h.precipitation_mm <= 2    THEN '0.6-2 mm (rain)'
                    ELSE                                 'over 2 mm (heavy)' END AS rain_band,
               count(*) AS hours,
               round(100 * (avg(h.hires / d.dry_avg) - 1), 1) AS change_vs_dry_pct
        FROM marts.hires_weather h JOIN dry d USING (month, hour_of_day)
        WHERE h.is_working_day AND h.hour_of_day BETWEEN 7 AND 19 AND d.dry_avg > 0
        GROUP BY 1 ORDER BY 1
    """,
}


def main() -> None:
    out = []
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        for title, sql in ANALYSES.items():
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
