-- The newest dock status must be less than 20 minutes old.
-- Catches: API down, collector stopped, staging not run (see data issue 3).
SELECT max(pulled_at) AS newest_pull, now() - max(pulled_at) AS age
FROM staging.dock_status
HAVING max(pulled_at) < now() - INTERVAL '20 minutes' OR max(pulled_at) IS NULL;
