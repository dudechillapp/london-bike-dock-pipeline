# Project Brief: London Bike Dock Pipeline

I'm building a pipeline that collects live London bike-dock data every 15 minutes, finds the docks that run empty, and forecasts which ones will be empty an hour from now.

## Why I'm doing this
I've spent years around last-mile fleets: as a rider and supervisor at Gorillas, where I also checked the e-bikes on the spot, and now as a logistics data analyst at Picnic. A vehicle in the wrong place at the wrong time is a lost order or a lost ride. London's Santander Cycles network has the same problem, and its data is public, so I can show the whole journey from raw API to a forecast someone could act on.

## Business question
Which Santander Cycles docks in London run out of bikes between 07:00 and 10:00 on weekdays, how much does rain change demand, and can I warn operators 1 hour before a dock runs empty so a van can restock it in time?

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
| Forecast error | MAE (Mean Absolute Error): the average number of bikes my 1-hour forecast is off by, compared with "bikes in 1 hour = bikes now" |

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
