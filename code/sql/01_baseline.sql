-- One incident per row. Outcome denominators differ when endpoints are unknown.
SELECT count(*) AS incidents,
       (SELECT count(*) FROM resolution_gap.events) AS events,
       count(resolution_hours) AS resolution_n,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY resolution_hours) AS resolution_median_hours,
       percentile_cont(0.9) WITHIN GROUP (ORDER BY resolution_hours) AS resolution_p90_hours,
       count(closure_hours) AS closure_n,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY closure_hours) AS closure_median_hours,
       count(reopen_count) AS reopen_eligible_n,
       count(*) FILTER (WHERE reopen_count > 0) AS reopened_n,
       100.0 * count(*) FILTER (WHERE reopen_count > 0) / nullif(count(reopen_count), 0) AS reopened_pct
FROM resolution_gap.incidents;
