"""One shipment's record in plain words: the lookup behind the Legal desk, the story and the chat.

Everything here reads the stored result files (data/awb_clean.parquet, data/dq_quarantine.parquet and
data/model_predictions.parquet); nothing is simulated in the app.
"""
from __future__ import annotations

import re

import pandas as pd
import streamlit as st

from lab import config as C
from lab import ui

ID = re.compile(r"\bAWB\s?(\d{7})\b", re.IGNORECASE)
REASONS = {"NFD before RCF": "the steps are out of order (ready before checked in)",
           "missing NFD": "the message saying it was ready is missing",
           "missing RCF": "the message saying it was checked in is missing",
           "unknown product": "the type-of-cargo code is not one the terminal uses",
           "weight mismatch": "the weight on the paperwork is far from the weight measured at check-in"}
UNIT = {"bup_breakdown": "in a container that had to be unpacked", "bup_intact": "in a container passed on unopened",
        "loose": "as loose pieces"}


def find_id(text: str) -> str | None:
    """The first shipment number in a piece of text, written the way the lab writes it (AWB and seven digits)."""
    m = ID.search(text or "")
    return f"AWB{m.group(1)}" if m else None


def _stamp(name: str) -> float:
    p = C.DATA / name
    return p.stat().st_mtime if p.exists() else 0.0


@st.cache_resource(show_spinner=False)
def _book(stamp: float) -> pd.DataFrame:
    a = pd.read_parquet(C.DATA / "awb_clean.parquet")
    a["awb_id"] = a["awb_id"].astype(str)
    return a.set_index("awb_id")


@st.cache_resource(show_spinner=False)
def _aside(stamp: float) -> pd.Series:
    q = pd.read_parquet(C.DATA / "dq_quarantine.parquet")
    return q.assign(awb_id=q["awb_id"].astype(str)).set_index("awb_id")["quarantine_reason"]


@st.cache_resource(show_spinner=False)
def _scores(stamp: float) -> pd.DataFrame:
    p = pd.read_parquet(C.DATA / "model_predictions.parquet")
    chosen = ui.table("model_meta").set_index("key")["value"]["chosen"]
    p["score"] = p["p_hgb" if chosen == "Gradient boosting" else "p_lr"]
    p["rank"] = p["score"].rank(pct=True)
    p["awb_id"] = p["awb_id"].astype(str)
    return p.set_index("awb_id")


def book() -> pd.DataFrame:
    return _book(_stamp("awb_clean.parquet"))


def aside() -> pd.Series:
    return _aside(_stamp("dq_quarantine.parquet"))


def scores() -> pd.DataFrame:
    return _scores(_stamp("model_predictions.parquet"))


def flag_cut() -> float:
    """The score above which a shipment is on the fast-track list (the riskiest share set in the config)."""
    return float(scores()["score"].quantile(1 - C.load()["model"]["expedite_share"]))


def dur(minutes: float) -> str:
    m = int(round(abs(minutes)))
    h, r = divmod(m, 60)
    if h and r:
        return f"{h} h {r} min"
    return f"{h} h" if h else f"{r} min"


def when(ts: pd.Timestamp, weekday: bool = True, year: bool = True) -> str:
    """A date the way people write it: Wednesday 1 July 2026."""
    s = f"{ts.day} {ts:%B}" + (f" {ts.year}" if year else "")
    return f"{ts:%A} {s}" if weekday else s


def short_when(ts: pd.Timestamp, year: bool = False) -> str:
    """A compact date and time for tables: Wed 1 Jul, 00:33."""
    return f"{ts:%a} {ts.day} {ts:%b}" + (f" {ts.year}" if year else "") + f", {ts:%H:%M}"


def shift_of(ts: pd.Timestamp) -> tuple[int, int]:
    """(weekday, shift index) of the shift on duty at a moment. A night shift belongs to the day it starts."""
    sh = C.load()["shifts"]
    starts, hours = sh["starts"], sh["hours"]
    for i, s in enumerate(starts):
        t0 = ts.normalize() + pd.Timedelta(hours=s)
        for back in (0, 1):
            start = t0 - pd.Timedelta(days=back)
            if start <= ts < start + pd.Timedelta(hours=hours):
                return int(start.weekday()), i
    return int(ts.weekday()), 0


def record(awb_id: str) -> dict:
    """Everything the lab knows about one shipment, with the promise worked out."""
    awb_id = (awb_id or "").strip().upper().replace(" ", "")
    b = book()
    if awb_id in b.index:
        r = b.loc[awb_id]
        cfg = C.load()
        sla = float(cfg["sla_hours"][str(r["product"])])
        due = r["arr_ts"] + pd.Timedelta(hours=sla)
        scored = bool(due < C.cutoff())
        nfd, dlv = r["nfd_ts"], r["dlv_ts"]
        rec = {"id": awb_id, "status": "kept", "flight": str(r["flight"]), "carrier": str(r["carrier"]),
               "aircraft": "freighter" if str(r["flight_type"]) == "freighter" else "passenger plane",
               "region": str(r["region"]), "product": str(r["product"]),
               "product_label": ui.PRODUCT_LABELS[str(r["product"])], "unit": UNIT.get(str(r["handling_unit"]), ""),
               "pieces": int(r["pieces"]), "weight": float(r["weight_kg"]), "sched": r["sched_arr"], "arr": r["arr_ts"],
               "rcf": r["rcf_ts"], "nfd": nfd, "dlv": dlv, "sla_h": sla, "due": due, "scored": scored,
               "on_time": bool(pd.notna(nfd) and nfd <= due) if scored else None,
               "margin_min": (due - nfd).total_seconds() / 60 if pd.notna(nfd) else None,
               "terminal_min": (nfd - r["arr_ts"]).total_seconds() / 60 if pd.notna(nfd) else None,
               "customer_min": (dlv - nfd).total_seconds() / 60 if pd.notna(dlv) and pd.notna(nfd) else None}
        s = scores()
        if awb_id in s.index:
            rec["score"] = float(s.loc[awb_id, "score"])
            rec["rank"] = float(s.loc[awb_id, "rank"])
            rec["flagged"] = rec["score"] >= flag_cut()
            rec["backlog"] = float(s.loc[awb_id, "backlog_at_arr"])
            rec["due_next_2h"] = float(s.loc[awb_id, "sched_awbs_next_2h"])
        return rec
    q = aside()
    if awb_id in q.index:
        reason = str(q.loc[awb_id])
        return {"id": awb_id, "status": "set_aside", "reason": REASONS.get(reason, reason)}
    return {"id": awb_id, "status": "unknown"}


