# Findings

What the data shows so far, with the evidence behind each result.
Data: 9,015,474 valid Santander Cycles hires (June 2025 to May 2026) joined to hourly London weather.

---

## Finding 1: Rain cuts hires by about 28%, and heavier rain cuts more

**On working days, an hour with more than 0.5 mm of rain has about 28% fewer hires than a dry hour at the same time of day in the same month.**

![Hires drop more the heavier the rain](img/rain_bands.png)

| Rain in the hour | Hires compared with a dry hour | Hours of data |
| --- | --- | --- |
| Drizzle (0.1–0.5 mm) | −13% | 477 |
| Rain (0.6–2 mm) | −28% | 139 |
| Heavy rain (over 2 mm) | −35% | 32 |

The steady step from drizzle to heavy rain is the strongest evidence here: a real effect gets bigger as the cause gets bigger.

### When rain matters most

![Rain cuts hires at every hour of the working day](img/rain_by_hour.png)

- **Both commuter peaks drop by about 27%** in rain (08:00 and 17:00).
- **07:00 drops only about 12%.** The earliest commuters seem to ride anyway.
- **Midday and early afternoon drop the most, about 30–36%.** Those trips are more optional, so rain puts people off more easily.

### How I measured it
- **Rain** means more than 0.5 mm in the hour, the definition from the [project brief](project_brief.md).
- **Like with like:** each rainy hour is compared with dry hours in the same month, at the same hour of the day, on the same kind of day (working day or not). Otherwise rain would also pick up the effect of winter and night-time, when fewer people ride anyway.
- **Working days** are Monday to Friday, excluding England bank holidays.
- **Valid trips only:** 1 minute to 1 day, ending after they start (see [data issue 5](data_issues.md)).

A simpler comparison of all rainy hours against all dry hours gives 26.8%, close to the 27.8% above. So in London, season and time of day barely distort the rain effect. I checked rather than assumed it.

### Limits
- **Rainy hours are rare.** Only 340 hours in the year had more than 0.5 mm, so each hour of the day has just 5 to 19 rainy hours behind it. The overall figure is solid; the hour-by-hour figures are signals, not facts.
- **Heavy rain has only 32 hours of data.** −35% is a direction, not a precise number.
- **The weather is one point in central London.** Outer areas may have had different rain in the same hour.
- **This is correlation.** Rain often comes with wind and cold. I haven't yet separated those effects.

---

## Recommendation to test: a rain discount

**My suggestion:** make hires cheaper when it rains, scaled to how heavy the rain is, to win back some of the riders rain puts off.

**What the data supports**
- There is real demand to win back: 13% to 35% of hires are lost in rain, depending on how heavy it is.
- Where to aim it: **midday and early afternoon**, where rain cuts the most hires (about 30–36%) and the bikes are least busy anyway.
- Where not to: **the 07:00 commute**, where most riders come anyway. A discount there would mostly give money to people who'd have paid full price.

**What the data can't tell us yet**
This data has no prices, so it can't show whether a discount would actually bring riders back, or how much revenue it would cost. That needs a test:
1. Run a pilot: a rain discount on some days or in some areas, and normal prices on the others.
2. Compare hires in rainy hours between the two groups.
3. Check that the extra hires are worth more than the discount given to riders who would have come anyway.

**A question for operations:** with about 27% fewer hires on wet mornings, do the usual problem docks still run empty? If not, a rain forecast could let the rebalancing team send fewer vans. My live dock data will answer this once it covers some rainy mornings.

---

_Reproduce: `python -m src.analysis.rain_effect` (numbers) and `python -m src.analysis.rain_charts` (charts)._
