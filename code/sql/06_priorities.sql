-- Prioritise investigative reach; summed calendar durations are not labor hours.
SELECT coalesce(initial_category, 'Unknown') AS category, count(*) AS incidents,
       count(resolution_hours) AS resolution_n,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY resolution_hours) AS median_hours,
       percentile_cont(0.9) WITHIN GROUP (ORDER BY resolution_hours) AS p90_hours,
       count(*) FILTER (WHERE reopen_count>0) AS reopened_n,
       count(*) FILTER (WHERE reassignment_count>=2) AS multi_reassignment_n,
       sum(resolution_hours) AS total_elapsed_incident_hours,
       100.0*sum(resolution_hours)/(SELECT sum(resolution_hours) FROM resolution_gap.incidents) AS elapsed_share_pct
FROM resolution_gap.incidents
GROUP BY initial_category HAVING count(*)>=200
ORDER BY total_elapsed_incident_hours DESC;