def verdict(rec: dict) -> list[str]:
    """The record in plain sentences, the way a reader with no cargo background would want it."""
    if rec["status"] == "unknown":
        return [f"No shipment numbered {rec['id']} landed in the lab's data. Shipment numbers run from AWB0000001 "
                f"upward."]
    if rec["status"] == "set_aside":
        return [f"The data checks set this record aside because {rec['reason']}.",
                "Its times should not be relied on until someone reviews the original messages. It is left out of "
                "every measure in the lab."]
    out = [f"The terminal promised to have this shipment of {ui.PRODUCT_NOUNS[rec['product']]} ready within "
           f"{rec['sla_h']:g} hours of landing, that is, by {rec['due']:%H:%M} on {when(rec['due'])}."]
    if not rec["scored"]:
        out.append("The promise had not yet run out when the lab's data ends, so it is not judged either way.")
    elif rec["on_time"]:
        out.append(f"It was ready at {rec['nfd']:%H:%M}, {dur(rec['margin_min'])} inside the promise. On the record, "
                   f"the terminal kept its promise.")
    else:
        out.append(f"It was ready at {rec['nfd']:%H:%M} on {when(rec['nfd'], False, False)}, {dur(rec['margin_min'])} after the promise ran out. "
                   f"On the record, the terminal missed its promise.")
    if rec["customer_min"] is not None:
        out.append(f"The customer collected it at {rec['dlv']:%H:%M} on {when(rec['dlv'], False, False)}, {dur(rec['customer_min'])} after it was "
                   f"ready. That time is on the customer's clock (customs, paperwork and pickup), and the promise does "
                   f"not cover it.")
    elif pd.notna(rec.get("nfd")):
        out.append("The record shows no collection before the data ends.")
    out.append("The record passed every data check, so its times can be relied on.")
    return out


def file_text(rec: dict) -> str:
    """A plain text shipment file to download and keep with a claim."""
    lines = [f"Shipment file: {rec['id']}", ui.SYNTHETIC, ""]
    if rec["status"] == "kept":
        lines += [f"Flight: {rec['flight']} ({rec['carrier']}, {rec['aircraft']} from {rec['region']})",
                  f"Cargo: {rec['product_label']}, {rec['pieces']} pieces, {rec['weight']:,.1f} kg, {rec['unit']}",
                  f"Scheduled landing: {rec['sched']:%Y-%m-%d %H:%M}",
                  f"Landed: {rec['arr']:%Y-%m-%d %H:%M}",
                  f"Checked in: {rec['rcf']:%Y-%m-%d %H:%M}" if pd.notna(rec["rcf"]) else "Checked in: not recorded",
                  f"Ready to collect: {rec['nfd']:%Y-%m-%d %H:%M}" if pd.notna(rec["nfd"]) else "Ready to collect: not recorded",
                  f"Collected: {rec['dlv']:%Y-%m-%d %H:%M}" if pd.notna(rec["dlv"]) else "Collected: not recorded",
                  f"Promise: {rec['sla_h']:g} hours from landing, due {rec['due']:%Y-%m-%d %H:%M}", ""]
    lines += verdict(rec)
    lines += ["", "Times are hub local time. This file is generated from a simulation and is not legal advice."]
    return "\n".join(lines) + "\n"


def examples() -> dict[str, str]:
    """A shipment for each kind of case the Legal desk explains, picked by a fixed rule from the stored records."""
    b = book()
    cut = C.cutoff()
    sla = pd.Series(C.load()["sla_hours"])
    due = b["arr_ts"] + pd.to_timedelta(b["product"].astype(str).map(sla).astype(float), unit="h")
    scored = due < cut
    late = scored & (b["nfd_ts"] > due)
    on = scored & (b["nfd_ts"] <= due)
    wait = (b["dlv_ts"] - b["nfd_ts"]).dt.total_seconds()
    out = {"A late shipment": b.index[late][0], "An on-time shipment": b.index[on][0],
           "On time, then a long wait for the customer": wait[on].idxmax()}
    q = aside()
    if len(q):
        out["A record the data checks set aside"] = sorted(q.index)[0]
    return out


def story_pick() -> str | None:
    """The shipment the overview's story follows: the earliest late shipment in the test months that the
    early-warning model put on its fast-track list. A fixed rule, so the story is not chosen to flatter."""
    s = scores()
    hit = s[(s["late"] == 1) & (s["score"] >= flag_cut())].sort_values("arr_ts")
    for awb_id in hit.index:
        if awb_id in book().index:
            return awb_id
    return None
