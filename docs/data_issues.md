# Data Issues Log

Problems I found in the source data, what I think causes them, and what I do about them.
Newest first. Each issue keeps the query I used, so anyone can check it again.

| # | Found | Issue | Status |
| --- | --- | --- | --- |
| 5 | 23 Oct 2026 | Unrealistic hire durations | Fixed: `is_valid_trip` flag |
| 4 | 23 Oct 2026 | Terminal numbers reused for docks elsewhere | Fixed: match on number and name |
| 3 | 23 Oct 2026 | Collector down for about 17 hours | Fixed |
| 2 | 22 Oct 2026 | Stray spaces in dock names | Fixed: `staging.clean_name()` |
| 1 | 22 Oct 2026 | Bikes + empty docks don't add up to total docks | Cause likely found, confirming with 24 h of data |

---

## 5. Unrealistic hire durations

**What I saw** (`python -m src.checks.journeys_check`, 9,093,044 hires, Jun 2025 to May 2026)
- 71,463 hires under 1 minute.
- 5,857 hires over 1 day.
- 66 hires that end before they start, and 184 with no duration.
- The average hire in June 2025 came out at 47.7 minutes, while the median over the whole year is 13.3 minutes.

**Likely cause**
- Under 1 minute: a bike taken out and docked again straight away, for example because it was faulty or the rider changed their mind.
- Over 1 day: bikes not docked properly, lost, or recovered later.
- Ending before starting: most likely clock or recording errors. Too few to matter, but impossible, so they can't count.

**Why it matters**
- These aren't real trips, so they would inflate demand counts slightly and distort average durations a lot.
- A forecast trained on them would learn noise.

**What I did**
- Added `is_valid_trip` to `staging.journeys`: true when a hire lasts 1 minute to 1 day and ends after it starts. Demand analysis uses valid trips only.
- Kept every row. Nothing is deleted, so the rule can be changed later.
- Report medians, not averages, for durations.

---

## 4. Terminal numbers reused for docks elsewhere

**What I saw**
Journey files identify stations by TfL's terminal number (for example `001058`), not the `BikePoints_` id the live API uses. 799 station ids matched a live terminal number and none matched a BikePoints number. But for 3 of them the names didn't agree:

| Terminal | Name in journey files | Name in live API | Journeys |
| --- | --- | --- | --- |
| 002681 | Harriet Street, Knightsbridge | Lowndes Square, Knightsbridge | 10,477 |
| 001058 | Edgware Road Station, Marylebone | Orchard Place, Blackwall Tunnel | 6,150 |
| 002639 | King Edward Walk, Waterloo | Brockwell Lido, Brixton | 2,910 |

**Likely cause**
TfL reuses a terminal number when a dock closes and a new one opens, sometimes on the other side of London.

**Why it matters**
Matching on the number alone would place about 19,500 journeys at the wrong dock, miles from where they started. A forecast for Orchard Place would include Edgware Road's demand.

**What I did**
- A journey only links to a dock when the terminal number **and** the cleaned name agree.
- New columns `start_match` and `end_match` record the outcome: `matched`, `name_mismatch` or `no_dock`, so the rule is visible rather than hidden.
- 17 station ids have no live dock at all, mostly closed or moved docks marked `_OLD` (for example `London Fields, Hackney Central_OLD`). They stay unmatched.

**Lesson**
An id that matches isn't proof that it's the same thing. Check a second attribute before trusting a join.

---

## 3. Collector down for about 17 hours

**What I saw**
`logs/collector.log` showed only 5 scheduled pulls on 22 Oct, from 16:53 to 17:50 (Düsseldorf time). After that:
- 17:50–19:55: no runs at all, because my PC was asleep.
- 19:55–21:54 and 10:24–10:39 the next morning: 11 runs, all failing with `psycopg.errors.ConnectionTimeout` on port 5432.
- Overnight: no runs, because the PC was off.

**Cause**
The scheduled task kept running, but Docker Desktop wasn't. It doesn't start by itself after a restart, so the warehouse was down and every run timed out.

**Why it matters**
- No dock data for about 17 hours, and nothing told me. I only found out by reading the log the next day.
- A dashboard or forecast built on this data would have quietly used stale numbers.

**What I did**
- Turned on "Start Docker Desktop when you sign in". The warehouse container already restarts with Docker (`restart: unless-stopped`).
- Set a collection window: weekdays 07:30–11:30 Düsseldorf time at minimum, which covers the 07:00–10:00 London rush in the project brief. Overnight data isn't needed for the question.
- Downstream SQL ignores gaps longer than 1 hour, so a missed slot can't be counted as hours of empty docks.

**What I'll add**
- A freshness test in Step 6: fail and alert if the newest `pulled_at` is more than 20 minutes old during the collection window. With that, this outage would have been caught after 20 minutes instead of 17 hours.

**Lesson**
"The job ran" and "the data arrived" are different things. Monitor the data, not just the job.

---

## 2. Stray spaces in dock names

