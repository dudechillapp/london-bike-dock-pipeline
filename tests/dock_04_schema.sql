-- Every dock in the newest raw snapshot must still carry the fields we rely on.
-- Catches: TfL renaming or dropping a field.
WITH latest AS (SELECT payload FROM raw.bikepoint_snapshot ORDER BY pulled_at DESC LIMIT 1),
expected(key) AS (VALUES ('NbBikes'), ('NbEBikes'), ('NbEmptyDocks'), ('NbDocks'), ('TerminalName'))
SELECT e.key AS missing_field, count(*) AS docks_missing_it
FROM latest, jsonb_array_elements(latest.payload) d
CROSS JOIN expected e
WHERE NOT EXISTS (SELECT 1 FROM jsonb_array_elements(d->'additionalProperties') p
                  WHERE p->>'key' = e.key)
GROUP BY e.key;
