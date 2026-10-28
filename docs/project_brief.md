# Project Brief: London Bike Dock Pipeline

I'm building a pipeline that collects London bike-share data, measures what drives demand, and forecasts how many bikes each dock will hire out in the next hour. Live dock data adds a view of which docks run empty.

## Why I'm doing this
I've spent years around last-mile fleets: as a rider and supervisor at Gorillas, where I also checked the e-bikes on the spot, and now as a logistics data analyst at Picnic. A vehicle in the wrong place at the wrong time is a lost order or a lost ride. London's Santander Cycles network has the same problem, and its data is public, so I can show the whole journey from raw API to a forecast someone could act on.

## Business question
How many bikes will each Santander Cycles dock in London hire out in the next hour, how much does rain change that, and which docks run out of bikes on weekday mornings (07:00–10:00)? A reliable hourly forecast tells the rebalancing team where bikes will be needed before riders arrive.

## Who uses the answer
- **The rebalancing team:** with a 1-hour warning instead of reacting once a dock is already empty, they can send a van to the right dock before riders arrive to find nothing there.
- **Operations managers:** they get a ranked list of the docks that fail most often, so they can decide where extra capacity or a fixed morning restock pays off.
- **An AI agent:** later in the project, I expose the results through MCP (Model Context Protocol), so someone can ask "Which docks near Waterloo will be empty in the next hour?" and get an answer from trusted, read-only data.

## KPIs (Key Performance Indicators)
| KPI | Definition |
| --- | --- |
| Empty-dock minutes | Minutes in a day when a dock has 0 bikes available to hire |
| Full-dock minutes | Minutes in a day when a dock has 0 free spaces to return a bike |
| Peak availability | Average bikes available per dock, 07:00–10:00, Monday to Friday |
| Rain effect | % difference in hires between hours with more than 0.5 mm of rain and dry hours, at the same hour of the day |
| Forecast error | MAE (Mean Absolute Error): the average number of hires per dock my next-hour forecast is off by, compared with the best simple baseline (for example "same hour last week"), tested on a month the model never saw |

Rules that apply to every KPI:
- All times are London local time.
- Weekdays means Monday to Friday, excluding UK bank holidays.
- Docks that are out of service are not counted as empty.

## Scope
**In scope**
- All Santander Cycles docks in London (about 800).
- Live dock status every 15 minutes, starting October 2026.
- 12 months of historical journeys from TfL (Transport for London).
- Hourly London weather from Open-Meteo.

**Out of scope**
- E-bike battery levels and pricing.
- Planning the van routes themselves: I say where bikes are needed, not how to drive there.
- Other cities and other bike-share schemes.

## What success looks like
One sentence with real numbers that an operations manager could act on, for example:
"20 docks cause X% of weekday morning empty-dock minutes, rain cuts hires by Y%, and my 1-hour forecast beats the naive guess by Z%."

I'll only fill in X, Y and Z once my own data proves them.

## Change of plan (28 Oct 2026)
The original main forecast was empty docks 1 hour ahead, which needs weeks of live dock data on weekday mornings. My collector only runs while my PC is on, and it had several outages (see [data issue 3](data_issues.md)). So the main forecast is now **hires per dock per hour**, trained on 9 million historical journeys (June 2025 to May 2026). Empty-dock minutes stay in scope as a smaller analysis on the live mornings I collect.
