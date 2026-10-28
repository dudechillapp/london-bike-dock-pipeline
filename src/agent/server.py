"""MCP (Model Context Protocol) server: lets an AI agent such as Claude answer
questions about London's bike docks from the warehouse.

Design rules:
- Read-only: it connects as agent_reader, which can only SELECT from marts.
- Narrow tools with clear descriptions, not free SQL: the agent picks a tool,
  the tool runs a fixed, tested query.
- Every answer says where it came from and how fresh it is (as_of / period).

Claude Desktop starts this file itself (see README). To test it by hand:
    python src/agent/server.py
"""

import os
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))                     # so Claude Desktop can start it from anywhere

import psycopg                                    # noqa: E402
from dotenv import load_dotenv                    # noqa: E402
from mcp.server.mcpserver import MCPServer        # noqa: E402  (mcp 2.x; was FastMCP in 1.x)

load_dotenv(ROOT / ".env")
mcp = MCPServer(
    "london-bike-docks",
    instructions=(
        "Answers questions about London Santander Cycles docks from a read-only warehouse. "
        "Historical hires cover June 2025 to May 2026; live dock status is only as fresh as its as_of time. "
        "Check metric_definition before quoting a KPI, use find_docks to get exact dock names, "
        "and say so when the data can't answer a question rather than guessing."
    ),
)


def _plain(value):
    """Make database values JSON-friendly."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def query(sql: str, params: tuple = ()) -> list[dict]:
    with psycopg.connect(os.environ["AGENT_DATABASE_URL"]) as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        cols = [c.name for c in cur.description]
        return [{c: _plain(v) for c, v in zip(cols, row)} for row in cur.fetchall()]


@mcp.tool()
def metric_definition(name: str = "") -> list[dict]:
    """How a KPI or term is defined in this project, e.g. 'hires', 'morning rush',
    'rain effect', 'forecast error', 'out of service spaces', 'area'.
    Leave name empty to list every definition. Use this before quoting a number."""
    if name:
        return query("SELECT name, definition, source FROM marts.metric_catalog "
                     "WHERE name ILIKE %s", (f"%{name}%",))
    return query("SELECT name, definition, source FROM marts.metric_catalog ORDER BY name")


@mcp.tool()
def find_docks(search: str) -> list[dict]:
    """Find docks whose name or area contains the search text, e.g. 'Waterloo' or
    'Hyde Park'. Returns up to 30 docks with their area. Use the exact names it returns
    in other tools. If nothing comes back, the dock doesn't exist in this data."""
    return query("""SELECT name, area, lat, lon FROM marts.dock
                    WHERE name ILIKE %s OR area ILIKE %s
                    ORDER BY name LIMIT 30""", (f"%{search}%", f"%{search}%"))


@mcp.tool()
def dock_status_now(search: str = "", only_empty: bool = False) -> dict:
    """Live bikes and free spaces at docks right now (from the newest 15-minute pull).
    search: part of a dock name or area, e.g. 'Waterloo'; empty = all docks.
    only_empty: true to list only docks with 0 bikes.
    Always report the as_of time: if it is old, the live collector may be down."""
    rows = query("""SELECT name, area, bikes, ebikes, empty_docks, total_docks,
                           out_of_service_spaces, as_of
                    FROM marts.dock_status_latest
                    WHERE (name ILIKE %s OR area ILIKE %s)
                      AND (NOT %s OR bikes = 0)
                    ORDER BY bikes, name LIMIT 50""",
                 (f"%{search}%", f"%{search}%", only_empty))
    as_of = rows[0]["as_of"] if rows else None
    for r in rows:
        r.pop("as_of")
    return {"as_of": as_of, "docks_returned": len(rows), "max_returned": 50, "docks": rows}


