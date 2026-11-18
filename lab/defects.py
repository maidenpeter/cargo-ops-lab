"""Builds the clean event log (the truth) and a dirty copy with defects injected at config rates.

The dirty copy looks like what an analyst receives: an AWB feed and a milestone feed, one row per message.
The record of which AWB got which defect is kept apart (dq_truth) and never shown to the detector.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from lab import config as C
from lab.schedule import rng_for

MILESTONES = ["ARR", "RCF", "NFD", "DLV"]
PRODUCT_CODES = {"general": "GEN", "express": "XPS", "perishable": "PER", "pharma": "PIL",
                 "dangerous_goods": "DGR", "live_animals": "AVI"}
BAD_CODES = ["", "GN", "PRE", "XXX", "DG"]
DEFECTS = ["missing_rcf", "missing_nfd", "out_of_sequence", "duplicate_resend", "weight_mismatch",
           "invalid_product", "timezone"]


def event_log(awbs: pd.DataFrame, rcf_min: np.ndarray, nfd_min: np.ndarray, t0: pd.Timestamp) -> pd.DataFrame:
    """Wide truth table: one row per AWB with the four milestones in hub local time, stamped to the minute.
    Milestones after the cut-off are not yet observed and stay empty."""
    cut = C.cutoff()
    w = awbs.copy()
    w["arr_ts"] = w["arr"].dt.floor("min")
    w["rcf_ts"] = (t0 + pd.to_timedelta(rcf_min, unit="min")).floor("min")
    w["nfd_ts"] = (t0 + pd.to_timedelta(nfd_min, unit="min")).floor("min")
    w["dlv_ts"] = (w["nfd_ts"] + pd.to_timedelta(w["customer_min"], unit="min")).dt.floor("min")
    for m in ["arr_ts", "rcf_ts", "nfd_ts", "dlv_ts"]:
        w.loc[w[m] >= cut, m] = pd.NaT
    w = w[w["arr_ts"].notna()].reset_index(drop=True)
    w["sched_arr"] = w["sched_arr"].dt.floor("min")
    return w.drop(columns=["arr"])


def to_feeds(wide: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Wide truth to the two message feeds (AWB master and milestone events), with UTC stored alongside local time."""
    off = pd.Timedelta(hours=C.load()["hub_utc_offset_hours"])
    awb_cols = ["awb_id", "flight_key", "flight", "carrier", "flight_type", "region", "product", "handling_unit",
                "pieces", "weight_kg", "weight_checked_kg", "sched_arr"]
    awb = wide[awb_cols].copy()
    awb.insert(1, "msg_id", "A" + pd.Series(np.arange(len(awb)), dtype=str).str.zfill(7))
    awb["product_code"] = awb.pop("product").map(PRODUCT_CODES)
    parts = []
    for m in MILESTONES:
        col = m.lower() + "_ts"
        e = wide.loc[wide[col].notna(), ["awb_id", col]].rename(columns={col: "ts_local"})
        e["milestone"] = m
        parts.append(e)
    ev = pd.concat(parts, ignore_index=True)
    ev["ts_utc"] = ev["ts_local"] - off
    ev = ev.sort_values(["awb_id", "ts_local"], kind="stable").reset_index(drop=True)
    ev.insert(0, "msg_id", "E" + pd.Series(np.arange(len(ev)), dtype=str).str.zfill(8))
    return awb, ev[["msg_id", "awb_id", "milestone", "ts_local", "ts_utc"]]


def assign(wide: pd.DataFrame) -> pd.DataFrame:
    """Which AWB gets which defect (at most one each), and which AWBs come through the manual channel."""
    cfg = C.load()
    rates = cfg["defects"]
    rng = rng_for(401)
    u = rng.random(len(wide))
    cum = np.cumsum([rates[d] for d in DEFECTS])
    k = np.searchsorted(cum, u, side="right")
    defect = np.where(k < len(DEFECTS), np.array(DEFECTS + ["none"])[np.minimum(k, len(DEFECTS))], "none")
    t = pd.DataFrame({"awb_id": wide["awb_id"].to_numpy(), "defect": defect})
    # a defect needs the milestones it corrupts; otherwise the AWB is left clean
    has_rcf, has_nfd = wide["rcf_ts"].notna().to_numpy(), wide["nfd_ts"].notna().to_numpy()
    need = {"missing_rcf": has_rcf, "missing_nfd": has_nfd, "out_of_sequence": has_rcf & has_nfd}
    for d, ok in need.items():
        t.loc[(t["defect"] == d) & ~ok, "defect"] = "none"
    tz = t["defect"] == "timezone"
    on_arr = rng_for(402).random(len(t)) < rates["timezone_arr_share"]
    t["variant"] = np.where(tz & on_arr, "arr_stamp", np.where(tz, "terminal_stamps", ""))
    t.loc[(t["variant"] == "terminal_stamps") & ~has_rcf, ["defect", "variant"]] = ["none", ""]
    t["manual_channel"] = rng_for(403).random(len(t)) < cfg["manual_channel_share"]
    return t


