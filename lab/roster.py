"""Roster optimization: a simulation grid, a choose-one-per-shift integer program (PuLP with CBC), and re-simulation.

The grid moves one weekday and shift at a time through its allowed headcounts, holding every other cell at a base
roster, and records the total late AWBs and penalty across the whole window. The integer program adds those
one-at-a-time effects up and picks one headcount per cell. Cells interact through backlog carried from one shift to the
next, so the sum is an approximation; every roster reported is re-simulated end to end.
"""
from __future__ import annotations

import multiprocessing as mp
from dataclasses import dataclass

import numpy as np
import pandas as pd
import pulp

from lab import config as C
from lab import schedule as S
from lab import terminal as T


@dataclass
class Bundle:
    name: str
    awbs: pd.DataFrame          # arrivals for the warm-up and the evaluation window
    flights: pd.DataFrame       # the schedule behind them
    t0: pd.Timestamp            # reference midnight, minute 0 of the simulation
    win_start: float            # evaluation window, minutes from t0
    win_end: float
    horizon: float
    weeks: float


SLIM = ["awb_id", "flight_key", "carrier", "flight_type", "region", "product", "handling_unit", "pieces", "weight_kg",
        "sched_arr", "arr"]


def make_bundle(name: str, flights: pd.DataFrame, awbs: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> Bundle:
    warm = C.load()["roster_opt"]["warmup_days"]
    t0 = (start - pd.Timedelta(days=warm + 1)).normalize()
    a = awbs[(awbs["arr"] >= t0 + pd.Timedelta(days=1)) & (awbs["arr"] < end)][SLIM]
    a = a.sort_values(["arr", "awb_id"], kind="stable").reset_index(drop=True)  # draws follow row order: keep it canonical
    f = flights[(flights["sched_arr"] >= t0) & (flights["sched_arr"] < end + pd.Timedelta(days=1))].reset_index(drop=True)
    mins = lambda ts: (ts - t0).total_seconds() / 60  # noqa: E731
    return Bundle(name, a, f, t0, mins(start), mins(end), mins(end) + 2 * 1440, (end - start).days / 7)


# ---------------------------------------------------------------- one evaluation
_PT: dict = {}
_BUNDLES: dict = {}


def _process_times(b: Bundle, seed: int) -> dict:
    key = (b.name, seed)
    if key not in _PT:
        pt = S.process_times(b.awbs, b.t0, seed)
        wd, sh = S.shift_cell(b.awbs["arr"])
        prods = S.products()
        pt["cell_wd"], pt["cell_sh"] = wd, sh
        pt["prod"] = b.awbs["product"].map({p: i for i, p in enumerate(prods)}).to_numpy()
        pt["sla"] = b.awbs["product"].map(C.sla_minutes()).to_numpy(float)
        pt["in_win"] = (pt["arr"] >= b.win_start) & (pt["arr"] < b.win_end)
        _PT[key] = pt
    return _PT[key]


def evaluate(b: Bundle, roster: np.ndarray, seed: int, flex: dict | None = None) -> dict:
    """Simulate one roster on one bundle and seed; count late AWBs in the window by arrival weekday, shift and product."""
    pt = _process_times(b, seed)
    sim = T.simulate(pt, b.t0.weekday(), roster, seed, b.horizon, flex)
    _, late = T.nfd_and_late(pt, sim, pt["sla"])
    w = pt["in_win"]
    P = len(S.products())
    shape = (7, 3, P)
    late_c = np.zeros(shape)
    n_c = np.zeros(shape)
    np.add.at(late_c, (pt["cell_wd"][w], pt["cell_sh"][w], pt["prod"][w]), late[w])
    np.add.at(n_c, (pt["cell_wd"][w], pt["cell_sh"][w], pt["prod"][w]), 1)
    sh = sim.shifts
    in_w = (sh["start_min"] >= b.win_start) & (sh["start_min"] < b.win_end)
    hours = C.load()["shifts"]["hours"]
    fx = sim.flex
    fx_w = fx[(fx["start_min"] >= b.win_start) & (fx["start_min"] < b.win_end)] if len(fx) else fx
    return {"late_c": late_c, "n_c": n_c,
            "staff_hours": float(sh.loc[in_w, "rostered"].sum() * hours),
            "present_hours": float(sh.loc[in_w, "present"].sum() * hours),
            "flex_hours": float((fx_w["staff"] * fx_w["minutes"]).sum() / 60) if len(fx_w) else 0.0,
            "callins": int(len(fx_w)),
            "unfinished": int(np.isnan(sim.rcf[w]).sum())}


def _init(bundles: dict) -> None:
    global _BUNDLES
    _BUNDLES = bundles


def _task(args) -> dict:
    name, roster, seed, flex = args
    return evaluate(_BUNDLES[name], roster, seed, flex)


class Runner:
    """A process pool that holds every bundle, so each task only sends a roster and a seed."""

    def __init__(self, bundles: dict[str, Bundle], processes: int | None = None):
        self.bundles = bundles
        self.pool = mp.get_context("spawn").Pool(processes or max(1, (mp.cpu_count() or 2) - 1),
                                                 initializer=_init, initargs=(bundles,))

    def map(self, tasks: list) -> list[dict]:
        return self.pool.map(_task, tasks, chunksize=1)

    def close(self) -> None:
        self.pool.close()
        self.pool.join()


# ---------------------------------------------------------------- summaries
def penalties() -> np.ndarray:
    return np.array([C.load()["late_penalty_usd"][p] for p in S.products()])


def summarize(results: list[dict], weeks: float) -> dict:
    """Average a roster's results over seeds, per week."""
    cfg = C.load()
    pen = penalties()
    late = np.mean([r["late_c"].sum() for r in results])
    n = np.mean([r["n_c"].sum() for r in results])
    staff = np.mean([r["staff_hours"] for r in results]) / weeks
    flex = np.mean([r["flex_hours"] for r in results]) / weeks
    penalty = np.mean([(r["late_c"] * pen).sum() for r in results]) / weeks
    labor = (staff + flex * cfg["flex"]["cost_multiplier"]) * cfg["hourly_cost_usd"]
    return {"on_time": 1 - late / n, "late_per_week": late / weeks, "awbs_per_week": n / weeks,
            "staff_hours_per_week": staff, "flex_hours_per_week": flex,
            "callins_per_week": np.mean([r["callins"] for r in results]) / weeks,
            "labor_cost_per_week": labor, "penalty_per_week": penalty, "total_cost_per_week": labor + penalty,
            "unfinished": float(np.mean([r["unfinished"] for r in results]))}


def cell_on_time(results: list[dict]) -> np.ndarray:
    late = np.sum([r["late_c"].sum(axis=2) for r in results], axis=0)
    n = np.sum([r["n_c"].sum(axis=2) for r in results], axis=0)
    return 1 - late / np.maximum(n, 1)


# ---------------------------------------------------------------- grid and integer program
def domain(legacy: np.ndarray) -> list[list[range]]:
    o = C.load()["roster_opt"]
    return [[range(max(o["min_headcount"], legacy[d, s] - o["max_change"]),
                   min(o["max_headcount"], legacy[d, s] + o["max_change"]) + 1) for s in range(3)] for d in range(7)]


def grid_tasks(bundle: str, base: np.ndarray, legacy: np.ndarray, seeds: list[int]) -> list[tuple]:
    """The base roster once, then every allowed headcount for one weekday and shift at a time, the rest held at base."""
    dom = domain(legacy)
    tasks = [(bundle, base.copy(), seed, None, -1, -1, -1) for seed in seeds]
    for d in range(7):
        for s in range(3):
            for h in dom[d][s]:
                if h == base[d, s]:
                    continue
                r = base.copy()
                r[d, s] = h
                for seed in seeds:
                    tasks.append((bundle, r, seed, None, d, s, h))
    return tasks


def grid_table(tasks: list[tuple], results: list[dict], weeks: float, base: np.ndarray) -> pd.DataFrame:
    """For every weekday, shift and headcount: total late AWBs and penalty per week across the whole window when only
    that cell changes, averaged over seeds. The base roster's own value fills each cell at its base headcount."""
    pen = penalties()
    rows = []
    for t, r in zip(tasks, results):
        tot = {"seed": t[2], "late": r["late_c"].sum() / weeks, "awbs": r["n_c"].sum() / weeks,
               "penalty": (r["late_c"] * pen).sum() / weeks}
        if t[4] < 0:
            rows += [{"weekday": d, "shift": s, "headcount": int(base[d, s]), "is_base": True, **tot}
                     for d in range(7) for s in range(3)]
        else:
            rows.append({"weekday": t[4], "shift": t[5], "headcount": t[6], "is_base": False, **tot})
    g = pd.DataFrame(rows)
    return g.groupby(["weekday", "shift", "headcount", "is_base"], as_index=False)[["late", "awbs", "penalty"]].mean()


def solve(grid: pd.DataFrame, legacy: np.ndarray, budget_hours: float, labor: bool = True) -> tuple[np.ndarray, float]:
    """Choose one headcount per weekday and shift within the weekly staff-hour budget and the allowed change from the
    legacy roster. With labor=True, minimize labor cost plus late penalties (the plan); with labor=False, minimize late
    penalties alone (the best service a budget can buy, for the frontier). Each cell's effects are added up, which is
    the first-order approximation the re-simulation then checks."""
    cfg = C.load()
    hours, cost = cfg["shifts"]["hours"], cfg["hourly_cost_usd"]
    dom = domain(legacy)
    g = grid.set_index(["weekday", "shift", "headcount"])["penalty"]
    prob = pulp.LpProblem("roster", pulp.LpMinimize)
    x = {}
    for d in range(7):
        for s in range(3):
            for h in dom[d][s]:
                if (d, s, h) in g.index:
                    x[d, s, h] = prob.add_variable(f"x_{d}_{s}_{h}", cat="Binary")
    prob += pulp.lpSum(v * ((k[2] * hours * cost if labor else 0.0) + float(g[k])) for k, v in x.items())
    for d in range(7):
        for s in range(3):
            prob += pulp.lpSum(v for k, v in x.items() if k[0] == d and k[1] == s) == 1
    prob += pulp.lpSum(v * k[2] * hours for k, v in x.items()) <= budget_hours
    stats = prob.solve(pulp.COIN_CMD(msg=False, gapRel=0.0, gapAbs=0.0))  # prove optimality; the model is small
    if not _optimal(stats):
        raise RuntimeError(f"roster model not solved to optimality: {stats.status}, gap {stats.gap_rel}")
    roster = np.zeros((7, 3), dtype=int)
    for k, v in x.items():
        if v.value() > 0.5:
            roster[k[0], k[1]] = k[2]
    return roster, float(prob.objective.value())


def _optimal(stats) -> bool:
    """CBC sometimes reports 'Optimal (within gap tolerance)' when bound and solution differ only by rounding;
    PuLP 4 calls that GapLimit. Accept it only with a solution and a gap that is zero in practice."""
    if stats.status == pulp.LpSolveStatus.Optimal:
        return True
    if stats.status != pulp.LpSolveStatus.GapLimit or not stats.has_solution:
        return False
    if stats.gap_rel is not None:
        return abs(stats.gap_rel) <= 1e-9
    obj, bound = stats.objective, stats.best_bound
    return obj is not None and bound is not None and abs(obj - bound) <= 1e-9 * max(1.0, abs(obj))


def predicted(grid: pd.DataFrame, roster: np.ndarray) -> dict:
    """What the grid says a roster will do: the base result plus each cell's own change, added up."""
    g = grid.set_index(["weekday", "shift", "headcount"])
    b = grid[grid["is_base"]].iloc[0]
    late, penalty = b["late"], b["penalty"]
    for d in range(7):
        for s in range(3):
            r = g.loc[(d, s, int(roster[d, s]))]
            late += r["late"] - b["late"]
            penalty += r["penalty"] - b["penalty"]
    return {"late_per_week": late, "penalty_per_week": penalty, "on_time": 1 - late / b["awbs"]}


def budget(legacy: np.ndarray, multiplier: float) -> float:
    return float(legacy.sum() * C.load()["shifts"]["hours"] * multiplier)


def optimize(runner: Runner, bundle: str, legacy: np.ndarray, seeds: list[int], multiplier: float,
             passes: int) -> dict:
    """Grid, solve, and (optionally) rebuild the grid around the answer and solve again."""
    b = runner.bundles[bundle]
    base = legacy.copy()
    grids = []
    roster = legacy
    for p in range(passes):
        tasks = grid_tasks(bundle, base, legacy, seeds)
        res = runner.map([t[:4] for t in tasks])
        g = grid_table(tasks, res, b.weeks, base)
        g.insert(0, "pass", p + 1)
        grids.append(g)
        roster, _ = solve(g, legacy, budget(legacy, multiplier))
        base = roster
    return {"roster": roster, "grid": grids[-1], "grids": pd.concat(grids, ignore_index=True)}


def roster_frame(roster: np.ndarray, **labels) -> pd.DataFrame:
    names = C.load()["shifts"]["names"]
    rows = [{**labels, "weekday": d, "shift": s, "shift_name": names[s], "headcount": int(roster[d, s])}
            for d in range(7) for s in range(3)]
    return pd.DataFrame(rows)
