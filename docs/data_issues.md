# Data Issues Log

Problems I found in the source data, what I think causes them, and what I do about them.
Newest first. Each issue keeps the query I used, so anyone can check it again.

| # | Found | Issue | Status |
| --- | --- | --- | --- |
| 2 | 22 Oct 2026 | Stray spaces in dock names | Fix planned |
| 1 | 22 Oct 2026 | Bikes + empty docks don't add up to total docks | Fix planned |

---

## 2. Stray spaces in dock names

**What I saw**
Some dock names have extra spaces, for example `Dunston Road , Haggerston` (a space before the comma).

**Likely cause**
Names are typed in by hand in TfL's system and come through the API exactly as entered.

**Why it matters**
- Searches and joins on the name can miss a dock: `Dunston Road, Haggerston` won't match.
- The AI agent in Step 8 searches docks by name (for example "docks near Waterloo"), so messy names mean missed answers.

**What I'll do**
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

**Open question:** 81% is much higher than I'd expect from broken docking points alone, so there may be a second cause. Next I'll check:
- whether `NbBikes` equals `NbStandardBikes + NbEBikes`, or leaves some bikes out;
- whether the same docks show gaps all day (broken hardware) or the gaps move around (something else, such as bikes reserved or being returned).

I won't use `bikes + empty_docks` as usable capacity until I know which it is.
