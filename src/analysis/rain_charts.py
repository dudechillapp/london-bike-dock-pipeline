"""Draw the two rain-effect charts for docs/findings.md from marts.hires_weather.

Run from the project folder:
    python -m src.analysis.rain_charts
Saves docs/img/rain_bands.png and docs/img/rain_by_hour.png.
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import psycopg
from matplotlib.patches import FancyBboxPatch

from src.analysis.rain_effect import ANALYSES
from src.checks.dock_gaps import DSN

OUT = Path(__file__).resolve().parents[2] / "docs" / "img"
SURF, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
DRY, RAIN = "#2a78d6", "#eb6834"                   # validated categorical slots 1 and 2
BAND_COLOURS = ["#86b6ef", "#2a78d6", "#104281"]   # one hue, light to dark: heavier rain = darker

plt.rcParams.update({"font.size": 11, "axes.edgecolor": GRID, "text.color": INK,
                     "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2})


def query(sql: str) -> list[tuple]:
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        cur.execute(sql)
        return cur.fetchall()


def tidy(ax, grid_axis: str) -> None:
    ax.set_facecolor(SURF)
    ax.grid(axis=grid_axis, color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    for side in ["top", "right", "left"]:
        ax.spines[side].set_visible(False)


def rain_bands() -> None:
    rows = [r for r in query(ANALYSES["5. Does heavier rain cut more? (working days, 07:00-19:59, vs dry same month and hour)"])
            if not r[0].startswith("0 mm")]
    labels = {"0.1-0.5 mm (drizzle)": "Drizzle\n0.1–0.5 mm", "0.6-2 mm (rain)": "Rain\n0.6–2 mm",
              "over 2 mm (heavy)": "Heavy rain\nover 2 mm"}
    fig, ax = plt.subplots(figsize=(8, 4.6), dpi=150)
    fig.patch.set_facecolor(SURF)
    ys = list(range(len(rows)))[::-1]
    for y, (band, hours, change), colour in zip(ys, rows, BAND_COLOURS):
        drop = -float(change)
        ax.add_patch(FancyBboxPatch((0, y - 0.28), drop, 0.56, boxstyle="round,pad=0,rounding_size=0.12",
                                    mutation_aspect=0.25, fc=colour, ec="none"))
        ax.text(drop + 0.8, y, f"−{drop:.0f}%", va="center", fontsize=13, fontweight="bold")
        ax.text(drop + 0.8, y - 0.3, f"{hours} hours", va="center", fontsize=9, color=INK2)
    ax.set_yticks(ys)
    ax.set_yticklabels([labels.get(r[0], r[0]) for r in rows], color=INK)
    ax.tick_params(axis="y", length=0)
    ax.set_xlim(0, 42)
    ax.set_ylim(-0.6, len(rows) - 0.4)
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0f}%")
    ax.set_xlabel("Fewer hires than a dry hour (same month, same hour of day)")
    tidy(ax, "x")
    fig.suptitle("The heavier the rain, the fewer people hire a bike", x=0.02, ha="left",
                 fontsize=14, fontweight="bold")
    ax.set_title("Working days, 07:00–19:59 London time", loc="left", fontsize=10, color=INK2, pad=10)
    fig.tight_layout()
    fig.savefig(OUT / "rain_bands.png", facecolor=SURF)


def rain_by_hour() -> None:
    rows = query(ANALYSES["4. Rain effect by hour of the day, working days (fair comparison)"])
    hours = [r[0] for r in rows]
    dry = [float(r[2]) for r in rows]
    rain = [float(r[3]) for r in rows]
    drop = {r[0]: float(r[4]) for r in rows}
    fig, ax = plt.subplots(figsize=(8, 4.6), dpi=150)
    fig.patch.set_facecolor(SURF)
    ax.plot(hours, dry, color=DRY, lw=2, marker="o", ms=4, label="Dry hour")
    ax.plot(hours, rain, color=RAIN, lw=2, marker="o", ms=4, label="Rainy hour (> 0.5 mm)")
    top = max(dry)
    line = dict(arrowstyle="-", color=INK2, lw=0.8)
    for peak, x_text in [(8, 9.6), (17, 18.6)]:
        mid = (dry[hours.index(peak)] + rain[hours.index(peak)]) / 2
        ax.annotate(f"{peak:02d}:00 peak: −{drop[peak]:.0f}% in rain", xy=(peak + 0.15, mid),
                    xytext=(x_text, top * 0.91), fontsize=10, va="center", arrowprops=line)
    ax.set_xticks(range(0, 24, 2))
    ax.set_xticklabels([f"{h:02d}:00" for h in range(0, 24, 2)], fontsize=9)
    ax.set_xlim(-0.5, 23.5)
    ax.set_ylim(0, top * 1.1)
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:,.0f}")
    ax.set_ylabel("Average hires per hour")
    ax.legend(frameon=False, loc="upper left", fontsize=10)
    tidy(ax, "y")
    fig.suptitle("Rain cuts hires at every hour of the working day", x=0.02, ha="left",
                 fontsize=14, fontweight="bold")
    ax.set_title("Working days, London time; rainy hours compared with dry hours in the same month",
                 loc="left", fontsize=10, color=INK2, pad=10)
    fig.tight_layout()
    fig.savefig(OUT / "rain_by_hour.png", facecolor=SURF)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rain_bands()
    rain_by_hour()
    print(f"Saved charts to {OUT}")


if __name__ == "__main__":
    main()
