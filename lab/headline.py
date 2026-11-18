"""Every number the README and the teaser cards quote, computed from the result files alone.

The sentences are worded from the numbers: where a result goes the other way from the expectation, the wording
follows the result.
"""
from __future__ import annotations

import json

import pandas as pd

from lab import config as C


def _read(name: str) -> pd.DataFrame:
    return pd.read_parquet(C.DATA / f"{name}.parquet")


def pct(x: float, d: int = 1) -> str:
    return f"{100 * x:.{d}f}%"


def compute() -> dict:
    cfg = C.load()
    k = _read("kpi_summary").set_index("kpi")["value"]
    dq = _read("dq_versions").set_index("version")["on_time"]
    m = _read("model_metrics")
    chosen = _read("model_meta").set_index("key")["value"]["chosen"]
    mt = m[(m["model"] == chosen) & (m["split"] == "test")].iloc[0]
    rev = _read("roster_eval").set_index("policy")
    dis = _read("disruption").set_index(["scenario", "policy"])
    drift = _read("drift").set_index("scenario")

    share = cfg["disruption"]["headline_share"]
    h_key = f"s{round(share * 100):02d}_v00"
    base_key = "s00_v00"
    hv = cfg["disruption"]["headline_volume"]
    v_key = f"s{round(share * 100):02d}_v{round(-hv * 100):02d}"

    st, rp = dis.loc[(h_key, "static")], dis.loc[(h_key, "replanned")]
    lg, fx = dis.loc[(h_key, "legacy")], dis.loc[(h_key, "flex")]
    base_static = dis.loc[(base_key, "static")]
    vf = dis.loc[(v_key, "static")]
    extra = rp["staff_hours_per_week"] - st["staff_hours_per_week"]

    h = {
        "awbs": int(k["awbs"]), "tonnes": float(k["tonnes"]), "window_start": cfg["window"]["start"],
        "awbs_total": int(k["awbs_total"]), "tonnes_total": float(k["tonnes_total"]),
        "cutoff": cfg["window"]["cutoff"],
        "nfd_on_time": float(k["nfd_on_time"]), "handler_p50_h": float(k["handler_p50_h"]),
        "handler_p90_h": float(k["handler_p90_h"]), "customer_p50_h": float(k["customer_p50_h"]),
        "customer_p90_h": float(k["customer_p90_h"]), "late_per_1000": float(k["late_per_1000"]),
        "handler_share_of_dwell": float(k["handler_share"]),
        "dq_truth": float(dq["Truth"]), "dq_raw": float(dq["Raw feed"]), "dq_quarantine": float(dq["Quarantine only"]),
        "dq_repaired": float(dq["Repaired"]), "dq_tz_only": float(dq["Time zone defect only"]),
        "tz_points": float(100 * (dq["Time zone defect only"] - dq["Truth"])),
        "model": chosen, "model_auc": float(mt["auc"]), "model_brier": float(mt["brier"]),
        "model_late_rate": float(mt["late_rate"]), "expedite_share": cfg["model"]["expedite_share"],
        "model_catch": float(mt["catch_top"]), "model_late_rate_top": float(mt["late_rate_top"]),
        "legacy_on_time": float(rev.loc["legacy", "on_time"]), "opt_on_time": float(rev.loc["optimized", "on_time"]),
        "legacy_late_week": float(rev.loc["legacy", "late_per_week"]), "opt_late_week": float(rev.loc["optimized", "late_per_week"]),
        "legacy_hours_week": float(rev.loc["legacy", "staff_hours_per_week"]),
        "opt_hours_week": float(rev.loc["optimized", "staff_hours_per_week"]),
        "legacy_cost_week": float(rev.loc["legacy", "total_cost_per_week"]),
        "opt_cost_week": float(rev.loc["optimized", "total_cost_per_week"]),
        "dis_share": share, "dis_scenario": h_key,
        "dis_legacy": float(lg["on_time"]), "dis_static": float(st["on_time"]), "dis_replanned": float(rp["on_time"]),
        "dis_flex": float(fx["on_time"]), "dis_extra_hours_week": float(extra),
        "dis_flex_hours_week": float(fx["flex_hours_per_week"]),
        "base_static": float(base_static["on_time"]), "base_static_late_week": float(base_static["late_per_week"]),
        "vol_scenario": v_key, "vol_change": float(hv),
        "vol_static": float(vf["on_time"]), "vol_static_late_week": float(vf["late_per_week"]),
        "drift_auc_base": float(drift.loc[base_key, "auc"]), "drift_auc": float(drift.loc[h_key, "auc"]),
        "drift_pred": float(drift.loc[h_key, "mean_pred"]), "drift_actual": float(drift.loc[h_key, "late_rate"]),
    }
    h["sentences"] = sentences(h)
    return h


