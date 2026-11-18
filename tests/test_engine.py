"""Sanity bounds on the simulation engine."""
import numpy as np

from lab import config as C
from lab import disruption as X
from lab import roster as R
from lab import schedule as S
from lab import terminal as T


def _run(bundle, roster, seed=0):
    pt = S.process_times(bundle.awbs, bundle.t0, seed)
    sim = T.simulate(pt, bundle.t0.weekday(), roster, seed, bundle.horizon)
    sla = bundle.awbs["product"].map(C.sla_minutes()).to_numpy(float)
    _, late = T.nfd_and_late(pt, sim, sla)
    w = (pt["arr"] >= bundle.win_start) & (pt["arr"] < bundle.win_end)
    return pt, sim, late, w


def test_simulation_is_reproducible_from_the_seed(short_arrivals):
    f, a, start, end = short_arrivals
    b = R.make_bundle("t", f, a, start, end)
    _, s1, _, _ = _run(b, C.legacy_roster(), seed=3)
    _, s2, _, _ = _run(b, C.legacy_roster(), seed=3)
    _, s3, _, _ = _run(b, C.legacy_roster(), seed=4)
    assert np.array_equal(s1.rcf, s2.rcf, equal_nan=True)
    assert s1.shifts.equals(s2.shifts)
    assert not np.array_equal(s1.rcf, s3.rcf, equal_nan=True)


def test_unlimited_headcount_leaves_almost_nothing_late(short_arrivals):
    f, a, start, end = short_arrivals
    b = R.make_bundle("t", f, a, start, end)
    _, _, late, w = _run(b, np.full((7, 3), 200))
    # only what tow, offload and the document check alone push past the promise remains
    assert late[w].mean() < 0.01


def test_one_person_per_shift_lets_backlog_grow(short_arrivals):
    f, a, start, end = short_arrivals
    b = R.make_bundle("t", f, a, start, end)
    pt, sim, late, w = _run(b, np.ones((7, 3), dtype=int))

    def backlog(t):
        bd = ~pt["intact"]
        return int(((pt["ready"] <= t) & bd).sum() - ((sim.rcf <= t) & bd).sum())

    day = 1440
    assert backlog(b.win_start + 14 * day) > backlog(b.win_start + 4 * day) > 100
    assert late[w].mean() > 0.5


def test_no_disruption_reproduces_the_base_case(short_arrivals):
    f, a, start, end = short_arrivals
    base = R.make_bundle("base", f, a, start, end)
    scen = X.bundles(f, a, start, end)[X.key(0.0, 0.0)]
    assert base.awbs[R.SLIM].equals(scen.awbs[R.SLIM])
    for roster in (C.legacy_roster(), np.full((7, 3), 9)):
        e1 = R.evaluate(base, roster, 0)
        R._PT.clear()
        e2 = R.evaluate(scen, roster, 0)
        assert np.array_equal(e1["late_c"], e2["late_c"]) and e1["staff_hours"] == e2["staff_hours"]


def test_disruption_moves_flights_and_cuts_volume(short_arrivals):
    f, a, start, end = short_arrivals
    win = (f["sched_arr"] >= start) & (f["sched_arr"] < end)
    fw, aw = f[win].reset_index(drop=True), a[a["flight_key"].isin(f.loc[win, "flight_key"])].reset_index(drop=True)
    f2, a2 = S.disrupt(fw, aw, 0.4, -0.2)
    assert 0.3 < f2["rescheduled"].mean() < 0.5
    assert 0.75 < len(a2) / len(aw) < 0.85
    f4, _ = S.disrupt(fw, aw, 0.6, 0.0)
    moved40 = set(f2.loc[f2["rescheduled"], "flight_key"])
    assert moved40 <= set(f4.loc[f4["rescheduled"], "flight_key"])  # nested scenarios
