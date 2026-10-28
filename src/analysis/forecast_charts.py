"""Charts for Finding 2 in docs/findings.md, from marts.hire_forecast.

Run from the project folder (after forecast_hires.py):
    python -m src.analysis.forecast_charts
Saves docs/img/forecast_week.png and docs/img/forecast_levels.png.
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import psycopg

from src.analysis.forecast_windows import SQL
from src.checks.dock_gaps import DSN

OUT = Path(__file__).resolve().parents[2] / "docs" / "img"
SURF, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
BLUE, ORANGE, BAR = "#2a78d6", "#eb6834", "#c9c8c2"
plt.rcParams.update({"font.size": 11, "axes.edgecolor": GRID, "text.color": INK,
                     "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2})


def tidy(ax, grid_axis: str) -> None:
    ax.set_facecolor(SURF)
    ax.grid(axis=grid_axis, color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    for side in ["top", "right", "left"]:
        ax.spines[side].set_visible(False)


def week_chart(df: pd.DataFrame) -> None:
    """One busy dock, one working week: actual hires against the forecasts."""
    busiest = df.groupby(["dock_id", "name"]).actual.sum().idxmax()
    days = pd.date_range("2026-05-11", "2026-05-15").date              # Mon to Fri
    d = df[(df.dock_id == busiest[0]) & df.day.isin(days)].sort_values(["day", "hour_of_day"])
    d = d[d.hour_of_day.between(6, 21)]
    x = range(len(d))
    fig, ax = plt.subplots(figsize=(9, 4.6), dpi=150)
    fig.patch.set_facecolor(SURF)
    ax.bar(x, d.actual, color=BAR, width=0.8, label="Actual hires")
    ax.plot(x, d.predicted_day_ahead, color=BLUE, lw=2, label="Model (day ahead)")
    ax.plot(x, d.baseline_last_week, color=ORANGE, lw=1.5, ls="--", label="Same hour last week")
    starts = [i for i, (a, b) in enumerate(zip(d.day, [None] + list(d.day)[:-1])) if a != b]
    ax.set_xticks(starts)
    ax.set_xticklabels([pd.Timestamp(day).strftime("%a %d %b") for day in d.day.iloc[starts]], fontsize=9)
    for s in starts[1:]:
        ax.axvline(s - 0.5, color=GRID, lw=1)
    ax.set_ylabel("Hires per hour")
    ax.legend(frameon=False, loc="upper left", fontsize=9, ncol=3)
    ax.set_ylim(0, max(d.actual.max(), d.baseline_last_week.max()) * 1.25)
    tidy(ax, "y")
    fig.suptitle("The model follows the daily pattern; single hours stay noisy", x=0.02, ha="left",
                 fontsize=14, fontweight="bold")
    ax.set_title(f"{busiest[1]}, 06:00–21:59 London time, 11–15 May 2026 (test month)",
                 loc="left", fontsize=10, color=INK2, pad=10)
    fig.tight_layout()
    fig.savefig(OUT / "forecast_week.png", facecolor=SURF)


def levels_chart(df: pd.DataFrame) -> None:
    """Error as a share of hires, from single dock-hours up to areas."""
    df = df.copy()
    df["area"] = df.name.str.split(",").str[-1].str.strip()
    rush = df[df.is_working_day & df.hour_of_day.between(7, 9)]
    cols = ["actual", "predicted_day_ahead", "baseline_last_week"]
    levels = {
        "One dock,\none hour": rush[cols],
        "One dock,\nwhole rush": rush.groupby(["dock_id", "day"])[cols].sum(),
        "One area,\nwhole rush": rush.groupby(["area", "day"])[cols].sum(),
    }
    pct = lambda g, c: (g.actual - g[c]).abs().mean() / g.actual.mean() * 100
    model = [pct(g, "predicted_day_ahead") for g in levels.values()]
    naive = [pct(g, "baseline_last_week") for g in levels.values()]
    fig, ax = plt.subplots(figsize=(8, 4.6), dpi=150)
    fig.patch.set_facecolor(SURF)
    x = range(len(levels))
    w = 0.36
    ax.bar([i - w / 2 - 0.01 for i in x], naive, w, color=ORANGE, label="Same days last week")
    ax.bar([i + w / 2 + 0.01 for i in x], model, w, color=BLUE, label="Model (day ahead)")
    for i in x:
        ax.text(i - w / 2 - 0.01, naive[i] + 1.5, f"{naive[i]:.0f}%", ha="center", fontsize=10, color=INK)
        ax.text(i + w / 2 + 0.01, model[i] + 1.5, f"{model[i]:.0f}%", ha="center", fontsize=10,
                color=INK, fontweight="bold")
    ax.set_xticks(list(x))
    ax.set_xticklabels(list(levels), color=INK)
    ax.tick_params(axis="x", length=0)
    ax.set_ylabel("Average error as % of actual hires")
    ax.set_ylim(0, max(naive) * 1.2)
    ax.legend(frameon=False, loc="upper right", fontsize=10)
    tidy(ax, "y")
    fig.suptitle(f"Planning by area cuts the error from {model[0]:.0f}% to {model[-1]:.0f}%",
                 x=0.02, ha="left", fontsize=14, fontweight="bold")
    ax.set_title("Working-day morning rush (07:00–09:59 London), May 2026",
                 loc="left", fontsize=10, color=INK2, pad=10)
    fig.tight_layout()
    fig.savefig(OUT / "forecast_levels.png", facecolor=SURF)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with psycopg.connect(DSN) as conn:
        df = pd.read_sql(SQL, conn)
    week_chart(df)
    levels_chart(df)
    print(f"Saved charts to {OUT}")


if __name__ == "__main__":
    main()
