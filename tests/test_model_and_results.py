"""Leakage guard, split separation, and the headline file against a fresh recomputation."""
import math

import numpy as np
import pandas as pd
import pytest

from lab import config as C
from lab import headline, model, readme
from lab import roster as R
from lab import schedule as S


def test_no_post_arrival_feature_in_the_model():
    assert not set(model.FEATURES) & set(model.FORBIDDEN)
    for f in model.FEATURES:
        for bad in ("rcf", "nfd", "dlv", "present", "checked", "bd_", "breakdown", "late"):
            assert bad not in f, f
    assert "rostered_headcount" in model.FEATURES and "present" not in " ".join(model.FEATURES)


def test_feature_list_used_in_the_build_matches(results_ready):
    meta = pd.read_parquet(C.DATA / "model_meta.parquet").set_index("key")["value"]
    assert meta["features"].split(", ") == model.FEATURES


def test_train_validation_and_test_months_do_not_overlap(results_ready):
    meta = pd.read_parquet(C.DATA / "model_meta.parquet").set_index("key")["value"]
    d = {k: pd.Timestamp(meta[k]) for k in meta.index if k.endswith(("_from", "_to"))}
    assert d["train_to"] < d["valid_from"] <= d["valid_to"] < d["test_from"] <= d["test_to"]
    split = C.load()["split"]
    assert d["train_to"] <= pd.Timestamp(split["train_end"]) and d["valid_to"] <= pd.Timestamp(split["valid_end"])
    df = pd.DataFrame({"arr_ts": pd.date_range("2025-04-01", "2026-09-30 23:00", freq="7h")})
    parts = model.split(df)
    assert sum(len(p) for p in parts.values()) == len(df)
    assert parts["train"]["arr_ts"].max() < parts["valid"]["arr_ts"].min()
    assert parts["valid"]["arr_ts"].max() < parts["test"]["arr_ts"].min()


def _close(a, b) -> bool:
    if isinstance(a, float) or isinstance(b, float):
        return math.isclose(float(a), float(b), rel_tol=1e-9, abs_tol=1e-12)
    return a == b


def test_headline_matches_a_fresh_recomputation(results_ready):
    stored = headline.read()
    fresh = headline.compute()
    for k, v in fresh.items():
        if k == "sentences":
            assert stored[k] == v
        else:
            assert _close(stored[k], v), k


def test_headline_roster_numbers_rebuild_from_the_simulation(results_ready):
    """Re-simulate the legacy roster on the test months and compare with the stored result."""
    cfg = C.load()
    flights = pd.read_parquet(C.LOGS / "flights.parquet")
    awbs = S.build_awbs(flights, S.rng_for(2))
    start = pd.Timestamp(cfg["split"]["valid_end"]) + pd.Timedelta(days=1)
    b = R.make_bundle("base", flights, awbs, start, C.cutoff())
    res = [R.evaluate(b, C.legacy_roster(), s) for s in range(cfg["roster_opt"]["seeds"])]
    sm = R.summarize(res, b.weeks)
    h = headline.read()
    assert sm["on_time"] == pytest.approx(h["legacy_on_time"], abs=1e-12)
    assert sm["staff_hours_per_week"] == pytest.approx(h["legacy_hours_week"])


def test_replanning_with_no_disruption_reproduces_the_plan(results_ready):
    ros = pd.read_parquet(C.DATA / "rosters.parquet")
    drs = pd.read_parquet(C.DATA / "disruption_rosters.parquet")
    plan = ros[ros["policy"] == "optimized"].sort_values(["weekday", "shift"])["headcount"].to_numpy()
    same = drs[drs["scenario"] == "s00_v00"].sort_values(["weekday", "shift"])["headcount"].to_numpy()
    assert np.array_equal(plan, same)
    dis = pd.read_parquet(C.DATA / "disruption.parquet").set_index(["scenario", "policy"])
    ev = pd.read_parquet(C.DATA / "roster_eval.parquet").set_index("policy")
    assert dis.loc[("s00_v00", "static"), "on_time"] == pytest.approx(ev.loc["optimized", "on_time"], abs=1e-12)
    assert dis.loc[("s00_v00", "replanned"), "on_time"] == pytest.approx(ev.loc["optimized", "on_time"], abs=1e-12)
    assert dis.loc[("s00_v00", "legacy"), "on_time"] == pytest.approx(ev.loc["legacy", "on_time"], abs=1e-12)


def test_readme_numbers_come_from_the_headline_file(results_ready):
    """The README is rendered from its template with headline.json; it must match a fresh render."""
    assert (C.ROOT / "README.md").read_text(encoding="utf-8") == readme.render(headline.compute())
