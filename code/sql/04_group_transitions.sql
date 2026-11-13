-- Adjacent observed group changes only. Missing and tied endpoints were excluded.
-- Counts omit analyst-only changes and unobserved intermediate groups.
SELECT from_group, to_group, count(*) AS observed_changes,
       count(DISTINCT number) AS distinct_incidents
FROM resolution_gap.transitions
GROUP BY from_group, to_group
ORDER BY observed_changes DESC, from_group, to_group;