**What I saw**
Some dock names have extra spaces, for example `Dunston Road , Haggerston` (a space before the comma).

**Likely cause**
Names are typed in by hand in TfL's system and come through the API exactly as entered.

**Why it matters**
- Searches and joins on the name can miss a dock: `Dunston Road, Haggerston` won't match.
- The AI agent in Step 8 searches docks by name (for example "docks near Waterloo"), so messy names mean missed answers.

**What I did (23 Oct 2026)**
Added `staging.clean_name()`, used for dock names and journey station names. Raw names stay untouched.

**Original plan**
- Keep the raw name untouched in `raw`, as with all raw data.
- In staging, clean it: trim spaces at the ends, remove a space before a comma, and collapse double spaces.
- Join on `dock_id` everywhere, never on the name.

**Query to measure it**
```sql
SELECT dock_id, name
FROM staging.dock
WHERE name ~ '\s,|\s{2,}|^\s|\s$';
```

---

## 1. Bikes + empty docks don't add up to total docks

**What I saw**
At some docks, available bikes plus empty docks is less than the total number of docks.
Examples from the 14:53 UTC pull on 22 Oct 2026:

| Dock | Bikes | Empty docks | Total docks | Unaccounted |
| --- | --- | --- | --- | --- |
| Abingdon Villas, Kensington | 0 | 11 | 17 | 6 |
| Black Lion Gate, Kensington Gardens | 0 | 20 | 24 | 4 |
| Gascoyne Road, Victoria Park | 0 | 17 | 20 | 3 |

**Likely cause**
TfL leaves docking points that are out of service out of both the bike count (`NbBikes`) and the empty count (`NbEmptyDocks`), but still counts them in the total (`NbDocks`).
So the gap is most likely broken docking points, or bikes locked in for repair.

**Why it matters**
- A dock can look half empty when riders actually can't use a third of it.
- **Full-dock minutes** would be undercounted: a dock with broken spaces fills up sooner than its total suggests.
- Using `total_docks` as capacity would give wrong availability percentages.

**What I'll do**
- Add a calculated column in staging:
  `broken_docks = total_docks - bikes - empty_docks`
- Use `bikes + empty_docks` as the **usable capacity**, not `total_docks`.
- Add a data quality test (Step 6) that fails if `broken_docks` is ever negative, which would mean the meaning of a field has changed.
- Track which docks have broken spaces for days at a time. That's a useful maintenance list for operations, beyond what this project set out to answer.

**Query to measure it**
```sql
SELECT count(*)                                AS docks_with_gaps,
       sum(total_docks - bikes - empty_docks)  AS spaces_out_of_service
FROM staging.dock_status
WHERE pulled_at = (SELECT max(pulled_at) FROM staging.dock_status)
  AND bikes + empty_docks < total_docks;
```

**Size of the problem (pull at about 15:00 UTC, 22 Oct 2026):** 648 of 801 docks (81%) had a gap, adding up to 1,597 docking points not counted as either a bike or a free space.

**Investigation, 22 Oct 2026** (`python -m src.checks.dock_gaps`, 3 pulls from 14:48 to 15:05 UTC)

81% looked too high for broken hardware alone, so I tested the other explanations first:

| Check | Result | Conclusion |
| --- | --- | --- |
| Does `NbBikes` = `NbStandardBikes` + `NbEBikes`? | Equal at all 801 docks | Not the cause: no bikes are left out of the count |
| Are the gaps at docks flagged `Locked` or not `Installed`? | All 801 docks are installed and unlocked | Not the cause: the flags don't explain it |
| How big are the gaps? | Mostly 1–3 spaces (524 docks), up to 10 | A few spaces per dock, not whole docks closed |
| Same docks every pull? | 648 docks had a gap in every pull; 631 of them never changed size | The gaps are fixed |
| Does the gap move when bikes are hired or returned? | Bikes changed in 486 dock steps, the gap in only 21; correlation -0.10 | No link: hires and returns don't explain it |

**Conclusion so far:** the gaps are fixed per dock and don't move with hires or returns. That fits docking points that are out of service (broken, or holding a bike awaiting repair) far better than anything that changes minute to minute. So the 81% is most likely real: many docks have one or two broken points.

**Limit of this check:** 3 pulls over 17 minutes is a short window. I'll rerun it after 24 hours of data. If gaps still stay fixed through the morning and evening rush, the conclusion holds.

**Decision:** I'll add `broken_docks = total_docks - bikes - empty_docks` in staging and use `bikes + empty_docks` as usable capacity, as planned above, once the 24-hour rerun confirms it.

**Side findings from the same check**
- 4 docks are flagged `Temporary`. I'll keep a flag for them in `staging.dock`.
- Every dock still has a `RemovalDate` field, and at least one holds a date in 2018 even though the dock is installed. I won't rely on that field.
- More names with a stray space before the comma turned up (`Gower Place , Euston`, `Soho Square , Soho`), which supports issue 2.
