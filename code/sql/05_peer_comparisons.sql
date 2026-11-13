-- Weighted within-stratum median differences are descriptive contrasts,
-- not adjusted population medians or causal effects. Minimum 20 in each arm.
WITH exposures AS (
    SELECT i.*, e.exposure, e.exposed
    FROM resolution_gap.incidents i
    CROSS JOIN LATERAL (VALUES
        ('multi_reassignment', reassignment_count >= 2),
        ('reopened', reopen_count > 0),
        ('knowledge_ever', knowledge_ever)
    ) e(exposure, exposed)
    WHERE resolution_hours IS NOT NULL AND initial_category IS NOT NULL
      AND initial_priority IS NOT NULL AND opened_at IS NOT NULL AND e.exposed IS NOT NULL
), cells AS (
    SELECT exposure, initial_category, initial_priority, date_trunc('month', opened_at) AS opened_month,
           count(*) AS n,
           count(*) FILTER (WHERE exposed) AS exposed_n,
           count(*) FILTER (WHERE NOT exposed) AS comparison_n,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY resolution_hours) FILTER (WHERE exposed)
           - percentile_cont(0.5) WITHIN GROUP (ORDER BY resolution_hours) FILTER (WHERE NOT exposed) AS difference_hours
    FROM exposures
    GROUP BY exposure, initial_category, initial_priority, date_trunc('month', opened_at)
), supported AS (
    SELECT * FROM cells WHERE exposed_n >= 20 AND comparison_n >= 20
)
SELECT s.exposure, count(*) AS supported_strata, sum(n) AS supported_n,
       sum(n * difference_hours) / sum(n) AS weighted_within_stratum_median_difference_hours,
       (SELECT count(*) FROM exposures e WHERE e.exposure=s.exposure) AS eligible_known_case_mix_n
FROM supported s GROUP BY s.exposure ORDER BY s.exposure;
