-- KPI definitions (DuckDB). Each block computes one measure from the KPI dictionary.
-- {awb} is a view with one row per AWB (see block "prepare"); {shifts} has one row per shift worked.
-- $cutoff is the end of the data cut-off day; $shift_hours is the paid length of a shift.
-- An AWB is scored for on-time once its promise has fallen due before the cut-off; a scored AWB with no NFD is late.

-- name: prepare
-- Adds the promise, the due time and the arrival calendar fields to a table of AWBs.
CREATE OR REPLACE VIEW {name} AS
SELECT s.*, p.sla_h,
       s.arr_ts + to_minutes(CAST(p.sla_h * 60 AS BIGINT)) AS due_ts,
       CAST(hour(s.arr_ts) AS INTEGER) AS arr_hour,
       CAST(isodow(s.arr_ts) - 1 AS INTEGER) AS arr_weekday,
       CASE WHEN hour(s.arr_ts) < 6 OR hour(s.arr_ts) >= 22 THEN 'Night'
            WHEN hour(s.arr_ts) < 14 THEN 'Morning' ELSE 'Afternoon' END AS arr_shift,
       date_trunc('month', s.arr_ts) AS arr_month
FROM {source} s
LEFT JOIN sla p ON p.product = s.product;

-- name: nfd_on_time
-- NFD on time %: share of scored AWBs notified ready within the promise.
SELECT COUNT(*) AS scored,
       COUNT(*) FILTER (WHERE nfd_ts <= due_ts) AS on_time,
       COUNT(*) FILTER (WHERE nfd_ts <= due_ts) / COUNT(*) AS value
FROM {awb}
WHERE due_ts < $cutoff;

-- name: nfd_on_time_by
-- NFD on time % for each level of one dimension (product, carrier, arrival shift or arrival hour).
SELECT {dim} AS level,
       COUNT(*) AS scored,
       AVG(CASE WHEN nfd_ts <= due_ts THEN 1.0 ELSE 0.0 END) AS value
FROM {awb}
WHERE due_ts < $cutoff
GROUP BY 1
ORDER BY 1;

-- name: on_time_hour_weekday
-- NFD on time % by arrival hour and weekday (Monday is 0), for the heatmap.
SELECT arr_weekday, arr_hour, COUNT(*) AS scored,
       AVG(CASE WHEN nfd_ts <= due_ts THEN 1.0 ELSE 0.0 END) AS value
FROM {awb}
WHERE due_ts < $cutoff
GROUP BY 1, 2
ORDER BY 1, 2;

-- name: monthly
-- AWBs, tonnes and NFD on time % by arrival month.
SELECT arr_month,
       COUNT(*) AS awbs,
       SUM(weight_kg) / 1000 AS tonnes,
       AVG(CASE WHEN nfd_ts <= due_ts THEN 1.0 ELSE 0.0 END) FILTER (WHERE due_ts < $cutoff) AS on_time
FROM {awb}
GROUP BY 1
ORDER BY 1;

-- name: handler_time
-- Handler time, ARR to NFD, in hours: median and 90th percentile. The terminal owns this clock.
SELECT quantile_cont(epoch(nfd_ts - arr_ts) / 3600, 0.5) AS p50_h,
       quantile_cont(epoch(nfd_ts - arr_ts) / 3600, 0.9) AS p90_h,
       COUNT(*) AS n
FROM {awb}
WHERE nfd_ts IS NOT NULL;

-- name: customer_time
-- Customer time, NFD to DLV, in hours: median and 90th percentile. Customs and the forwarder own this clock.
-- Only AWBs notified at least 7 days before the cut-off, so slow pickups still open at the cut-off do not bias it.
SELECT quantile_cont(epoch(dlv_ts - nfd_ts) / 3600, 0.5) AS p50_h,
       quantile_cont(epoch(dlv_ts - nfd_ts) / 3600, 0.9) AS p90_h,
       COUNT(*) AS n
