"""Investigate data issue #1: why bikes + empty docks < total docks at most docks.

Check 1: does NbBikes equal NbStandardBikes + NbEBikes?
Check 2: do the same docks have gaps in every pull (fixed, like broken hardware)
         or do the gaps move around between pulls?

Run from the project folder:
    python -m src.checks.dock_gaps
Writes the results to logs/dock_gaps_report.txt and prints them.
"""

import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

load_dotenv()
DSN = os.environ["WAREHOUSE_URL"].replace("postgresql+psycopg://", "postgresql://")
REPORT = Path(__file__).resolve().parents[2] / "logs" / "dock_gaps_report.txt"

# Every property of every dock in the newest raw snapshot, one row each
LATEST_PROPS = """
WITH latest AS (
    SELECT payload FROM raw.bikepoint_snapshot ORDER BY pulled_at DESC LIMIT 1
), props AS (
    SELECT d->>'id' AS dock_id, p->>'key' AS key, p->>'value' AS value
    FROM latest, jsonb_array_elements(payload) d,
         jsonb_array_elements(d->'additionalProperties') p
)
"""

CHECKS = {
    "0a. Pulls available": """
        SELECT (SELECT count(*) FROM raw.bikepoint_snapshot)        AS raw_pulls,
               (SELECT count(DISTINCT pulled_at) FROM staging.dock_status) AS staged_pulls,
               (SELECT min(pulled_at) FROM staging.dock_status)     AS first_pull,
               (SELECT max(pulled_at) FROM staging.dock_status)     AS last_pull
    """,
    "0b. Every property key TfL sends (newest pull)": LATEST_PROPS + """
        SELECT key, count(*) AS docks,
               min(value) AS example_min, max(value) AS example_max
        FROM props GROUP BY key ORDER BY key
    """,
    "1a. Does NbBikes = NbStandardBikes + NbEBikes? (newest pull)": LATEST_PROPS + """
        , wide AS (
            SELECT dock_id,
                   max(CASE WHEN key='NbBikes'         THEN NULLIF(value,'')::int END) AS bikes,
                   max(CASE WHEN key='NbStandardBikes' THEN NULLIF(value,'')::int END) AS standard,
                   max(CASE WHEN key='NbEBikes'        THEN NULLIF(value,'')::int END) AS ebikes
            FROM props GROUP BY dock_id
        )
        SELECT count(*)                                              AS docks,
               count(*) FILTER (WHERE bikes =  standard + ebikes)    AS equal,
               count(*) FILTER (WHERE bikes <> standard + ebikes)    AS not_equal,
               count(*) FILTER (WHERE standard IS NULL)              AS standard_missing,
               sum(standard + ebikes - bikes)                        AS total_difference
        FROM wide
    """,
    "1b. Is the gap explained by locked or not-installed docks? (newest pull)": LATEST_PROPS + """
        , wide AS (
            SELECT dock_id,
                   max(CASE WHEN key='NbBikes'      THEN NULLIF(value,'')::int END) AS bikes,
                   max(CASE WHEN key='NbEmptyDocks' THEN NULLIF(value,'')::int END) AS empty_docks,
                   max(CASE WHEN key='NbDocks'      THEN NULLIF(value,'')::int END) AS total_docks,
                   max(CASE WHEN key='Locked'       THEN value END)                AS locked,
                   max(CASE WHEN key='Installed'    THEN value END)                AS installed,
                   max(CASE WHEN key='Temporary'    THEN value END)                AS temporary
            FROM props GROUP BY dock_id
        )
        SELECT locked, installed, temporary,
               count(*)                                                AS docks,
               count(*) FILTER (WHERE bikes + empty_docks < total_docks) AS docks_with_gap,
               sum(total_docks - bikes - empty_docks)                  AS gap_spaces
        FROM wide GROUP BY 1, 2, 3 ORDER BY docks DESC
    """,
    "1c. How big are the gaps? (newest pull, docks per gap size)": """
        SELECT total_docks - bikes - empty_docks AS gap, count(*) AS docks
        FROM staging.dock_status
        WHERE pulled_at = (SELECT max(pulled_at) FROM staging.dock_status)
        GROUP BY 1 ORDER BY 1
    """,
    "2a. Do the same docks have gaps in every pull?": """
        WITH per_dock AS (
            SELECT dock_id,
                   count(*)                                                AS pulls,
                   count(*) FILTER (WHERE bikes + empty_docks < total_docks) AS pulls_with_gap,
                   min(total_docks - bikes - empty_docks)                  AS min_gap,
                   max(total_docks - bikes - empty_docks)                  AS max_gap
            FROM staging.dock_status GROUP BY dock_id
        )
        SELECT CASE WHEN pulls_with_gap = 0     THEN '1. never a gap'
                    WHEN pulls_with_gap = pulls THEN '2. gap in every pull'
                    ELSE                             '3. gap in some pulls' END AS pattern,
               count(*)                                        AS docks,
               count(*) FILTER (WHERE min_gap = max_gap)       AS gap_size_never_changes,
               round(avg(max_gap - min_gap), 2)                AS avg_change_in_gap
        FROM per_dock GROUP BY 1 ORDER BY 1
    """,
    "2b. Does the gap move with bikes being taken or returned? (change between pulls)": """
        WITH steps AS (
            SELECT dock_id,
                   bikes - LAG(bikes) OVER w                                   AS bikes_change,
                   (total_docks - bikes - empty_docks)
                     - LAG(total_docks - bikes - empty_docks) OVER w          AS gap_change
            FROM staging.dock_status
            WINDOW w AS (PARTITION BY dock_id ORDER BY pulled_at)
        )
        SELECT count(*)                                              AS dock_steps,
               count(*) FILTER (WHERE gap_change <> 0)               AS gap_changed,
               count(*) FILTER (WHERE bikes_change <> 0)             AS bikes_changed,
               count(*) FILTER (WHERE gap_change <> 0 AND bikes_change <> 0) AS both_changed,
               round(corr(gap_change, bikes_change)::numeric, 3)    AS correlation
        FROM steps WHERE gap_change IS NOT NULL
    """,
    "2c. Ten docks with the biggest gaps (every pull)": """
        SELECT d.name, s.pulled_at::time(0) AS utc_time, s.bikes, s.empty_docks, s.total_docks,
               s.total_docks - s.bikes - s.empty_docks AS gap
        FROM staging.dock_status s JOIN staging.dock d USING (dock_id)
        WHERE s.dock_id IN (
            SELECT dock_id FROM staging.dock_status
            WHERE pulled_at = (SELECT max(pulled_at) FROM staging.dock_status)
            ORDER BY total_docks - bikes - empty_docks DESC LIMIT 10)
        ORDER BY d.name, s.pulled_at
    """,
}


def as_table(cur) -> str:
    cols = [c.name for c in cur.description]
    rows = [[("" if v is None else str(v)) for v in r] for r in cur.fetchall()]
    widths = [max(len(c), *(len(r[i]) for r in rows)) if rows else len(c) for i, c in enumerate(cols)]
    line = lambda vals: " | ".join(v.ljust(w) for v, w in zip(vals, widths))
    return "\n".join([line(cols), "-+-".join("-" * w for w in widths)] + [line(r) for r in rows])


def main() -> None:
    out = []
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        for title, sql in CHECKS.items():
            try:
                cur.execute(sql)
                out.append(f"## {title}\n{as_table(cur)}\n")
            except Exception as e:  # keep going so one bad check doesn't hide the rest
                conn.rollback()
                out.append(f"## {title}\nERROR: {e}\n")
    text = "\n".join(out)
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text(text, encoding="utf-8")
    print(text)
    print(f"Saved to {REPORT}")


if __name__ == "__main__":
    main()