def sentences(h: dict) -> dict:
    share = round(100 * h["dis_share"])
    extra = h["dis_extra_hours_week"]
    if abs(extra) < 0.5:
        cost = "with the same staff hours"
    elif extra > 0:
        cost = f"for {extra:,.0f} more staff hours a week"
    else:
        cost = f"with {-extra:,.0f} fewer staff hours a week"
    if h["dis_replanned"] > h["dis_static"]:
        replan = f"Re-planning from the live schedule gets back to {pct(h['dis_replanned'])} {cost}."
    else:
        replan = (f"Re-planning from the live schedule does not beat it: {pct(h['dis_replanned'])} on time {cost}.")
    headline = (f"When {share}% of arrivals bunch into waves, the roster built on the normal timetable delivers "
                f"{pct(h['dis_static'])} on time. {replan}")

    vol = round(-100 * h["vol_change"])
    if h["vol_static"] < h["base_static"]:
        volume = (f"Even with {vol}% less freight, on-time performance under the normal-timetable roster falls from "
                  f"{pct(h['base_static'])} to {pct(h['vol_static'])} once {share}% of flights bunch into waves.")
    else:
        volume = (f"With {vol}% less freight, the spare capacity absorbs the waves: on-time performance under the "
                  f"normal-timetable roster is {pct(h['vol_static'])}, against {pct(h['base_static'])} on the normal timetable.")

    tz = h["tz_points"]
    tz_s = (f"Unchecked, the time zone defect alone moves on-time performance by {abs(tz):.1f} points "
            f"({'up' if tz > 0 else 'down'}), from {pct(h['dq_truth'])} to {pct(h['dq_tz_only'])}.")

    catch = (f"Expediting the riskiest {round(100 * h['expedite_share'])}% of AWBs at arrival would reach "
             f"{pct(h['model_catch'], 0)} of the shipments that end up late.")

    gap = h["drift_pred"] - h["drift_actual"]
    drift = (f"The risk model trained on normal months predicts a {pct(h['drift_pred'])} late rate on the bunched "
             f"arrivals; the actual rate is {pct(h['drift_actual'])}. Its AUC moves from {h['drift_auc_base']:.3f} to "
             f"{h['drift_auc']:.3f}.")
    fx = C.load()["flex"]
    pool = (f"a call-in pool of {fx['pool_size']} staff, called when more than {fx['backlog_trigger']} AWBs wait for "
            f"breakdown")
    if h["dis_flex"] > max(h["dis_replanned"], h["dis_static"]):
        flex = (f"Keeping the normal-timetable roster and adding {pool}, does better still: {pct(h['dis_flex'])} on time "
                f"for {h['dis_flex_hours_week']:,.0f} call-in hours a week.")
    else:
        flex = (f"Keeping the normal-timetable roster and adding {pool}, reaches {pct(h['dis_flex'])} on time for "
                f"{h['dis_flex_hours_week']:,.0f} call-in hours a week.")
    roster = (f"On the normal timetable, the optimized roster delivers {pct(h['opt_on_time'])} on time against "
              f"{pct(h['legacy_on_time'])} for the legacy roster, with {h['opt_hours_week']:,.0f} staff hours a week "
              f"against {h['legacy_hours_week']:,.0f}.")
    return {"headline": headline, "flex": flex, "volume": volume, "timezone": tz_s, "catch": catch, "drift": drift,
            "roster": roster, "drift_direction": "over" if gap > 0 else "under"}


def write(h: dict) -> None:
    (C.DATA / "headline.json").write_text(json.dumps(h, indent=2, default=str), encoding="utf-8")


def read() -> dict:
    return json.loads((C.DATA / "headline.json").read_text(encoding="utf-8"))
