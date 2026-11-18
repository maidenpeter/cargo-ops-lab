"""Risk of missing the ready-time promise, scored at aircraft arrival.

Features come from sql/features.sql. The split is by arrival date: train, then validation months, then test months.
Two models: a logistic regression baseline and a histogram gradient boosting classifier.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from lab import config as C
from lab import kpis

# scikit-learn is imported inside the functions that fit or score, so the app can read this module without it.

CATEGORICAL = ["product", "handling_unit", "carrier", "flight_type", "region"]
NUMERIC = ["pieces", "weight_kg", "arr_hour", "arr_weekday", "delay_min", "rostered_headcount",
           "backlog_at_arr", "sched_awbs_next_2h"]
FEATURES = CATEGORICAL + NUMERIC
# Known only after arrival, or a direct read of the outcome. None of these may be a feature.
FORBIDDEN = ["rcf_ts", "nfd_ts", "dlv_ts", "due_ts", "late", "present", "present_headcount", "bd_start",
             "breakdown_start", "weight_checked_kg", "handler_time", "customer_time", "customs_hold", "customer_min"]

LABELS = {
    "product": "Product", "handling_unit": "Handling unit", "carrier": "Carrier", "flight_type": "Aircraft type",
    "region": "Origin region", "pieces": "Pieces", "weight_kg": "Weight", "arr_hour": "Arrival hour",
    "arr_weekday": "Arrival weekday", "delay_min": "Arrival delay", "rostered_headcount": "Rostered crew on shift",
    "backlog_at_arr": "Backlog at arrival", "sched_awbs_next_2h": "AWBs due in the next 2 hours",
}


def features(con, awb: str, flights: str, roster: str) -> pd.DataFrame:
    df = kpis.run(con, "features.sql", "features", {"awb": awb, "flights": flights, "roster": roster})
    return categorize(df)


def categorize(df: pd.DataFrame) -> pd.DataFrame:
    cfg = C.load()
    levels = {
        "product": list(cfg["products"]),
        "handling_unit": ["bup_breakdown", "bup_intact", "loose"],
        "carrier": sorted({r["carrier"] for r in cfg["timetable"]}),
        "flight_type": ["belly", "freighter"],
        "region": sorted({r["region"] for r in cfg["timetable"]}),
    }
    df = df.copy()
    for c, lv in levels.items():
        df[c] = pd.Categorical(df[c], categories=lv)
    for c in NUMERIC:
        df[c] = df[c].astype(float)
    return df


def split(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    cfg = C.load()["split"]
    d = df["arr_ts"]
    tr_end = pd.Timestamp(cfg["train_end"]) + pd.Timedelta(days=1)
    va_end = pd.Timestamp(cfg["valid_end"]) + pd.Timedelta(days=1)
    return {"train": df[d < tr_end], "valid": df[(d >= tr_end) & (d < va_end)], "test": df[d >= va_end]}


def logistic():
    from sklearn.compose import ColumnTransformer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import FunctionTransformer, OneHotEncoder, StandardScaler

    pre = ColumnTransformer([
        ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL + ["arr_hour", "arr_weekday"]),
        ("log", Pipeline([("log", FunctionTransformer(np.log1p)), ("sc", StandardScaler())]), ["pieces", "weight_kg"]),
        ("num", StandardScaler(), ["delay_min", "rostered_headcount", "backlog_at_arr", "sched_awbs_next_2h"]),
    ])
    return Pipeline([("pre", pre), ("lr", LogisticRegression(max_iter=3000, C=1.0))])


def boosting():
    from sklearn.ensemble import HistGradientBoostingClassifier

    h = C.load()["model"]["hgb"]
    return HistGradientBoostingClassifier(categorical_features="from_dtype", random_state=C.load()["seed"] % 2**31,
                                          early_stopping=False, **h)


def capture(y: np.ndarray, p: np.ndarray, share: float) -> tuple[float, float]:
    """Expedite the riskiest `share` of AWBs: the share of all late AWBs caught, and the late rate among those expedited."""
    n = max(1, int(round(share * len(p))))
    top = np.argsort(-p, kind="stable")[:n]
    caught = y[top].sum()
    return caught / max(1, y.sum()), caught / n


def calibration(y: np.ndarray, p: np.ndarray, bins: int) -> pd.DataFrame:
    q = pd.qcut(pd.Series(p).rank(method="first"), bins, labels=False)
    return (pd.DataFrame({"bin": q, "p": p, "y": y}).groupby("bin")
            .agg(mean_pred=("p", "mean"), observed=("y", "mean"), n=("y", "size")).reset_index())


def fit_and_score(df: pd.DataFrame) -> dict:
    from sklearn.inspection import permutation_importance
    from sklearn.metrics import brier_score_loss, roc_auc_score

    cfg = C.load()["model"]
    s = split(df)
    X = {k: v[FEATURES] for k, v in s.items()}
    y = {k: v["late"].to_numpy() for k, v in s.items()}
    models = {"Logistic regression": logistic(), "Gradient boosting": boosting()}
    rows, cal, preds = [], [], {}
    for name, m in models.items():
        m.fit(X["train"], y["train"])
        for part in ("valid", "test"):
            p = m.predict_proba(X[part])[:, 1]
            catch, prec = capture(y[part], p, cfg["expedite_share"])
            rows.append({"model": name, "split": part, "n": len(p), "late_rate": y[part].mean(),
                         "mean_pred": p.mean(), "auc": roc_auc_score(y[part], p), "brier": brier_score_loss(y[part], p),
                         "catch_top": catch, "late_rate_top": prec})
            if part == "test":
                preds[name] = p
                c = calibration(y[part], p, cfg["calibration_bins"])
                c.insert(0, "model", name)
                cal.append(c)
    metrics = pd.DataFrame(rows)
    val = metrics[metrics["split"] == "valid"].set_index("model")
    chosen = val["auc"].idxmax()

    test = s["test"]
    pred = test[["awb_id", "arr_ts", "product", "late", "backlog_at_arr", "sched_awbs_next_2h"]].copy()
    pred["p_lr"] = preds["Logistic regression"]
    pred["p_hgb"] = preds["Gradient boosting"]

    imp = permutation_importance(models["Gradient boosting"], X["test"], y["test"], scoring="roc_auc",
                                 n_repeats=cfg["permutation_repeats"], random_state=0, n_jobs=1)
    importance = pd.DataFrame({"feature": FEATURES, "label": [LABELS[f] for f in FEATURES],
                               "mean": imp.importances_mean, "std": imp.importances_std}).sort_values("mean", ascending=False)

    shares = np.round(np.arange(0.01, 0.51, 0.01), 2)
    curve = []
    for name, col in (("Logistic regression", "p_lr"), ("Gradient boosting", "p_hgb")):
        for sh in shares:
            c, pr = capture(pred["late"].to_numpy(), pred[col].to_numpy(), sh)
            curve.append({"model": name, "share": sh, "catch": c, "late_rate_top": pr})
    sizes = {k: len(v) for k, v in s.items()}
    return {"metrics": metrics, "calibration": pd.concat(cal, ignore_index=True), "predictions": pred,
            "importance": importance, "capture_curve": pd.DataFrame(curve), "chosen": chosen,
            "models": models, "sizes": sizes,
            "months": {k: (v["arr_ts"].min(), v["arr_ts"].max()) for k, v in s.items()}}
