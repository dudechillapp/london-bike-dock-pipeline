"""Forecast hires per dock for the next hour, and test it against simple baselines.

Train: 8 June 2025 to 30 April 2026 (the first week is skipped: no "last week" lag yet).
Test:  May 2026, which the model never sees while training.

Scored with MAE (Mean Absolute Error): the average number of hires the forecast is off by.

Run from the project folder (allow a few minutes, it reads about 7 million rows):
    python -m src.analysis.forecast_hires
Writes logs/forecast_report.txt and the May predictions to marts.hire_forecast.
"""

import io
import time
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error

from src.checks.dock_gaps import DSN

REPORT = Path(__file__).resolve().parents[2] / "logs" / "forecast_report.txt"
TEST_START = pd.Timestamp("2026-05-01")          # London time
FEATURES = ["hour_of_day", "day_of_week", "is_working_day", "month_num",
            "temperature_c", "precipitation_mm", "wind_speed_kmh",
            "hires_lag_1h", "hires_lag_24h", "hires_lag_168h", "dock_hour_mean"]


def load() -> pd.DataFrame:
    sql = """COPY (
        SELECT dock_id, hour, hour_london, hour_of_day, day_of_week,
               extract(month FROM month)::int AS month_num, is_working_day::int AS is_working_day,
               temperature_c, precipitation_mm, wind_speed_kmh,
               hires, hires_lag_1h, hires_lag_24h, hires_lag_168h
        FROM marts.dock_hourly_hires
        WHERE hires_lag_168h IS NOT NULL
    ) TO STDOUT WITH CSV HEADER"""
    buf = io.BytesIO()
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        with cur.copy(sql) as copy:
            for chunk in copy:
                buf.write(chunk)
    buf.seek(0)
    df = pd.read_csv(buf, parse_dates=["hour_london"])
    for c in ["hour_of_day", "day_of_week", "month_num", "is_working_day",
              "hires", "hires_lag_1h", "hires_lag_24h", "hires_lag_168h"]:
        df[c] = df[c].astype("int16")
    for c in ["temperature_c", "precipitation_mm", "wind_speed_kmh"]:
        df[c] = df[c].astype("float32")
    return df


def mae_table(name_to_pred: dict, actual: pd.Series) -> pd.DataFrame:
    rows = [(n, mean_absolute_error(actual, p)) for n, p in name_to_pred.items()]
    out = pd.DataFrame(rows, columns=["forecast", "mae"])
    best_baseline = out[out.forecast != "Model"].mae.min()
    out["vs_best_baseline"] = (1 - out.mae / best_baseline).map(lambda v: f"{v:+.1%}")
    out["mae"] = out.mae.round(3)
    return out


def main() -> None:
    t0 = time.time()
    lines = []
    say = lambda s="": (print(s), lines.append(s))

    df = load()
    say(f"Loaded {len(df):,} dock-hours for {df.dock_id.nunique()} docks in {time.time() - t0:.0f}s")

    train = df[df.hour_london < TEST_START].copy()
    test = df[df.hour_london >= TEST_START].copy()

    # A dock's normal level for this hour and kind of day, learned from training data only
    means = (train.groupby(["dock_id", "hour_of_day", "is_working_day"]).hires.mean()
             .rename("dock_hour_mean").reset_index())
    train = train.merge(means, on=["dock_id", "hour_of_day", "is_working_day"], how="left")
    test = test.merge(means, on=["dock_id", "hour_of_day", "is_working_day"], how="left")
    test["dock_hour_mean"] = test.dock_hour_mean.fillna(0)
    say(f"Train: {len(train):,} rows, to {train.hour_london.max():%d %b %Y}. "
        f"Test: {len(test):,} rows, {test.hour_london.min():%d %b} to {test.hour_london.max():%d %b %Y}")

    model = HistGradientBoostingRegressor(loss="poisson", max_iter=300, learning_rate=0.1,
                                          max_leaf_nodes=63, random_state=42)
    model.fit(train[FEATURES], train.hires)
    test["predicted"] = model.predict(test[FEATURES]).astype("float32")
    say(f"Model trained in {time.time() - t0:.0f}s total")

    preds = {
        "Same hour last week": test.hires_lag_168h,
        "Same hour yesterday": test.hires_lag_24h,
        "Previous hour": test.hires_lag_1h,
        "Dock's usual level for this hour": test.dock_hour_mean,
        "Model": test.predicted,
    }

    say("\n## 1. All dock-hours in May 2026")
    say(mae_table(preds, test.hires).to_string(index=False))

    rush = (test.is_working_day == 1) & test.hour_of_day.between(7, 9)
    say("\n## 2. Working-day morning rush (07:00-09:59 London), the hours the brief cares about")
    say(mae_table({k: v[rush] for k, v in preds.items()}, test.hires[rush]).to_string(index=False))

    busiest = train.groupby("dock_id").hires.sum().nlargest(20).index
    big = test.dock_id.isin(busiest)
    say("\n## 3. The 20 busiest docks")
    say(mae_table({k: v[big] for k, v in preds.items()}, test.hires[big]).to_string(index=False))

    say("\n## 4. Context")
    say(f"Average hires per dock-hour in May: {test.hires.mean():.2f}; "
        f"in the morning rush: {test.hires[rush].mean():.2f}; at the 20 busiest docks: {test.hires[big].mean():.2f}")
    say(f"Dock-hours with 0 hires: {(test.hires == 0).mean():.0%}")

    # What the model leans on (permutation importance on a sample, to keep it quick)
    from sklearn.inspection import permutation_importance
    sample = test.sample(min(200_000, len(test)), random_state=42)
    imp = permutation_importance(model, sample[FEATURES], sample.hires, n_repeats=3,
                                 random_state=42, scoring="neg_mean_absolute_error")
    order = np.argsort(-imp.importances_mean)
    say("\n## 5. What the model relies on (increase in MAE when a feature is shuffled)")
    for i in order:
        say(f"{FEATURES[i]:<18} {imp.importances_mean[i]:.4f}")

    # Save May predictions for the dashboard and the agent
    out = test[["dock_id", "hour", "hires", "predicted", "hires_lag_168h"]].rename(
        columns={"hires": "actual", "hires_lag_168h": "baseline_last_week"})
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        cur.execute("""CREATE TABLE IF NOT EXISTS marts.hire_forecast (
                           dock_id text, hour timestamptz, actual int, predicted real,
                           baseline_last_week int, PRIMARY KEY (dock_id, hour))""")
        cur.execute("COMMENT ON TABLE marts.hire_forecast IS 'Test-period (May 2026) hourly hire "
                    "forecasts per dock from src/analysis/forecast_hires.py, next to the actual hires.'")
        cur.execute("TRUNCATE marts.hire_forecast")
        with cur.copy("COPY marts.hire_forecast FROM STDIN") as copy:
            for r in out.itertuples(index=False):   # plain Python types for psycopg
                copy.write_row((r.dock_id, r.hour, int(r.actual), float(r.predicted),
                                int(r.baseline_last_week)))
        conn.commit()
    say(f"\nSaved {len(out):,} predictions to marts.hire_forecast in {time.time() - t0:.0f}s total")

    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Saved to {REPORT}")


if __name__ == "__main__":
    main()
