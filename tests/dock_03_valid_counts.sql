-- In the newest pull: no negative counts, and bikes + empty spaces never more than the total.
-- Catches: bad values, or a field that has changed meaning (see data issue 1).
SELECT dock_id, bikes, empty_docks, total_docks
FROM staging.dock_status
WHERE pulled_at = (SELECT max(pulled_at) FROM staging.dock_status)
  AND (bikes < 0 OR empty_docks < 0 OR total_docks < 0
       OR bikes + empty_docks > total_docks);
