-- Consequential cardinality and endpoint checks. Retained event rows reconcile.
SELECT (SELECT count(*) FROM resolution_gap.events) AS events,
       (SELECT count(DISTINCT event_id) FROM resolution_gap.events) AS unique_events,
       (SELECT count(*) FROM resolution_gap.incidents) AS incidents,
       (SELECT count(DISTINCT number) FROM resolution_gap.incidents) AS unique_incidents,
       (SELECT sum(event_count) FROM resolution_gap.incidents) AS summed_event_counts,
       (SELECT count(*) FROM resolution_gap.events e JOIN resolution_gap.incidents i USING(number)) AS joined_rows,
       (SELECT count(*) FROM resolution_gap.incidents WHERE resolution_hours<0 OR closure_hours<0) AS negative_eligible,
       (SELECT count(*) FROM resolution_gap.transitions t LEFT JOIN resolution_gap.incidents i USING(number) WHERE i.number IS NULL) AS orphan_transitions;
