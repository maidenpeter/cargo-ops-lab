-- Risk model features (DuckDB): one row per scored AWB, using only what is known at aircraft arrival (ARR).
-- {awb}: prepared AWB view (see kpis.sql "prepare"); {flights}: the arrival schedule (sched_arr, n_awbs);
-- {roster}: rostered headcount by weekday (Monday 0) and shift (0 morning, 1 afternoon, 2 night).
-- $cutoff: end of the cut-off day; $window_h: look-ahead hours for scheduled arrivals.
-- Backlog at ARR uses other AWBs' RCF status at that moment, which the terminal knows; nothing from this AWB's
-- own RCF, NFD or DLV is used except the label.

-- name: features
WITH arr_c AS (
    SELECT arr_ts AS ts, SUM(COUNT(*)) OVER (ORDER BY arr_ts) - COUNT(*) AS arrived_before
    FROM {awb} GROUP BY arr_ts
), rcf_c AS (
    SELECT rcf_ts AS ts, SUM(COUNT(*)) OVER (ORDER BY rcf_ts) AS received
    FROM {awb} WHERE rcf_ts IS NOT NULL GROUP BY rcf_ts
), sch AS (
    SELECT sched_arr AS ts, SUM(SUM(n_awbs)) OVER (ORDER BY sched_arr) AS cum
    FROM {flights} GROUP BY sched_arr
), base AS (
    SELECT w.*,
           CASE WHEN arr_hour < 6 THEN (arr_weekday + 6) % 7 ELSE arr_weekday END AS shift_weekday,
           CASE WHEN arr_hour < 6 OR arr_hour >= 22 THEN 2 WHEN arr_hour < 14 THEN 0 ELSE 1 END AS shift_idx
    FROM {awb} w
    WHERE due_ts < $cutoff
)
SELECT b.awb_id, b.arr_ts,
       b.product, b.handling_unit, b.carrier, b.flight_type, b.region,
       b.pieces, b.weight_kg, b.arr_hour, b.arr_weekday,
       epoch(b.arr_ts - b.sched_arr) / 60 AS delay_min,
       r.headcount AS rostered_headcount,
       a.arrived_before - COALESCE(rc.received, 0) AS backlog_at_arr,
       COALESCE(s2.cum, 0) - COALESCE(s1.cum, 0) AS sched_awbs_next_2h,
       CASE WHEN b.nfd_ts <= b.due_ts THEN 0 ELSE 1 END AS late
FROM base b
JOIN arr_c a ON a.ts = b.arr_ts
ASOF LEFT JOIN rcf_c rc ON b.arr_ts >= rc.ts
ASOF LEFT JOIN sch s1 ON b.arr_ts >= s1.ts
ASOF LEFT JOIN sch s2 ON b.arr_ts + to_hours($window_h) >= s2.ts
LEFT JOIN {roster} r ON r.weekday = b.shift_weekday AND r.shift = b.shift_idx
ORDER BY b.arr_ts, b.awb_id;
