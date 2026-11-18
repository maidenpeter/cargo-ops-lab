"""Weekly timetable to flights, flights to air waybills (AWBs), process-time draws, and the disruption transform.

Times are hub local. Minutes are counted from a reference midnight (t0) so the simulation works on plain floats.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from lab import config as C

HANDLING_UNITS = ["bup_breakdown", "bup_intact", "loose"]


def products() -> list[str]:
    return list(C.load()["products"].keys())


def rng_for(*keys: int) -> np.random.Generator:
    """A generator derived from the master seed and extra integer keys, so every draw is reproducible."""
    return np.random.default_rng([C.load()["seed"], *keys])


# ---------------------------------------------------------------- flights
def build_flights(start: pd.Timestamp, end: pd.Timestamp, rng: np.random.Generator) -> pd.DataFrame:
    """Every scheduled flight from start (inclusive) to end (exclusive), with delay, cancellation and AWB count."""
    cfg = C.load()
    tt = C.timetable()
    rows = []
    for day in pd.date_range(start, end - pd.Timedelta(days=1), freq="D"):
        wd = str(day.isoweekday())
        for r in tt.itertuples(index=False):
            if wd in str(r.days):
                hh, mm = (int(x) for x in r.sta.split(":"))
                rows.append((r.flight, r.carrier, r.type, r.region, day + pd.Timedelta(hours=hh, minutes=mm), r.awbs))
    f = pd.DataFrame(rows, columns=["flight", "carrier", "flight_type", "region", "sched_arr", "awbs_mean"])
    n = len(f)
    fc = cfg["flights"]
    f["cancelled"] = rng.random(n) < fc["cancel_rate"]

    d = fc["delay"]
    par = {k: f["flight_type"].map({t: d[t][k] for t in d}).to_numpy(float) for k in ("mean", "sd", "tail_prob", "tail_mean")}
    z, u, e = rng.standard_normal(n), rng.random(n), rng.exponential(1.0, n)
    delay = par["mean"] + par["sd"] * z + (u < par["tail_prob"]) * par["tail_mean"] * e
    f["delay_min"] = np.round(np.maximum(delay, fc["earliest_min"]), 1)
    f["arr"] = f["sched_arr"] + pd.to_timedelta(f["delay_min"], unit="min")

    season = np.array(fc["season"])[f["sched_arr"].dt.month.to_numpy() - 1]
    years = (f["sched_arr"] - C.start()).dt.days.to_numpy() / 365.25
    mean = f["awbs_mean"].to_numpy() * season * (1 + fc["growth_per_year"]) ** years
    k = fc["awb_dispersion"]
    lam = rng.gamma(k, mean / k)
    f["n_awbs"] = rng.poisson(lam)
    f.loc[f["cancelled"], "n_awbs"] = 0
    f["flight_key"] = f["flight"] + "-" + f["sched_arr"].dt.strftime("%Y%m%d")
    return f.sort_values(["sched_arr", "flight"]).reset_index(drop=True)


# ---------------------------------------------------------------- air waybills
def build_awbs(flights: pd.DataFrame, rng: np.random.Generator, id_start: int = 1) -> pd.DataFrame:
    """One row per AWB on each operated flight: product, handling unit, pieces, weights and customer time."""
    cfg = C.load()
    op = flights[flights["n_awbs"] > 0]
    idx = np.repeat(op.index.to_numpy(), op["n_awbs"].to_numpy())
    a = flights.loc[idx, ["flight_key", "flight", "carrier", "flight_type", "region", "sched_arr", "arr"]].reset_index(drop=True)
    n = len(a)
    a.insert(0, "awb_id", [f"AWB{i:07d}" for i in range(id_start, id_start + n)])

    prods = products()
    shares = np.array([cfg["products"][p] for p in prods])
    a["product"] = np.array(prods)[rng.choice(len(prods), size=n, p=shares / shares.sum())]

    hu = np.empty(n, dtype=object)
    u = rng.random(n)
    for t, sh in cfg["handling_units"].items():
        m = (a["flight_type"] == t).to_numpy()
        cum = np.cumsum([sh[h] for h in HANDLING_UNITS])
        hu[m] = np.array(HANDLING_UNITS)[np.searchsorted(cum / cum[-1], u[m], side="right")]
    a["handling_unit"] = hu

    pm = a["flight_type"].map(cfg["pieces_mean"]).to_numpy(float) - 1
    nb_n = 2.0
    a["pieces"] = 1 + rng.negative_binomial(nb_n, nb_n / (nb_n + pm))
    kgpp = np.exp(np.log(a["flight_type"].map(cfg["kg_per_piece_median"]).to_numpy(float)) + cfg["kg_per_piece_sigma"] * rng.standard_normal(n))
    a["weight_kg"] = np.round(a["pieces"].to_numpy() * kgpp, 1)
    gap = np.clip(cfg["weight_check_noise"] * rng.standard_normal(n), -cfg["weight_check_clip"], cfg["weight_check_clip"])
    a["weight_checked_kg"] = np.round(a["weight_kg"] * (1 + gap), 1)

    cu = cfg["customer"]
    hold = (rng.random(n) < a["product"].map(cu["hold_prob"]).to_numpy(float)) * np.exp(
        np.log(cu["hold_median_h"]) + cu["hold_sigma"] * rng.standard_normal(n))
    pickup = np.exp(np.log(a["product"].map(cu["pickup_median_h"]).to_numpy(float)) + cu["pickup_sigma"] * rng.standard_normal(n))
    a["customer_min"] = np.round((hold + pickup) * 60, 1)
    a["customs_hold"] = hold > 0
    return a


# ---------------------------------------------------------------- process times
def process_times(awbs: pd.DataFrame, t0: pd.Timestamp, seed: int) -> dict[str, np.ndarray]:
    """Per-AWB process draws for one simulation seed. The same seed gives the same draws for any roster
    (common random numbers), so rosters are compared on identical work."""
    cfg = C.load()
    rng = rng_for(101, seed)
    n = len(awbs)
    ft = awbs["flight_type"].to_numpy()
    lo = np.where(ft == "belly", cfg["tow_min"]["belly"][0], cfg["tow_min"]["freighter"][0])
    hi = np.where(ft == "belly", cfg["tow_min"]["belly"][1], cfg["tow_min"]["freighter"][1])
    spread = np.where(ft == "belly", cfg["offload_spread_min"]["belly"], cfg["offload_spread_min"]["freighter"])
    tow = lo + (hi - lo) * rng.random(n)
    off = spread * rng.random(n)
    arr = ((awbs["arr"] - t0).dt.total_seconds() / 60).to_numpy()

    w = cfg["work"]
    hu = awbs["handling_unit"].to_numpy()
    setup = np.select([hu == "bup_breakdown", hu == "loose"], [w["setup"]["bup_breakdown"], w["setup"]["loose"]], 0.0)
    base = setup + w["per_piece"] * awbs["pieces"].to_numpy() + w["per_100kg"] * awbs["weight_kg"].to_numpy() / 100
    noise = np.exp(-w["noise_sigma"] ** 2 / 2 + w["noise_sigma"] * rng.standard_normal(n))
    work = base * awbs["product"].map(w["product_factor"]).to_numpy(float) * noise
    intact = hu == "bup_intact"
    work[intact] = 0.0
    ci = cfg["intact_checkin_min"]
    checkin = ci[0] + (ci[1] - ci[0]) * rng.random(n)
    doc = np.exp(np.log(cfg["doc_check_median_min"]) + cfg["doc_check_sigma"] * rng.standard_normal(n))

    order = {p: i for i, p in enumerate(cfg["priority_products"])}
    prio = awbs["product"].map(lambda p: order.get(p, len(order))).to_numpy(int)
    return {"arr": arr, "ready": arr + tow + off, "work": work, "intact": intact, "checkin": checkin, "doc": doc,
            "prio": prio, "kg": awbs["weight_kg"].to_numpy(float)}


# ---------------------------------------------------------------- disruption
def wave_times(sched: pd.Series) -> pd.Series:
    """Nearest wave center to each scheduled arrival (looking at the day before, the same day and the day after)."""
    cfg = C.load()["disruption"]
    day = sched.dt.normalize()
    best, best_gap = None, None
    for c in cfg["wave_centers"]:
        hh, mm = (int(x) for x in c.split(":"))
        for shift_days in (-1, 0, 1):
            cand = day + pd.Timedelta(days=shift_days, hours=hh, minutes=mm)
            gap = (cand - sched).abs()
            if best is None:
                best, best_gap = cand.copy(), gap
            else:
                take = gap < best_gap
                best[take], best_gap[take] = cand[take], gap[take]
    return best


def disrupt(flights: pd.DataFrame, awbs: pd.DataFrame, share: float, volume_change: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Move a share of flights into compressed arrival waves and thin AWB volume.

    The draws behind both choices are fixed, so scenarios are nested: the flights moved at 20% are also moved at
    40%, and the AWBs dropped at minus 10% are also dropped at minus 20%. With no change the inputs come back as they are.
    """
    cfg = C.load()["disruption"]
    f = flights.copy()
    a = awbs.copy()
    if share <= 0 and volume_change >= 0:
        return f, a
    u = rng_for(202).random(len(f))
    jitter = rng_for(203).uniform(-cfg["wave_half_width_min"], cfg["wave_half_width_min"], len(f))
    moved = u < share
    f["rescheduled"] = moved
    new_sched = (wave_times(f["sched_arr"]) + pd.to_timedelta(np.round(jitter), unit="min")).astype(f["sched_arr"].dtype)
    f.loc[moved, "sched_arr"] = new_sched[moved]
    f["arr"] = f["sched_arr"] + pd.to_timedelta(f["delay_min"], unit="min")
    m = f.set_index("flight_key")
    a["sched_arr"] = m["sched_arr"].reindex(a["flight_key"]).to_numpy()
    a["arr"] = m["arr"].reindex(a["flight_key"]).to_numpy()
    keep = rng_for(204).random(len(a)) >= -volume_change
    a = a[keep].reset_index(drop=True)
    f["n_awbs"] = f["flight_key"].map(a.groupby("flight_key").size()).fillna(0).astype(int)
    return f.sort_values("sched_arr").reset_index(drop=True), a.sort_values(["arr", "awb_id"]).reset_index(drop=True)


# ---------------------------------------------------------------- shift cells
def shift_cell(ts: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    """Weekday (Monday 0) and shift index (0 morning, 1 afternoon, 2 night) that own each timestamp.
    The night shift belongs to the day it starts, so 02:00 on Tuesday is Monday's night shift."""
    s = C.load()["shifts"]["starts"]
    h = ts.dt.hour.to_numpy()
    shift = np.where(h < s[0], 2, np.where(h < s[1], 0, np.where(h < s[2], 1, 2)))
    wd = ts.dt.weekday.to_numpy()
    wd = np.where(h < s[0], (wd - 1) % 7, wd)
    return wd, shift
