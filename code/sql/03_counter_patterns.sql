-- Counters are terminal only after zero-start/nondecreasing checks in clean.py.
SELECT reassignment_count, reopen_count, count(*) AS incidents,
       count(resolution_hours) AS resolution_n,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY resolution_hours) AS median_hours,
       percentile_cont(0.9) WITHIN GROUP (ORDER BY resolution_hours) AS p90_hours
FROM resolution_gap.incidents
GROUP BY reassignment_count, reopen_count
ORDER BY incidents DESC;
