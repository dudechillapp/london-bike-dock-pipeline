-- The newest pull must have 700 to 900 docks (London has about 800).
-- Catches: a half-empty API response, or a staging step that dropped rows.
SELECT pulled_at, count(*) AS docks
FROM staging.dock_status
WHERE pulled_at = (SELECT max(pulled_at) FROM staging.dock_status)
GROUP BY pulled_at
HAVING count(*) NOT BETWEEN 700 AND 900;