FROM {awb}
WHERE dlv_ts IS NOT NULL AND nfd_ts < $cutoff - INTERVAL 7 DAY;

-- name: time_split_by_product
-- Mean handler time and mean customer time by product, and the handler's share of total dwell.
SELECT product,
       AVG(epoch(nfd_ts - arr_ts) / 3600) AS handler_h,
       AVG(epoch(dlv_ts - nfd_ts) / 3600) AS customer_h,
       SUM(epoch(nfd_ts - arr_ts)) / SUM(epoch(dlv_ts - arr_ts)) AS handler_share,
       COUNT(*) AS n
FROM {awb}
WHERE dlv_ts IS NOT NULL AND nfd_ts < $cutoff - INTERVAL 7 DAY
GROUP BY 1
ORDER BY handler_h;

-- name: dwell_split
-- Share of total dwell (ARR to DLV) that sits on the handler's clock, all products.
SELECT SUM(epoch(nfd_ts - arr_ts)) / SUM(epoch(dlv_ts - arr_ts)) AS handler_share,
       AVG(epoch(dlv_ts - arr_ts) / 3600) AS dwell_mean_h
FROM {awb}
WHERE dlv_ts IS NOT NULL AND nfd_ts < $cutoff - INTERVAL 7 DAY;

-- name: throughput
-- Breakdown throughput: kilograms broken down per present staff hour, by shift.
SELECT shift_name AS level,
       SUM(kg) / SUM(present * $shift_hours) AS value,
       SUM(present * $shift_hours) AS staff_hours
FROM {shifts}
WHERE present > 0
GROUP BY 1
ORDER BY 1;

-- name: backlog_at_shift_end
-- Backlog at shift end: AWBs that had arrived but were not yet received from the flight when the shift ended.
WITH arr_c AS (
    SELECT arr_ts AS ts, SUM(COUNT(*)) OVER (ORDER BY arr_ts) AS cum FROM {awb} GROUP BY arr_ts
), rcf_c AS (
    SELECT rcf_ts AS ts, SUM(COUNT(*)) OVER (ORDER BY rcf_ts) AS cum FROM {awb} WHERE rcf_ts IS NOT NULL GROUP BY rcf_ts
), ends AS (
    SELECT shift_name, end_ts FROM {shifts} WHERE end_ts <= $cutoff AND end_ts > (SELECT MIN(arr_ts) FROM {awb}) + INTERVAL 1 DAY
), b AS (
    SELECT e.shift_name, e.end_ts, a.cum - COALESCE(r.cum, 0) AS backlog
    FROM ends e
    ASOF LEFT JOIN arr_c a ON e.end_ts > a.ts
    ASOF LEFT JOIN rcf_c r ON e.end_ts > r.ts
)
SELECT shift_name AS level, AVG(backlog) AS value, quantile_cont(backlog, 0.9) AS p90, MAX(backlog) AS max
FROM b
GROUP BY 1
ORDER BY 1;

-- name: late_per_1000
-- Late shipments per 1,000 scored AWBs.
SELECT 1000.0 * COUNT(*) FILTER (WHERE NOT COALESCE(nfd_ts <= due_ts, FALSE)) / COUNT(*) AS value
FROM {awb}
WHERE due_ts < $cutoff;

-- name: completeness
-- Data completeness: share of AWBs with all four milestones present and in order (ARR, RCF, NFD, DLV).
-- Only AWBs that arrived at least 14 days before the cut-off, so the customer has had time to collect.
SELECT AVG(CASE WHEN arr_ts IS NOT NULL AND rcf_ts IS NOT NULL AND nfd_ts IS NOT NULL AND dlv_ts IS NOT NULL
                 AND arr_ts <= rcf_ts AND rcf_ts <= nfd_ts AND nfd_ts <= dlv_ts THEN 1.0 ELSE 0.0 END) AS value,
       COUNT(*) AS n
FROM {awb}
WHERE arr_ts < $cutoff - INTERVAL 14 DAY;
