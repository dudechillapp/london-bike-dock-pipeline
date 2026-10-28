-- At least 97 percent of hires must link to a dock (it is about 98.8 now).
-- Catches: TfL changing station ids, or the dock dimension going stale (see data issue 4).
SELECT round(100.0 * count(*) FILTER (WHERE start_match = 'matched') / count(*), 2) AS pct_matched
FROM staging.journeys
HAVING 100.0 * count(*) FILTER (WHERE start_match = 'matched') / count(*) < 97;
