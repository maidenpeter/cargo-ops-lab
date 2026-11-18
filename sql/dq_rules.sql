-- Data quality rules for the milestone feed (DuckDB).
-- Inputs: awb_feed (one row per AWB message), event_feed (one row per milestone message), product_codes.
-- Parameters: $cutoff (end of the cut-off day), $offset_h (hub local minus UTC), $tol (weight tolerance),
-- $tol_kg (minimum kilograms for a weight flag), $grace_h (hours an AWB has to reach RCF and NFD before a missing message counts).
-- Every rule returns the AWB numbers it flags. Rules run on the feed as received.

-- name: feed_wide
-- One row per AWB from its first message, milestones pivoted, UTC kept alongside local time.
CREATE OR REPLACE VIEW feed_wide AS
WITH a AS (
    SELECT * FROM awb_feed
    QUALIFY ROW_NUMBER() OVER (PARTITION BY awb_id ORDER BY msg_id) = 1
), e AS (
    SELECT * FROM event_feed
    QUALIFY ROW_NUMBER() OVER (PARTITION BY awb_id, milestone ORDER BY msg_id) = 1
)
SELECT a.awb_id, a.flight_key, a.flight, a.carrier, a.flight_type, a.region, a.product_code, a.handling_unit,
       a.pieces, a.weight_kg, a.weight_checked_kg, a.sched_arr,
       MAX(e.ts_local) FILTER (WHERE e.milestone = 'ARR') AS arr_ts,
       MAX(e.ts_local) FILTER (WHERE e.milestone = 'RCF') AS rcf_ts,
       MAX(e.ts_local) FILTER (WHERE e.milestone = 'NFD') AS nfd_ts,
       MAX(e.ts_local) FILTER (WHERE e.milestone = 'DLV') AS dlv_ts,
       MAX(e.ts_utc) FILTER (WHERE e.milestone = 'ARR') AS arr_utc,
       MAX(e.ts_utc) FILTER (WHERE e.milestone = 'RCF') AS rcf_utc,
       MAX(e.ts_utc) FILTER (WHERE e.milestone = 'NFD') AS nfd_utc,
       MAX(e.ts_utc) FILTER (WHERE e.milestone = 'DLV') AS dlv_utc,
       COALESCE(BOOL_AND(e.ts_utc IS NULL), TRUE) AS utc_missing
FROM a LEFT JOIN e USING (awb_id)
GROUP BY ALL;

-- name: rule_duplicate_resend
-- The same AWB number arrives in more than one AWB record.
SELECT awb_id FROM awb_feed GROUP BY awb_id HAVING COUNT(*) > 1;

-- name: rule_missing_rcf
-- No RCF message, for an AWB that arrived long enough before the cut-off to have one.
SELECT awb_id FROM feed_wide
WHERE rcf_ts IS NULL AND arr_ts < $cutoff - to_hours($grace_h);

-- name: rule_missing_nfd
-- No NFD message, for an AWB that arrived long enough before the cut-off to have one.
SELECT awb_id FROM feed_wide
WHERE nfd_ts IS NULL AND arr_ts < $cutoff - to_hours($grace_h);

-- name: rule_out_of_sequence
-- Freight notified ready before it was received from the flight.
SELECT awb_id FROM feed_wide WHERE nfd_ts < rcf_ts;

-- name: rule_weight_mismatch
-- Checked-in weight differs from the manifest by more than the tolerance, and by at least the minimum kilograms.
SELECT awb_id FROM feed_wide
WHERE ABS(weight_checked_kg - weight_kg) > $tol * weight_kg AND ABS(weight_checked_kg - weight_kg) >= $tol_kg;

-- name: rule_invalid_product
-- Product code blank or not in the code list, so the promise cannot be looked up.
SELECT awb_id FROM feed_wide
WHERE product_code IS NULL OR TRIM(product_code) = ''
   OR product_code NOT IN (SELECT code FROM product_codes);

-- name: rule_timezone
-- Where UTC is carried: the local stamp is not UTC plus the hub offset.
-- Where it is not: the terminal received the freight before the aircraft arrived.
SELECT DISTINCT awb_id FROM event_feed
WHERE ts_utc IS NOT NULL AND ts_local <> ts_utc + to_hours($offset_h)
UNION
SELECT awb_id FROM feed_wide WHERE utc_missing AND rcf_ts < arr_ts;

