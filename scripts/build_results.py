"""Build every result the app reads. Run locally; the outputs in data/ are committed.

    python scripts/build_results.py            # everything, then the tests
    python scripts/build_results.py --no-tests
    python scripts/build_results.py --finalize # only headline.json, README.md and the tests, from the stored results
    python scripts/build_results.py --skip-sims  # everything except the roster and disruption simulations (kept as stored)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import duckdb  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from lab import config as C  # noqa: E402
from lab import defects as D  # noqa: E402
from lab import disruption as X  # noqa: E402
from lab import headline, kpis, model, readme  # noqa: E402
from lab import roster as R  # noqa: E402
from lab import schedule as S  # noqa: E402
from lab import terminal as T  # noqa: E402

DQ_RULES = {"missing_rcf": "Missing RCF", "missing_nfd": "Missing NFD", "out_of_sequence": "NFD before RCF",
            "duplicate_resend": "Duplicate resend", "weight_mismatch": "Weight mismatch",
            "invalid_product": "Invalid product code", "timezone": "Time zone stamp"}

_T0 = time.time()


def log(msg: str) -> None:
    print(f"[{time.time() - _T0:6.1f}s] {msg}", flush=True)


def save(df: pd.DataFrame, name: str, folder: Path = C.DATA) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    df.to_parquet(folder / f"{name}.parquet", index=False, compression="zstd")


# ---------------------------------------------------------------- 1. history
def history():
    cfg = C.load()
    flights = S.build_flights(C.start(), C.cutoff(), S.rng_for(1))
    awbs = S.build_awbs(flights, S.rng_for(2))
    t0 = C.start() - pd.Timedelta(days=1)
    pt = S.process_times(awbs, t0, 0)
    horizon = (C.cutoff() - t0).total_seconds() / 60 + cfg["window"]["run_on_days"] * 1440
    legacy = C.legacy_roster()
    sim = T.simulate(pt, t0.weekday(), legacy, 0, horizon)
    nfd = sim.rcf + pt["doc"]
    wide = D.event_log(awbs, sim.rcf, nfd, t0)
    names = cfg["shifts"]["names"]
    sh = sim.shifts.copy()
    sh["start_ts"] = t0 + pd.to_timedelta(sh["start_min"], unit="min")
    sh["end_ts"] = sh["start_ts"] + pd.Timedelta(hours=cfg["shifts"]["hours"])
    sh["shift_name"] = sh["shift"].map(dict(enumerate(names)))
    sh = sh[(sh["start_ts"] >= C.start() - pd.Timedelta(hours=2)) & (sh["start_ts"] < C.cutoff())]
    sh = sh[["start_ts", "end_ts", "weekday", "shift", "shift_name", "rostered", "present", "busy_min", "kg", "awbs"]]
    log(f"history: {len(flights):,} flights, {len(awbs):,} AWBs simulated")
    return flights, awbs, wide, sh.reset_index(drop=True)


# ---------------------------------------------------------------- 2. data quality
def data_quality(con, wide: pd.DataFrame):
    awb_clean_feed, ev_clean_feed = D.to_feeds(wide)
    truth = D.assign(wide)
    awb_dirty, ev_dirty = D.inject(awb_clean_feed, ev_clean_feed, truth)
    awb_tz, ev_tz = D.inject(awb_clean_feed, ev_clean_feed, truth, only=["timezone"])

    def load(awb, ev):
        con.register("awb_feed", awb)
        con.register("event_feed", ev)
        kpis.run(con, "dq_rules.sql", "feed_wide")

    def rule_hits() -> dict[str, set]:
        return {r: set(kpis.run(con, "dq_rules.sql", f"rule_{r}")["awb_id"]) for r in DQ_RULES}

    # the rules on the clean feeds must flag nothing
    load(awb_clean_feed, ev_clean_feed)
    clean_hits = rule_hits()

    # time zone defect alone, taken at face value
    load(awb_tz, ev_tz)
    kpis.run(con, "dq_rules.sql", "raw_wide")
    con.execute("CREATE OR REPLACE TABLE tz_only_src AS SELECT * FROM raw_wide")

    # the dirty feeds
    load(awb_dirty, ev_dirty)
    hits = rule_hits()
    fw = con.execute("""SELECT f.awb_id, f.product_code, f.weight_kg, f.weight_checked_kg, f.arr_ts, f.rcf_ts, f.nfd_ts,
                               f.arr_utc, f.rcf_utc, f.nfd_utc, n.records
                        FROM feed_wide f JOIN (SELECT awb_id, COUNT(*) AS records FROM awb_feed GROUP BY 1) n USING (awb_id)
                     """).df().set_index("awb_id")
    examples = []
    for r in DQ_RULES:
        caught = sorted(hits[r] & set(truth.loc[truth["defect"] == r, "awb_id"]))
        if r == "timezone":
            with_utc = [i for i in caught if pd.notna(fw.loc[i, "arr_utc"])][:2]
            no_utc = [i for i in caught if pd.isna(fw.loc[i, "arr_utc"])][:1]
            caught = with_utc + no_utc
        for i in caught[:3]:
            examples.append({"rule": r, "label": DQ_RULES[r], "awb_id": i, **fw.loc[i].to_dict()})
    save(pd.DataFrame(examples), "dq_examples")
    kpis.run(con, "dq_rules.sql", "raw_wide")
    con.execute("CREATE OR REPLACE TABLE raw_src AS SELECT * FROM raw_wide")
    kpis.run(con, "dq_rules.sql", "repaired")
    flagged = pd.DataFrame({"awb_id": sorted(set().union(*hits.values()))})
    con.register("flagged_df", flagged)
    con.execute("""CREATE OR REPLACE TABLE qonly_src AS
                   SELECT f.*, pc.product FROM feed_wide f LEFT JOIN product_codes pc ON pc.code = f.product_code
                   WHERE f.awb_id NOT IN (SELECT awb_id FROM flagged_df)""")
    con.execute("""CREATE OR REPLACE TABLE awb_clean_src AS
                   SELECT awb_id, flight_key, flight, carrier, flight_type, region, product, handling_unit, pieces,
                          weight_kg, sched_arr, arr_ts, rcf_ts, nfd_ts, dlv_ts
                   FROM awb_repaired WHERE quarantine_reason IS NULL""")
    con.execute("CREATE OR REPLACE TABLE feed_src AS SELECT f.*, pc.product FROM feed_wide f "  # the feed as received
                "LEFT JOIN product_codes pc ON pc.code = f.product_code")

    truth_cols = ["awb_id", "flight_key", "flight", "carrier", "flight_type", "region", "product", "handling_unit",
                  "pieces", "weight_kg", "sched_arr", "arr_ts", "rcf_ts", "nfd_ts", "dlv_ts"]
    con.register("truth_df", wide[truth_cols])
    con.execute("CREATE OR REPLACE TABLE truth_src AS SELECT * FROM truth_df")

    con.execute("CREATE OR REPLACE TABLE truth_kept_src AS SELECT * FROM truth_src "
                "WHERE awb_id IN (SELECT awb_id FROM awb_clean_src)")
    versions = {"Truth": "truth_src", "Raw feed": "raw_src", "Quarantine only": "qonly_src", "Repaired": "awb_clean_src",
                "Time zone defect only": "tz_only_src", "Truth, kept AWBs": "truth_kept_src"}
    rows = []
    for label, src in versions.items():
        v = "v_" + src
        kpis.prepare(con, v, src)
        r = kpis.kpi(con, "nfd_on_time", v).iloc[0]
        rows.append({"version": label, "rows": int(con.execute(f"SELECT COUNT(*) FROM {src}").fetchone()[0]),
                     "scored": int(r["scored"]), "on_time": float(r["value"])})
    dq_versions = pd.DataFrame(rows)

    # scorecard against the injected truth
    sc = []
    for r, label in DQ_RULES.items():
        injected = set(truth.loc[truth["defect"] == r, "awb_id"])
        tp = len(hits[r] & injected)
        sc.append({"rule": r, "label": label, "flagged": len(hits[r]), "injected": len(injected), "true_pos": tp,
                   "precision": tp / len(hits[r]) if hits[r] else np.nan,
                   "recall": tp / len(injected) if injected else np.nan,
                   "flagged_on_clean": len(clean_hits[r])})
    scorecard = pd.DataFrame(sc)

    rep = con.execute("SELECT * FROM awb_repaired").df()
    save(rep.loc[rep["quarantine_reason"].notna(), ["awb_id", "quarantine_reason"]], "dq_quarantine")
    outcome = (rep.assign(reason=rep["quarantine_reason"].fillna("kept"))
               .groupby("reason").size().rename("awbs").reset_index())
    # how many re-stamped AWBs came back exactly to the truth
    rs = rep[rep["restamped"].fillna(False) & rep["quarantine_reason"].isna()][["awb_id", "arr_ts", "rcf_ts", "nfd_ts"]]
    tw = wide.set_index("awb_id").loc[rs["awb_id"], ["arr_ts", "rcf_ts", "nfd_ts"]].reset_index()
    exact = (rs.set_index("awb_id")[["arr_ts", "rcf_ts", "nfd_ts"]].eq(tw.set_index("awb_id")) |
             (rs.set_index("awb_id")[["arr_ts", "rcf_ts", "nfd_ts"]].isna() & tw.set_index("awb_id").isna())).all(axis=1)
    tz = truth[truth["defect"] == "timezone"]
    missed = tz[~tz["awb_id"].isin(hits["timezone"])]
    repair = {"restamped": int(len(rs)), "restamped_exact": int(exact.sum()),
              "tz_missed": int(len(missed)),
              "tz_missed_arr_no_utc": int(((missed["variant"] == "arr_stamp") & missed["manual_channel"]).sum()),
              "tz_missed_terminal_no_utc": int(((missed["variant"] == "terminal_stamps") & missed["manual_channel"]).sum()),
              "manual_share": float(truth["manual_channel"].mean())}

    # completeness on the feed as received and after cleaning
    kpis.prepare(con, "v_feed", "feed_src")
    comp = {"feed": float(kpis.kpi(con, "completeness", "v_feed")["value"].iloc[0]),
            "cleaned": float(kpis.kpi(con, "completeness", "v_awb_clean_src")["value"].iloc[0]),
            "truth": float(kpis.kpi(con, "completeness", "v_truth_src")["value"].iloc[0])}

    save(awb_clean_feed, "awb_master", C.LOGS)
    save(ev_clean_feed, "events_clean", C.LOGS)
    save(awb_dirty, "awb_feed", C.LOGS)
    save(ev_dirty, "event_feed", C.LOGS)
    save(truth, "dq_truth", C.LOGS)
    log(f"data quality: {len(flagged):,} AWBs flagged, raw {dq_versions.set_index('version').on_time['Raw feed']:.4f} "
        f"vs truth {dq_versions.set_index('version').on_time['Truth']:.4f}")
    return scorecard, dq_versions, outcome, repair, comp


# ---------------------------------------------------------------- 3. KPIs on the cleaned data
def kpi_tables(con, sh: pd.DataFrame, comp: dict):
    con.register("shift_df", sh)
    con.execute("CREATE OR REPLACE TABLE shift_log AS SELECT * FROM shift_df")
    con.execute("CREATE OR REPLACE TABLE awb_clean AS SELECT * FROM awb_clean_src")
    kpis.prepare(con, "awb", "awb_clean")
    ot = kpis.kpi(con, "nfd_on_time").iloc[0]
    ht = kpis.kpi(con, "handler_time").iloc[0]
    ct = kpis.kpi(con, "customer_time").iloc[0]
    dw = kpis.kpi(con, "dwell_split").iloc[0]
    tot = con.execute("SELECT COUNT(*), SUM(weight_kg) / 1000 FROM awb").fetchone()
    tru = con.execute("SELECT COUNT(*), SUM(weight_kg) / 1000 FROM truth_src").fetchone()
    seg = con.execute("""SELECT AVG(epoch(rcf_ts - arr_ts)) / 3600, AVG(epoch(nfd_ts - rcf_ts)) / 3600,
                                AVG(epoch(dlv_ts - nfd_ts)) / 3600
                         FROM awb WHERE dlv_ts IS NOT NULL AND nfd_ts < $cutoff - INTERVAL 7 DAY""",
                      {"cutoff": C.cutoff().to_pydatetime()}).fetchone()
    summary = pd.DataFrame([
        ("awbs_total", "AWBs landed in the window", tru[0]), ("tonnes_total", "Tonnes landed in the window", tru[1]),
        ("awbs", "AWBs after cleaning", tot[0]), ("tonnes", "Tonnes after cleaning", tot[1]),
        ("arr_to_rcf_mean_h", "Mean hours, ARR to RCF", seg[0]), ("rcf_to_nfd_mean_h", "Mean hours, RCF to NFD", seg[1]),
        ("nfd_to_dlv_mean_h", "Mean hours, NFD to DLV", seg[2]),
        ("scored", "AWBs scored for on-time", ot["scored"]), ("nfd_on_time", "NFD on time %", ot["value"]),
        ("handler_p50_h", "Handler time p50, hours", ht["p50_h"]), ("handler_p90_h", "Handler time p90, hours", ht["p90_h"]),
        ("customer_p50_h", "Customer time p50, hours", ct["p50_h"]), ("customer_p90_h", "Customer time p90, hours", ct["p90_h"]),
        ("handler_share", "Handler share of dwell", dw["handler_share"]), ("dwell_mean_h", "Mean dwell, hours", dw["dwell_mean_h"]),
        ("late_per_1000", "Late per 1,000 AWBs", kpis.kpi(con, "late_per_1000")["value"].iloc[0]),
        ("completeness_feed", "Data completeness, feed as received", comp["feed"]),
        ("completeness_cleaned", "Data completeness, after cleaning", comp["cleaned"]),
    ], columns=["kpi", "label", "value"])
    by = []
    for dim, label in (("product", "Product"), ("carrier", "Carrier"), ("arr_shift", "Arrival shift"),
                       ("arr_hour", "Arrival hour"), ("handling_unit", "Handling unit"), ("flight_type", "Aircraft type")):
        t = kpis.kpi(con, "nfd_on_time_by", dim=dim)
        t.insert(0, "dim", label)
        t["level"] = t["level"].astype(str)
        by.append(t)
    lp = con.execute("""SELECT product AS level, 1000.0 * COUNT(*) FILTER (WHERE NOT COALESCE(nfd_ts <= due_ts, FALSE)) / COUNT(*) AS value
                        FROM awb WHERE due_ts < $cutoff GROUP BY 1""", {"cutoff": C.cutoff().to_pydatetime()}).df()
    ht_p = con.execute("""SELECT product, quantile_cont(epoch(nfd_ts - arr_ts) / 3600, 0.5) AS p50_h,
                                 quantile_cont(epoch(nfd_ts - arr_ts) / 3600, 0.9) AS p90_h, ANY_VALUE(sla_h) AS sla_h
                          FROM awb WHERE nfd_ts IS NOT NULL GROUP BY 1""").df()
    ready = con.execute("""SELECT product, AVG(epoch(rcf_ts - arr_ts) / 60) AS arr_to_rcf_min,
                                  AVG(epoch(nfd_ts - rcf_ts) / 60) AS rcf_to_nfd_min
                           FROM awb WHERE nfd_ts IS NOT NULL GROUP BY 1""").df()
    out = {
        "kpi_summary": summary,
        "kpi_by": pd.concat(by, ignore_index=True),
        "late_per_1000_by_product": lp,
        "handler_time_by_product": ht_p.merge(ready, on="product"),
        "heatmap": kpis.kpi(con, "on_time_hour_weekday"),
        "monthly": kpis.kpi(con, "monthly"),
        "time_split": kpis.kpi(con, "time_split_by_product"),
        "throughput": kpis.kpi(con, "throughput"),
        "backlog": kpis.kpi(con, "backlog_at_shift_end"),
    }
    for k, v in out.items():
        save(v, k)
    kd = kpis.dictionary()
    kd.to_csv(C.DATA / "kpi_dictionary.csv", index=False)
    # what the app's live filters and the shipment lookup query; the full cleaned table is rebuilt from the logs
    awb = con.execute("""SELECT awb_id, flight, carrier, flight_type, region, product, handling_unit, pieces, weight_kg,
                                sched_arr, arr_ts, rcf_ts, nfd_ts, dlv_ts FROM awb ORDER BY arr_ts, awb_id""").df()
    for c in ["flight", "carrier", "flight_type", "region", "product", "handling_unit"]:
        awb[c] = awb[c].astype("category")
    save(awb, "awb_clean")
    save(sh, "shift_log")
    log(f"KPIs: on time {ot['value']:.4f}, handler p90 {ht['p90_h']:.2f} h")


# ---------------------------------------------------------------- 4. risk model
def risk_model(con, flights: pd.DataFrame):
    con.register("flights_df", flights[["flight_key", "sched_arr", "n_awbs"]])
    con.execute("CREATE OR REPLACE TABLE flights_hist AS SELECT * FROM flights_df")
    con.register("legacy_df", R.roster_frame(C.legacy_roster())[["weekday", "shift", "headcount"]])
    con.execute("CREATE OR REPLACE TABLE roster_legacy AS SELECT * FROM legacy_df")
    feats = model.features(con, "awb", "flights_hist", "roster_legacy")
    res = model.fit_and_score(feats)
    save(res["metrics"], "model_metrics")
    save(res["calibration"], "model_calibration")
    save(res["predictions"], "model_predictions")
    save(res["importance"], "model_importance")
    save(res["capture_curve"], "model_capture")
    meta = {"chosen": res["chosen"], "features": ", ".join(model.FEATURES),
            **{f"n_{k}": str(v) for k, v in res["sizes"].items()},
            **{f"{k}_from": str(v[0].date()) for k, v in res["months"].items()},
            **{f"{k}_to": str(v[1].date()) for k, v in res["months"].items()}}
    save(pd.DataFrame({"key": list(meta), "value": list(meta.values())}), "model_meta")
    t = res["metrics"].query("split == 'test'").set_index("model")
    log(f"model: chosen {res['chosen']}, test AUC {t['auc'].round(3).to_dict()}")
    return res["models"][res["chosen"]]


# ---------------------------------------------------------------- 5 and 6. roster and disruption
def roster_and_disruption(flights, awbs, fitted):
    cfg = C.load()
    o = cfg["roster_opt"]
    start = pd.Timestamp(cfg["split"]["valid_end"]) + pd.Timedelta(days=1)
    end = C.cutoff()
    legacy = C.legacy_roster()
    seeds = list(range(o["seeds"]))
    dseeds = seeds  # the same seeds, so re-planning with no disruption reproduces the plan exactly
    base = R.make_bundle("base", flights, awbs, start, end)
    dis_b = X.bundles(flights, awbs, start, end)
    runner = R.Runner({"base": base, **dis_b})
    try:
        opt = R.optimize(runner, "base", legacy, seeds, o["budget_multiplier"], o["passes"])
        static = opt["roster"]
        save(opt["grids"], "roster_grid")
        log(f"roster: optimized\n{static.T}")

        ev = runner.map([("base", legacy, s, None) for s in seeds] + [("base", static, s, None) for s in seeds])
        rows, cells = [], []
        for pol, rs in (("legacy", ev[:len(seeds)]), ("optimized", ev[len(seeds):])):
            rows.append({"policy": pol, **R.summarize(rs, base.weeks)})
            co = R.cell_on_time(rs)
            cells += [{"policy": pol, "weekday": d, "shift": s, "on_time": co[d, s]} for d in range(7) for s in range(3)]
        rev = pd.DataFrame(rows)
        pred = R.predicted(opt["grid"], static)
        rev.loc[rev["policy"] == "optimized", "grid_late_per_week"] = pred["late_per_week"]
        rev.loc[rev["policy"] == "optimized", "grid_on_time"] = pred["on_time"]
        save(rev, "roster_eval")
        save(pd.DataFrame(cells), "roster_cells")
        save(pd.concat([R.roster_frame(legacy, policy="legacy"), R.roster_frame(static, policy="optimized")]), "rosters")

        fr_rosters = {m: R.solve(opt["grid"], legacy, R.budget(legacy, m), labor=False)[0] for m in o["frontier_multipliers"]}
        tasks = [("base", fr_rosters[m], s, None) for m in o["frontier_multipliers"] for s in seeds]
        res = runner.map(tasks)
        fr = []
        for i, m in enumerate(o["frontier_multipliers"]):
            sm = R.summarize(res[i * len(seeds):(i + 1) * len(seeds)], base.weeks)
            fr.append({"multiplier": m, "budget_hours": R.budget(legacy, m), **sm})
        save(pd.DataFrame(fr), "frontier")
        log("roster: frontier done")

        pol = X.evaluate_policies(runner, legacy, static, dseeds)
        rp = X.replan(runner, legacy, dseeds, o["budget_multiplier"], o["passes"])
        pol.update(rp["evals"])
        rows = []
        for (scen, p), rs in pol.items():
            share, vol = next((s, v) for s, v in X.scenarios() if X.key(s, v) == scen)
            rows.append({"scenario": scen, "share": share, "volume_change": vol, "policy": p,
                         **R.summarize(rs, runner.bundles[scen].weeks)})
        save(pd.DataFrame(rows), "disruption")
        save(pd.concat([R.roster_frame(r, scenario=n) for n, r in rp["rosters"].items()]), "disruption_rosters")
        log("disruption: policies done")
    finally:
        runner.close()

    drift_rows, drift_cal = [], []
    for n, b in dis_b.items():
        m, cal = X.drift(b, legacy, fitted, cfg["model"]["calibration_bins"])
        drift_rows.append({"scenario": n, **m})
        cal.insert(0, "scenario", n)
        drift_cal.append(cal)
    save(pd.DataFrame(drift_rows), "drift")
    save(pd.concat(drift_cal, ignore_index=True), "drift_calibration")
    save(X.arrival_profile(dis_b), "arrival_profile")
    log("disruption: model drift done")


# ---------------------------------------------------------------- 7. tests
def run_tests() -> None:
    xml = C.DATA / "_pytest.xml"
    subprocess.run([sys.executable, "-m", "pytest", "-q", f"--junitxml={xml}"], cwd=ROOT)
    rows = []
    for case in ET.parse(xml).getroot().iter("testcase"):
        status = "failed" if case.find("failure") is not None or case.find("error") is not None else (
            "skipped" if case.find("skipped") is not None else "passed")
        rows.append({"test": case.get("name"), "file": (case.get("classname") or "").split(".")[-1],
                     "status": status, "seconds": float(case.get("time") or 0)})
    pd.DataFrame(rows).to_csv(C.DATA / "test_results.csv", index=False)
    xml.unlink(missing_ok=True)
    log(f"tests: {sum(r['status'] == 'passed' for r in rows)} of {len(rows)} passed")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-tests", action="store_true")
    ap.add_argument("--finalize", action="store_true")
    ap.add_argument("--skip-sims", action="store_true")
    args = ap.parse_args()
    C.DATA.mkdir(exist_ok=True)
    if args.finalize:
        h = headline.compute()
        headline.write(h)
        readme.write(h)
        log("headline: " + h["sentences"]["headline"])
        if not args.no_tests:
            run_tests()
        return
    flights, awbs, wide, sh = history()
    save(flights, "flights", C.LOGS)
    save(wide, "events_wide_truth", C.LOGS)
    con = duckdb.connect()
    kpis.register_reference(con)
    scorecard, versions, outcome, repair, comp = data_quality(con, wide)
    save(scorecard, "dq_scorecard")
    save(versions, "dq_versions")
    save(outcome, "dq_outcome")
    (C.DATA / "dq_repair.json").write_text(json.dumps(repair, indent=2), encoding="utf-8")
    kpi_tables(con, sh, comp)
    fitted = risk_model(con, flights)
    con.close()
    if not args.skip_sims:
        roster_and_disruption(flights, awbs, fitted)
    h = headline.compute()
    headline.write(h)
    readme.write(h)
    log("headline: " + h["sentences"]["headline"])
    if not args.no_tests:
        run_tests()


if __name__ == "__main__":
    main()
