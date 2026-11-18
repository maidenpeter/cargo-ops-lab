"""The clean log, the reconciliation to the KPI tables, and the data quality rules."""
import pandas as pd
import pytest

from lab import config as C


@pytest.fixture(scope="module")
def truth(logs_ready):
    return pd.read_parquet(C.LOGS / "events_wide_truth.parquet")


def test_clean_log_milestones_in_order(truth):
    t = truth
    for a, b in (("arr_ts", "rcf_ts"), ("rcf_ts", "nfd_ts"), ("nfd_ts", "dlv_ts")):
        both = t[a].notna() & t[b].notna()
        assert (t.loc[both, a] <= t.loc[both, b]).all(), f"{a} after {b}"
    # a later milestone is never present without the earlier one
    assert not (t["rcf_ts"].isna() & t["nfd_ts"].notna()).any()
    assert not (t["nfd_ts"].isna() & t["dlv_ts"].notna()).any()
    ht = (t["nfd_ts"] - t["arr_ts"]).dropna()
    assert (ht >= pd.Timedelta(0)).all()


def test_awb_counts_and_weights_reconcile(truth, logs_ready):
    flights = pd.read_parquet(C.LOGS / "flights.parquet")
    arrived = flights[flights["arr"] < C.cutoff()]
    assert arrived["n_awbs"].sum() == len(truth)

    clean = pd.read_parquet(C.DATA / "awb_clean.parquet")
    outcome = pd.read_parquet(C.DATA / "dq_outcome.parquet").set_index("reason")["awbs"]
    assert outcome.sum() == len(truth)                      # every AWB is kept or quarantined, once
    assert outcome["kept"] == len(clean)

    summary = pd.read_parquet(C.DATA / "kpi_summary.parquet").set_index("kpi")["value"]
    monthly = pd.read_parquet(C.DATA / "monthly.parquet")
    assert summary["awbs"] == len(clean) == monthly["awbs"].sum()
    assert summary["tonnes"] == pytest.approx(clean["weight_kg"].sum() / 1000)
    assert monthly["tonnes"].sum() == pytest.approx(summary["tonnes"])
    # kept weight is the truth less the quarantined AWBs, to the kilogram
    q = pd.read_parquet(C.DATA / "dq_quarantine.parquet")
    assert len(q) == len(truth) - len(clean) and q["awb_id"].is_unique
    kept = truth[~truth["awb_id"].isin(q["awb_id"])]
    assert len(kept) == len(clean)
    assert clean["weight_kg"].sum() == pytest.approx(kept["weight_kg"].sum(), abs=0.5)


def test_each_rule_catches_its_defect_and_nothing_on_the_clean_log(results_ready):
    sc = pd.read_parquet(C.DATA / "dq_scorecard.parquet")
    floor = C.load()["dq_min_recall"]
    assert len(sc) == 7
    for r in sc.itertuples():
        assert r.injected > 0, r.rule
        assert r.recall >= floor, f"{r.rule} recall {r.recall:.3f}"
        assert r.flagged_on_clean == 0, f"{r.rule} flags {r.flagged_on_clean} clean AWBs"


def test_repaired_kpi_is_closer_to_truth_than_raw(results_ready):
    v = pd.read_parquet(C.DATA / "dq_versions.parquet").set_index("version")["on_time"]
    assert abs(v["Repaired"] - v["Truth"]) <= abs(v["Raw feed"] - v["Truth"])