-- name: repaired
-- Safe repairs, then quarantine for what cannot be repaired safely.
-- Repairs: keep the first message of a resent AWB; re-stamp local time from UTC where UTC is carried; where it is
-- not, move RCF and NFD forward by the offset only when that puts the freight back after the arrival.
-- Quarantine: missing RCF or NFD, NFD before RCF, weight mismatch, unknown product, and any stamp still out of order.
CREATE OR REPLACE TABLE awb_repaired AS
WITH fixed AS (
    SELECT f.*,
           f.utc_missing AND f.rcf_ts < f.arr_ts AS shift_terminal,
           COALESCE(f.arr_utc + to_hours($offset_h), f.arr_ts) AS arr_fix,
           CASE WHEN f.rcf_utc IS NOT NULL THEN f.rcf_utc + to_hours($offset_h)
                WHEN f.utc_missing AND f.rcf_ts < f.arr_ts THEN f.rcf_ts + to_hours($offset_h)
                ELSE f.rcf_ts END AS rcf_fix,
           CASE WHEN f.nfd_utc IS NOT NULL THEN f.nfd_utc + to_hours($offset_h)
                WHEN f.utc_missing AND f.rcf_ts < f.arr_ts THEN f.nfd_ts + to_hours($offset_h)
                ELSE f.nfd_ts END AS nfd_fix,
           COALESCE(f.dlv_utc + to_hours($offset_h), f.dlv_ts) AS dlv_fix
    FROM feed_wide f
)
SELECT x.awb_id, x.flight_key, x.flight, x.carrier, x.flight_type, x.region, pc.product, x.product_code,
       x.handling_unit, x.pieces, x.weight_kg, x.weight_checked_kg, x.sched_arr,
       x.arr_fix AS arr_ts, x.rcf_fix AS rcf_ts, x.nfd_fix AS nfd_ts, x.dlv_fix AS dlv_ts,
       (x.arr_fix <> x.arr_ts OR x.rcf_fix <> x.rcf_ts OR x.nfd_fix <> x.nfd_ts OR x.dlv_fix <> x.dlv_ts) AS restamped,
       CASE
           WHEN pc.product IS NULL THEN 'unknown product'
           WHEN x.rcf_fix IS NULL AND x.arr_fix < $cutoff - to_hours($grace_h) THEN 'missing RCF'
           WHEN x.nfd_fix IS NULL AND x.arr_fix < $cutoff - to_hours($grace_h) THEN 'missing NFD'
           WHEN x.nfd_fix < x.rcf_fix THEN 'NFD before RCF'
           WHEN x.rcf_fix < x.arr_fix THEN 'RCF before arrival'
           WHEN ABS(x.weight_checked_kg - x.weight_kg) > $tol * x.weight_kg
                AND ABS(x.weight_checked_kg - x.weight_kg) >= $tol_kg THEN 'weight mismatch'
       END AS quarantine_reason
FROM fixed x
LEFT JOIN product_codes pc ON pc.code = x.product_code;

-- name: raw_wide
-- What a first query on the feed returns: every AWB record as received, local stamps taken at face value.
CREATE OR REPLACE VIEW raw_wide AS
SELECT a.awb_id, a.msg_id, a.flight_key, a.carrier, a.flight_type, a.region, pc.product, a.product_code,
       a.handling_unit, a.pieces, a.weight_kg, a.sched_arr,
       MIN(e.ts_local) FILTER (WHERE e.milestone = 'ARR') AS arr_ts,
       MIN(e.ts_local) FILTER (WHERE e.milestone = 'RCF') AS rcf_ts,
       MIN(e.ts_local) FILTER (WHERE e.milestone = 'NFD') AS nfd_ts,
       MIN(e.ts_local) FILTER (WHERE e.milestone = 'DLV') AS dlv_ts
FROM awb_feed a
LEFT JOIN product_codes pc ON pc.code = a.product_code
LEFT JOIN event_feed e ON e.awb_id = a.awb_id
GROUP BY ALL;