@mcp.tool()
def busiest_areas(month: str = "2026-05", top: int = 10) -> dict:
    """Areas with the most bike hires in the working-day morning rush (07:00-09:59
    London time), averaged per working day, for one month.
    month: 'YYYY-MM', between 2025-06 and 2026-05 (the journey data available)."""
    rows = query("""SELECT area, round(avg(hires)) AS avg_morning_rush_hires, count(*) AS working_days
                    FROM marts.area_morning_rush
                    WHERE to_char(day, 'YYYY-MM') = %s
                    GROUP BY area ORDER BY 2 DESC LIMIT %s""", (month, min(top, 50)))
    return {"month": month, "measure": "average valid hires per working day, 07:00-09:59",
            "areas": rows}


@mcp.tool()
def dock_usual_hires(dock_name: str) -> dict:
    """A dock's usual hires per hour of the day, on working days and other days,
    over June 2025 to May 2026. Use find_docks first to get the exact dock name."""
    rows = query("""SELECT h.hour_of_day,
                           round(avg(h.hires) FILTER (WHERE h.is_working_day), 1)     AS working_day,
                           round(avg(h.hires) FILTER (WHERE NOT h.is_working_day), 1) AS weekend_or_holiday
                    FROM marts.dock_hourly_hires h
                    JOIN marts.dock d USING (dock_id)
                    WHERE d.name = %s
                    GROUP BY 1 ORDER BY 1""", (dock_name,))
    if not rows:
        return {"error": f"No dock called '{dock_name}'. Use find_docks to get the exact name."}
    return {"dock": dock_name, "period": "June 2025 to May 2026",
            "measure": "average valid hires per hour, London time", "by_hour": rows}


@mcp.tool()
def rain_effect() -> dict:
    """How much rain cuts bike hires, by how heavy the rain is (working days,
    07:00-19:59, compared with dry hours in the same month at the same hour)."""
    rows = query("""
        WITH dry AS (
            SELECT month, hour_of_day, avg(hires) AS dry_avg
            FROM marts.hires_weather
            WHERE is_working_day AND precipitation_mm = 0
            GROUP BY 1, 2)
        SELECT CASE WHEN h.precipitation_mm <= 0.5 THEN '0.1-0.5 mm (drizzle)'
                    WHEN h.precipitation_mm <= 2   THEN '0.6-2 mm (rain)'
                    ELSE 'over 2 mm (heavy)' END AS rain_band,
               count(*) AS hours,
               round(100 * (avg(h.hires / d.dry_avg) - 1), 1) AS change_vs_dry_pct
        FROM marts.hires_weather h JOIN dry d USING (month, hour_of_day)
        WHERE h.is_working_day AND h.hour_of_day BETWEEN 7 AND 19
          AND h.precipitation_mm > 0 AND d.dry_avg > 0
        GROUP BY 1 ORDER BY 1""")
    return {"period": "June 2025 to May 2026", "bands": rows,
            "note": "Correlation, not proof of cause. Few heavy-rain hours, so treat that band as a direction."}


@mcp.tool()
def forecast_accuracy(area: str = "") -> dict:
    """How accurate the day-ahead hires forecast was in May 2026 (a month the model never
    saw), for the morning rush per area per day, against 'same days last week'.
    area: e.g. 'Waterloo'; empty = all areas together."""
    rows = query("""
        WITH r AS (
            SELECT d.area, (f.hour AT TIME ZONE 'Europe/London')::date AS day,
                   sum(f.actual) AS actual, sum(f.predicted_day_ahead) AS forecast,
                   sum(f.baseline_last_week) AS last_week
            FROM marts.hire_forecast f
            JOIN marts.dock d USING (dock_id)
            JOIN marts.hires_weather w ON w.hour = f.hour
            WHERE w.is_working_day AND w.hour_of_day BETWEEN 7 AND 9
              AND d.area ILIKE %s
            GROUP BY 1, 2)
        SELECT count(*) AS area_days,
               round(avg(actual), 1) AS avg_actual_hires,
               round(avg(abs(actual - forecast))::numeric, 1) AS model_avg_error,
               round(avg(abs(actual - last_week))::numeric, 1) AS last_week_avg_error
        FROM r""", (f"%{area}%",))
    return {"test_month": "May 2026", "area": area or "all areas",
            "measure": "morning rush hires per area per working day", "result": rows[0]}


if __name__ == "__main__":
    mcp.run()
