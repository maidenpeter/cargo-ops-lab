"""The schedule breaks: a share of flights bunch into arrival waves and volume falls.

Four policies meet the same disrupted arrivals: the legacy roster, the roster optimized on the normal timetable,
a roster re-optimized on the disrupted schedule, and the normal-timetable roster plus a call-in pool.
The risk model trained on normal months is also scored on the disrupted arrivals.
"""
from __future__ import annotations

import duckdb
import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, roc_auc_score

from lab import config as C
from lab import kpis, model
from lab import roster as R
from lab import schedule as S
from lab import terminal as T

from lab.scenarios import POLICIES, key, scenarios  # noqa: E402,F401


def bundles(flights: pd.DataFrame, awbs: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> dict[str, R.Bundle]:
    """One bundle per scenario. The disruption applies inside the evaluation window only; the warm-up week is normal."""
    out = {}
    warm_start = (start - pd.Timedelta(days=C.load()["roster_opt"]["warmup_days"] + 1)).normalize()
    win = (flights["sched_arr"] >= start) & (flights["sched_arr"] < end)
    for share, vol in scenarios():
        f_in, a_in = flights[win], awbs[awbs["flight_key"].isin(flights.loc[win, "flight_key"])]
        f_d, a_d = S.disrupt(f_in.reset_index(drop=True), a_in.reset_index(drop=True), share, vol)
        pre_f = flights[(flights["sched_arr"] >= warm_start) & (flights["sched_arr"] < start)]
        pre_a = awbs[awbs["flight_key"].isin(pre_f["flight_key"])]
        f_all = pd.concat([pre_f, f_d], ignore_index=True)
        a_all = pd.concat([pre_a, a_d], ignore_index=True).sort_values(["arr", "awb_id"]).reset_index(drop=True)
        out[key(share, vol)] = R.make_bundle(key(share, vol), f_all, a_all, start, end)
    return out


def evaluate_policies(runner: R.Runner, legacy: np.ndarray, static: np.ndarray, seeds: list[int]) -> dict:
    flex = C.load()["flex"]
    names = [key(s, v) for s, v in scenarios()]
    tasks = []
    for n in names:
        for seed in seeds:
            tasks += [(n, legacy, seed, None), (n, static, seed, None), (n, static, seed, flex)]
    res = runner.map(tasks)
    out: dict = {}
    for t, r in zip(tasks, res):
        pol = "legacy" if t[1] is legacy else ("flex" if t[3] else "static")
        out.setdefault((t[0], pol), []).append(r)
    return out


def replan(runner: R.Runner, legacy: np.ndarray, seeds: list[int], multiplier: float, passes: int) -> dict:
    """Re-optimize the roster on each disrupted schedule, all scenarios batched through the pool together."""
    names = [key(s, v) for s, v in scenarios()]
    base = {n: legacy.copy() for n in names}
    rosters, grids = {}, {}
    for _ in range(passes):
        tasks = {n: R.grid_tasks(n, base[n], legacy, seeds) for n in names}
        flat = [t for n in names for t in tasks[n]]
        res = runner.map([t[:4] for t in flat])
        i = 0
        for n in names:
            k = len(tasks[n])
            g = R.grid_table(tasks[n], res[i:i + k], runner.bundles[n].weeks, base[n])
            i += k
            rosters[n], _ = R.solve(g, legacy, R.budget(legacy, multiplier))
            grids[n] = g
            base[n] = rosters[n]
    tasks = [(n, rosters[n], seed, None) for n in names for seed in seeds]
    res = runner.map(tasks)
    evals: dict = {}
    for t, r in zip(tasks, res):
        evals.setdefault((t[0], "replanned"), []).append(r)
    return {"rosters": rosters, "evals": evals, "grids": grids}


def drift(bundle: R.Bundle, legacy: np.ndarray, fitted, bins: int) -> tuple[dict, pd.DataFrame]:
    """Score the normal-month model on one scenario simulated under the legacy roster (the roster it learned from)."""
    pt = S.process_times(bundle.awbs, bundle.t0, 0)
    sim = T.simulate(pt, bundle.t0.weekday(), legacy, 0, bundle.horizon)
    nfd = sim.rcf + pt["doc"]
    a = bundle.awbs.copy()
    to_ts = lambda m: (bundle.t0 + pd.to_timedelta(m, unit="min")).floor("min")  # noqa: E731
    a["arr_ts"] = a["arr"].dt.floor("min")
    a["rcf_ts"] = to_ts(sim.rcf)
    a["nfd_ts"] = to_ts(nfd)
    a["dlv_ts"] = pd.NaT
    a["sched_arr"] = a["sched_arr"].dt.floor("min")
    a = a.drop(columns=["arr"])
    con = duckdb.connect()
    kpis.register_reference(con)
    con.register("sim_src", a)
    con.register("sim_flights", bundle.flights[["sched_arr", "n_awbs"]])
    r = R.roster_frame(legacy)[["weekday", "shift", "headcount"]]
    con.register("sim_roster", r)
    kpis.prepare(con, "sim_awb", "sim_src")
    feats = model.features(con, "sim_awb", "sim_flights", "sim_roster")
    con.close()
    feats = feats[feats["arr_ts"] >= bundle.t0 + pd.to_timedelta(bundle.win_start, unit="min")]
    p = fitted.predict_proba(feats[model.FEATURES])[:, 1]
    y = feats["late"].to_numpy()
    cal = model.calibration(y, p, bins)
    m = {"n": len(y), "late_rate": y.mean(), "mean_pred": p.mean(),
         "auc": roc_auc_score(y, p) if 0 < y.sum() < len(y) else np.nan, "brier": brier_score_loss(y, p),
         "catch_top": model.capture(y, p, C.load()["model"]["expedite_share"])[0]}
    return m, cal


def arrival_profile(bundles: dict[str, R.Bundle]) -> pd.DataFrame:
    """Average AWBs arriving per hour of the day, in the evaluation window, for each scenario."""
    rows = []
    for n, b in bundles.items():
        arr = b.awbs["arr"]
        w = arr >= b.t0 + pd.to_timedelta(b.win_start, unit="min")
        days = (b.win_end - b.win_start) / 1440
        cnt = arr[w].dt.hour.value_counts().reindex(range(24), fill_value=0) / days
        for h, v in cnt.items():
            rows.append({"scenario": n, "hour": h, "awbs_per_day": v})
    return pd.DataFrame(rows)
