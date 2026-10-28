-- Every loaded journey file must be staged, with no rows lost.
SELECT r.file_name, r.row_count, s.rows_staged
FROM raw.journey_file r
LEFT JOIN staging.journey_file_staged s USING (file_name)
WHERE s.rows_staged IS DISTINCT FROM r.row_count;