def inject(awb: pd.DataFrame, ev: pd.DataFrame, truth: pd.DataFrame, only: list[str] | None = None
           ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Apply the assigned defects to copies of the two feeds. `only` limits injection to some defect types."""
    cfg = C.load()
    off = pd.Timedelta(hours=cfg["hub_utc_offset_hours"])
    t = truth if only is None else truth[truth["defect"].isin(only)]
    hit = lambda d: set(t.loc[t["defect"] == d, "awb_id"])  # noqa: E731
    a, e = awb.copy(), ev.copy()
    rng = rng_for(404)

    # manual channel: no UTC stamp
    manual = set(truth.loc[truth["manual_channel"], "awb_id"])
    e.loc[e["awb_id"].isin(manual), "ts_utc"] = pd.NaT

    # missing milestones: the message never arrives
    drop = (e["awb_id"].isin(hit("missing_rcf")) & (e["milestone"] == "RCF")) | \
           (e["awb_id"].isin(hit("missing_nfd")) & (e["milestone"] == "NFD"))
    e = e[~drop]

    # out of sequence: NFD stamped before RCF (local and UTC agree, so it is not a time zone problem)
    ids = hit("out_of_sequence")
    rcf = e[(e["milestone"] == "RCF") & e["awb_id"].isin(ids)].set_index("awb_id")["ts_local"]
    m = (e["milestone"] == "NFD") & e["awb_id"].isin(ids)
    back = pd.to_timedelta(rng.uniform(10, 120, m.sum()).round(), unit="min")
    e.loc[m, "ts_local"] = rcf.reindex(e.loc[m, "awb_id"]).to_numpy() - back.to_numpy()
    e.loc[m & e["ts_utc"].notna(), "ts_utc"] = e.loc[m & e["ts_utc"].notna(), "ts_local"] - off

    # time zone: stamped in UTC but labeled hub local, so the local value is offset hours early
    tz = t[t["defect"] == "timezone"]
    arr_ids = set(tz.loc[tz["variant"] == "arr_stamp", "awb_id"])
    term_ids = set(tz.loc[tz["variant"] == "terminal_stamps", "awb_id"])
    m = (e["awb_id"].isin(arr_ids) & (e["milestone"] == "ARR")) | \
        (e["awb_id"].isin(term_ids) & e["milestone"].isin(["RCF", "NFD"]))
    e.loc[m, "ts_local"] = e.loc[m, "ts_local"] - off

    # weight keyed wrong at check-in
    ids = hit("weight_mismatch")
    m = a["awb_id"].isin(ids)
    kind = rng.integers(0, 4, m.sum())
    factor = np.select([kind == 0, kind == 1, kind == 2], [10.0, 0.1, rng.uniform(0.5, 0.8, m.sum())],
                       rng.uniform(1.25, 2.0, m.sum()))
    a.loc[m, "weight_checked_kg"] = (a.loc[m, "weight_kg"] * factor).round(1)

    # product code blank or not in the code list
    ids = hit("invalid_product")
    m = a["awb_id"].isin(ids)
    a.loc[m, "product_code"] = np.array(BAD_CODES)[rng.integers(0, len(BAD_CODES), m.sum())]

    # duplicate resend: the AWB record and all its milestone messages arrive twice
    ids = hit("duplicate_resend")
    da = a[a["awb_id"].isin(ids)].copy()
    da["msg_id"] = da["msg_id"] + "R"
    de = e[e["awb_id"].isin(ids)].copy()
    de["msg_id"] = de["msg_id"] + "R"
    a = pd.concat([a, da], ignore_index=True)
    e = pd.concat([e, de], ignore_index=True)
    return a.sort_values(["awb_id", "msg_id"]).reset_index(drop=True), e.sort_values(["awb_id", "msg_id"]).reset_index(drop=True)
