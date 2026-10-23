-- 010_stage_dock_status.sql
-- Flattens raw.bikepoint_snapshot (one JSON blob per pull) into:
--   staging.dock         one row per dock: name and location
--   staging.dock_status  one row per dock per pull: bikes and spaces
--
-- Incremental: only snapshots newer than what is already staged are processed.
-- Idempotent: running it twice adds nothing the second time.

BEGIN;

-- 1. The snapshots that have not been staged yet
CREATE TEMP TABLE new_docks ON COMMIT DROP AS
SELECT s.pulled_at,
       d AS dock                                   -- one JSON object per dock
FROM raw.bikepoint_snapshot s,
     jsonb_array_elements(s.payload) d
WHERE s.pulled_at > COALESCE((SELECT max(pulled_at) FROM staging.dock_status),
                             '-infinity'::timestamptz);

-- 2. Dock dimension: add new docks, update names and locations that changed
INSERT INTO staging.dock (dock_id, name, lat, lon, first_seen, last_seen, terminal_name)
SELECT dock_id, name, lat, lon, first_seen, last_seen, terminal_name
FROM (
    SELECT dock->>'id'                       AS dock_id,
           dock->>'commonName'               AS name,
           (dock->>'lat')::numeric(9,6)      AS lat,
           (dock->>'lon')::numeric(9,6)      AS lon,
           min(pulled_at) OVER w             AS first_seen,
           max(pulled_at) OVER w             AS last_seen,
           (SELECT p->>'value' FROM jsonb_array_elements(dock->'additionalProperties') p
            WHERE p->>'key' = 'TerminalName')  AS terminal_name,
           ROW_NUMBER() OVER (PARTITION BY dock->>'id' ORDER BY pulled_at DESC) AS rn
    FROM new_docks
    WINDOW w AS (PARTITION BY dock->>'id')
) latest
WHERE rn = 1                                      -- keep the newest version of each dock
ON CONFLICT (dock_id) DO UPDATE
SET name       = EXCLUDED.name,
    lat        = EXCLUDED.lat,
    lon        = EXCLUDED.lon,
    terminal_name = EXCLUDED.terminal_name,
    first_seen = LEAST(staging.dock.first_seen, EXCLUDED.first_seen),
    last_seen  = GREATEST(staging.dock.last_seen, EXCLUDED.last_seen);

-- 3. Dock status: turn the key/value list into columns
INSERT INTO staging.dock_status (pulled_at, dock_id, bikes, ebikes, empty_docks, total_docks)
SELECT n.pulled_at,
       n.dock->>'id' AS dock_id,
       max(CASE WHEN p->>'key' = 'NbBikes'      THEN NULLIF(p->>'value', '')::int END) AS bikes,
       max(CASE WHEN p->>'key' = 'NbEBikes'     THEN NULLIF(p->>'value', '')::int END) AS ebikes,
       max(CASE WHEN p->>'key' = 'NbEmptyDocks' THEN NULLIF(p->>'value', '')::int END) AS empty_docks,
       max(CASE WHEN p->>'key' = 'NbDocks'      THEN NULLIF(p->>'value', '')::int END) AS total_docks
FROM new_docks n,
     jsonb_array_elements(n.dock->'additionalProperties') p
GROUP BY n.pulled_at, n.dock->>'id'
ON CONFLICT (dock_id, pulled_at) DO NOTHING;     -- safety net if a pull is processed twice

COMMIT;
