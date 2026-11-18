"""SimPy model of the import terminal.

ULDs reach the floor after the tow; intact ULDs are checked in without breakdown; everything else waits in one
priority queue for breakdown staff. Each shift brings its rostered crew minus absences. A worker on shift takes the
next AWB (priority products first, then first come first served), works it to the end even past the shift change,
and goes home when the shift is over. NFD follows RCF after a documentation check that is not staff constrained.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import simpy

from lab import config as C


@dataclass
class SimResult:
    rcf: np.ndarray            # minutes from t0; NaN if not received before the horizon
    bd_start: np.ndarray       # breakdown start, minutes from t0 (NaN for intact ULDs)
    shifts: pd.DataFrame       # one row per shift: rostered, present, busy minutes, kg and AWBs broken down
    flex: pd.DataFrame         # one row per call-in block (empty when no flex pool)


def simulate(pt: dict, t0_weekday: int, roster: np.ndarray, seed: int, horizon: float,
             flex: dict | None = None) -> SimResult:
    """Run the terminal from minute 0 to `horizon` on the process draws `pt` (see schedule.process_times)."""
    cfg = C.load()
    starts = cfg["shifts"]["starts"]
    shift_len = cfg["shifts"]["hours"] * 60
    rng = np.random.default_rng([cfg["seed"], 303, seed])  # absences only
    p_abs = cfg["absence_rate"]
    slots = 64  # one draw per possible crew slot per shift, so one shift's headcount never shifts another's absences

    ready, work, prio, kg = pt["ready"], pt["work"], pt["prio"], pt["kg"]
    n = len(ready)
    rcf = np.full(n, np.nan)
    bd_start = np.full(n, np.nan)
    intact = pt["intact"]
    rcf[intact] = ready[intact] + pt["checkin"][intact]
    rcf[rcf > horizon] = np.nan
    bd = np.flatnonzero(~intact)
    order = bd[np.argsort(ready[bd], kind="stable")]

    env = simpy.Environment()
    store = simpy.PriorityStore(env)
    shift_rows: list[dict] = []
    flex_rows: list[dict] = []

    def feeder():
        for i in order:
            t = ready[i]
            if t >= horizon:
                return
            if t > env.now:
                yield env.timeout(t - env.now)
            store.put((prio[i], t, i))

    def worker(end: float, rec: dict, state: list):
        while env.now < end:
            req = store.get()
            state[0] = req
            try:
                item = yield req
            except simpy.Interrupt:
                if req.triggered:          # an item was handed over in the same instant: put it back
                    store.put(req.value)
                else:
                    req.cancel()
                return
            state[0] = None
            i = item[2]
            bd_start[i] = env.now
            yield env.timeout(work[i])
            rcf[i] = env.now
            rec["busy_min"] += work[i]
            rec["kg"] += kg[i]
            rec["awbs"] += 1

    def start_crew(size: int, end: float, rec: dict) -> list:
        crew = []
        for _ in range(size):
            state = [None]
            crew.append((env.process(worker(end, rec, state)), state))
        return crew

    def send_home(crew: list) -> None:
        for proc, state in crew:
            req = state[0]
            if proc.is_alive and req is not None and not req.triggered:
                proc.interrupt()

    def manager():
        crew: list = []
        day = 0
        while True:
            for k, s in enumerate(starts):
                t = day * 1440 + s * 60
                if t >= horizon:
                    send_home(crew)
                    return
                if t > env.now:
                    yield env.timeout(t - env.now)
                send_home(crew)
                wd = (t0_weekday + day) % 7
                r = int(roster[wd, k])
                u = rng.random(slots)
                present = r - int((u[:r] < p_abs).sum())
                rec = {"start_min": t, "day": day, "weekday": wd, "shift": k, "rostered": r, "present": present,
                       "busy_min": 0.0, "kg": 0.0, "awbs": 0}
                shift_rows.append(rec)
                crew = start_crew(present, t + shift_len, rec)
            day += 1

    def flex_monitor():
        free_at = 0.0
        while env.now + 15 < horizon:
            yield env.timeout(15)
            if env.now >= free_at and len(store.items) >= flex["backlog_trigger"]:
                on = env.now + flex["lead_time_min"]
                off = on + flex["block_hours"] * 60
                free_at = off
                env.process(flex_block(on, off))

    def flex_block(on: float, off: float):
        if on >= horizon:
            return
        yield env.timeout(on - env.now)
        rec = {"start_min": on, "staff": flex["pool_size"], "minutes": off - on, "busy_min": 0.0, "kg": 0.0, "awbs": 0}
        flex_rows.append(rec)
        crew = start_crew(flex["pool_size"], off, rec)
        yield env.timeout(min(off, horizon) - env.now)
        send_home(crew)

    env.process(feeder())
    env.process(manager())
    if flex:
        env.process(flex_monitor())
    env.run(until=horizon)

    shifts = pd.DataFrame(shift_rows)
    flexdf = pd.DataFrame(flex_rows, columns=["start_min", "staff", "minutes", "busy_min", "kg", "awbs"])
    return SimResult(rcf=rcf, bd_start=bd_start, shifts=shifts, flex=flexdf)


def nfd_and_late(pt: dict, sim: SimResult, sla_min: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """NFD time and the late flag (NFD after ARR plus the promise). Work not finished by the horizon counts as late."""
    nfd = sim.rcf + pt["doc"]
    late = ~(nfd <= pt["arr"] + sla_min)
    return nfd, late
