"""Every number the README and the teaser cards quote, computed from the result files alone.

The sentences are worded from the numbers: where a result goes the other way from the expectation, the wording
follows the result.
"""
from __future__ import annotations

import json

import pandas as pd

from lab import config as C


PRODUCT_NOUNS = {"general": "general freight", "express": "express freight", "perishable": "perishable goods",
                 "pharma": "medicines", "dangerous_goods": "dangerous goods", "live_animals": "live animals"}


def _read(name: str) -> pd.DataFrame:
    return pd.read_parquet(C.DATA / f"{name}.parquet")


def story(chosen: str) -> dict:
    """The shipment the overview's story follows: the earliest late shipment in the test months that the
    early-warning model put on its fast-track list (lab.shipments.story_pick applies the same rule in the app)."""
    cfg = C.load()
    p = _read("model_predictions")
    p["awb_id"] = p["awb_id"].astype(str)
    p["score"] = p["p_hgb" if chosen == "Gradient boosting" else "p_lr"]
    p["rank"] = p["score"].rank(pct=True)
    cut = p["score"].quantile(1 - cfg["model"]["expedite_share"])
    a = _read("awb_clean")
    a["awb_id"] = a["awb_id"].astype(str)
    a = a.set_index("awb_id")
    hit = p[(p["late"] == 1) & (p["score"] >= cut) & p["awb_id"].isin(a.index)].sort_values("arr_ts").iloc[0]
    r = a.loc[hit["awb_id"]]
    sla = float(cfg["sla_hours"][str(r["product"])])
    due = r["arr_ts"] + pd.Timedelta(hours=sla)
    return {"id": hit["awb_id"], "flight": str(r["flight"]), "carrier": str(r["carrier"]),
            "aircraft": "freighter" if str(r["flight_type"]) == "freighter" else "passenger plane",
            "region": str(r["region"]), "product": str(r["product"]), "pieces": int(r["pieces"]),
            "weight_kg": float(r["weight_kg"]), "sla_h": sla, "arr": r["arr_ts"].isoformat(),
            "due": due.isoformat(), "nfd": r["nfd_ts"].isoformat(),
            "flight_late_min": float((r["arr_ts"] - r["sched_arr"]).total_seconds() / 60),
            "backlog": float(hit["backlog_at_arr"]), "score": float(hit["score"]), "rank": float(hit["rank"]),
            "missed_by_min": float((r["nfd_ts"] - due).total_seconds() / 60)}


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
        "story": story(chosen),
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
        replan = f"Re-planning the roster for the new schedule brings it back to {pct(h['dis_replanned'])} {cost}."
    else:
        replan = (f"Re-planning the roster for the new schedule does not beat it: {pct(h['dis_replanned'])} on time {cost}.")
    headline = (f"When {share}% of flights are squeezed into two daily rush hours, the roster built for the normal "
                f"timetable gets {pct(h['dis_static'])} of shipments ready on time. {replan}")

    vol = round(-100 * h["vol_change"])
    if h["vol_static"] < h["base_static"]:
        volume = (f"Even with {vol}% less freight, the recommended roster falls from {pct(h['base_static'])} to "
                  f"{pct(h['vol_static'])} on time once {share}% of flights bunch into rush hours.")
    else:
        volume = (f"With {vol}% less freight, the spare capacity absorbs the rush hours: the recommended roster gets "
                  f"{pct(h['vol_static'])} on time, against {pct(h['base_static'])} on the normal timetable.")

    tz = h["tz_points"]
    tz_s = (f"Left unchecked, the time zone error alone moves on-time performance {'up' if tz > 0 else 'down'} "
            f"{abs(tz):.1f} percentage points, from {pct(h['dq_truth'])} to {pct(h['dq_tz_only'])}.")

    catch = (f"Flagging the riskiest {round(100 * h['expedite_share'])}% of shipments when their plane lands would "
             f"catch {pct(h['model_catch'], 0)} of the shipments that end up late.")

    gap = h["drift_pred"] - h["drift_actual"]
    auc_drop = h["drift_auc_base"] - h["drift_auc"]
    rank = (f"It still puts the riskiest shipments first almost as well as before (ranking accuracy {h['drift_auc_base']:.3f} "
            f"on the normal timetable, {h['drift_auc']:.3f} here), so its order holds but its odds need updating."
            if auc_drop < 0.01 else
            f"Its ranking slips too: accuracy falls from {h['drift_auc_base']:.3f} to {h['drift_auc']:.3f}.")
    drift = (f"The early-warning model, trained on normal months, expects {pct(h['drift_pred'])} of shipments to be late "
             f"on the bunched schedule; in fact {pct(h['drift_actual'])} are. {rank}")
    fx = C.load()["flex"]
    pool = (f"a team of {fx['pool_size']} on-call staff, called in whenever {fx['backlog_trigger']} or more shipments "
            f"are waiting to be unpacked")
    if h["dis_flex"] > max(h["dis_replanned"], h["dis_static"]):
        flex = (f"Keeping the recommended roster and adding {pool}, does better still: {pct(h['dis_flex'])} on time "
                f"for {h['dis_flex_hours_week']:,.0f} on-call hours a week.")
    else:
        flex = (f"Keeping the recommended roster and adding {pool}, reaches {pct(h['dis_flex'])} on time for "
                f"{h['dis_flex_hours_week']:,.0f} on-call hours a week.")
    roster = (f"On the normal timetable, a recommended roster gets {pct(h['opt_on_time'])} of shipments ready on time "
              f"against {pct(h['legacy_on_time'])} for the current roster, with {h['opt_hours_week']:,.0f} staff hours "
              f"a week instead of {h['legacy_hours_week']:,.0f}.")
    s = h["story"]
    arr, nfd = pd.Timestamp(s["arr"]), pd.Timestamp(s["nfd"])
    cfg = C.load()
    test0 = pd.Timestamp(cfg["split"]["valid_end"]) + pd.Timedelta(days=1)
    late = s["flight_late_min"]
    lateness = (f"{late:.0f} minutes behind schedule" if late > 5 else f"{-late:.0f} minutes early" if late < -5
                else "on schedule")
    story_s = (f"{'Shortly after midnight on ' if arr.hour < 3 else 'On '}{arr:%A} {arr.day} {arr:%B %Y}, flight "
               f"{s['flight']}, a {s['aircraft']} from {s['carrier']}, lands from {s['region']} {lateness}. On board is "
               f"shipment {s['id']}: {s['pieces']} pieces of {PRODUCT_NOUNS[s['product']]} weighing "
               f"{s['weight_kg']:,.1f} kg, promised ready within {s['sla_h']:g} hours. {s['backlog']:.0f} shipments are "
               f"already waiting to be unpacked. The early-warning model flags it the moment the plane lands: riskier "
               f"than {100 * s['rank']:.0f}% of the shipments from {test0:%B} to "
               f"{pd.Timestamp(cfg['window']['cutoff']):%B %Y}. Even so, it is ready at {nfd:%H:%M}, "
               f"{s['missed_by_min']:.0f} minutes after the promise runs out.")
    return {"headline": headline, "flex": flex, "volume": volume, "timezone": tz_s, "catch": catch, "drift": drift,
            "roster": roster, "drift_direction": "over" if gap > 0 else "under", "story": story_s}


def write(h: dict) -> None:
    (C.DATA / "headline.json").write_text(json.dumps(h, indent=2, default=str), encoding="utf-8")


def read() -> dict:
    return json.loads((C.DATA / "headline.json").read_text(encoding="utf-8"))
