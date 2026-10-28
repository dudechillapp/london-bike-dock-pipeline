"""Is the forecast more useful at the level a van team plans?

Reads the May 2026 predictions saved by forecast_hires.py (marts.hire_forecast) and:
1. estimates the best possible error for single dock-hours, if hires were pure chance;
2. totals the working-day morning rush (07:00-09:59 London) per dock per day and
   per area per day, and compares the day-ahead model with the baselines.

Run from the project folder (after forecast_hires.py):
    python -m src.analysis.forecast_windows
Writes logs/forecast_windows_report.txt and prints it.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import psycopg
from scipy.stats import poisson
from sklearn.metrics import mean_absolute_error

from src.checks.dock_gaps import DSN

REPORT = Path(__file__).resolve().parents[2] / "logs" / "forecast_windows_report.txt"

SQL = """
SELECT f.dock_id, d.name,
       (f.hour AT TIME ZONE 'Europe/London')::date AS day,
       extract(hour FROM f.hour AT TIME ZONE 'Europe/London')::int AS hour_of_day,
       w.is_working_day,
       f.actual, f.predicted, f.predicted_day_ahead, f.baseline_last_week, f.baseline_usual
FROM marts.hire_forecast f
JOIN staging.dock d USING (dock_id)
JOIN marts.hires_weather w ON w.hour = f.hour
"""


def poisson_floor(rate: np.ndarray, kmax: int = 80) -> float:
    """Best possible MAE if hires were pure chance (Poisson) around these rates:
    the expected distance from the best single guess, the median."""
    rate = np.clip(rate, 1e-6, None).astype("float64")
    k = np.arange(kmax + 1)
    total = 0.0
    for start in range(0, len(rate), 50_000):          # in chunks, to keep memory low
        r = rate[start:start + 50_000]
        pmf = poisson.pmf(k[None, :], r[:, None])
        total += (pmf * np.abs(k[None, :] - poisson.median(r)[:, None])).sum()
    return total / len(rate)


def compare(g: pd.DataFrame) -> pd.DataFrame:
    rows = [(name, mean_absolute_error(g.actual, g[col])) for name, col in [
        ("Same days last week", "baseline_last_week"),
        ("Usual level for these hours", "baseline_usual"),
        ("Model (day ahead)", "predicted_day_ahead"),
    ]]
    t = pd.DataFrame(rows, columns=["forecast", "mae"])
    usual = t.loc[t.forecast == "Usual level for these hours", "mae"].iloc[0]
    t["vs_usual_level"] = (1 - t.mae / usual).map(lambda v: f"{v:+.1%}")
    t["error_as_pct_of_hires"] = (t.mae / g.actual.mean()).map(lambda v: f"{v:.0%}")
    t["mae"] = t.mae.round(2)
    return t


def main() -> None:
    lines = []
    say = lambda s="": (print(s), lines.append(s))

    with psycopg.connect(DSN) as conn:
        df = pd.read_sql(SQL, conn)
    df["area"] = df.name.str.split(",").str[-1].str.strip()
    say(f"Loaded {len(df):,} May 2026 dock-hour predictions for {df.dock_id.nunique()} docks "
        f"in {df.area.nunique()} areas (area = the part of the dock name after the last comma)")

    rush = df[df.is_working_day & df.hour_of_day.between(7, 9)]

    say("\n## 1. Single dock-hours: how close to the best possible?")
    for label, part in [("All hours", df), ("Morning rush", rush)]:
        floor = poisson_floor(part.predicted.to_numpy())
        model = mean_absolute_error(part.actual, part.predicted)
        say(f"{label:<13} best possible about {floor:.3f}, model {model:.3f}, "
            f"average hires {part.actual.mean():.2f}")

    sums = ["actual", "predicted_day_ahead", "baseline_last_week", "baseline_usual"]
    for level, keys in [("dock", ["dock_id", "day"]), ("area", ["area", "day"])]:
        g = rush.groupby(keys)[sums].sum()
        say(f"\n## 2{'a' if level == 'dock' else 'b'}. Morning rush (07:00-09:59) total per {level} "
            f"per working day: {len(g):,} {level}-days, average {g.actual.mean():.1f} hires")
        say(compare(g).to_string(index=False))

    say("\n## 3. Busiest areas in the morning rush (average per working day in May)")
    a = rush.groupby(["area", "day"])[sums].sum().groupby("area").mean()
    a["abs_error_model"] = (rush.groupby(["area", "day"])[sums].sum()
                            .eval("abs(actual - predicted_day_ahead)").groupby("area").mean())
    top = a.sort_values("actual", ascending=False).head(10)
    say(top[["actual", "predicted_day_ahead", "abs_error_model"]].round(1).to_string())

    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Saved to {REPORT}")


if __name__ == "__main__":
    main()
