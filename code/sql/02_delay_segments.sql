-- First-observed case mix; never silently backfill a missing opening attribute.
WITH dimensions AS (
    SELECT i.*, d.dimension, coalesce(d.value, 'Unknown') AS segment
    FROM resolution_gap.incidents i
    CROSS JOIN LATERAL (VALUES ('category', initial_category),
                              ('priority', initial_priority),
                              ('location', initial_location)) d(dimension, value)
)
SELECT dimension, segment, count(*) AS incidents, count(resolution_hours) AS resolution_n,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY resolution_hours) AS median_hours,
       percentile_cont(0.9) WITHIN GROUP (ORDER BY resolution_hours) AS p90_hours,
       sum(resolution_hours) AS total_elapsed_incident_hours
FROM dimensions
GROUP BY dimension, segment
ORDER BY dimension, incidents DESC;
