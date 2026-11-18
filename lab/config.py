"""Reads config.yml, and lists every assumption with its one-line comment for the Methods page."""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config.yml"
DATA = ROOT / "data"
LOGS = DATA / "logs"
SQL = ROOT / "sql"

SYNTHETIC = "Synthetic terminal. Illustrative only."


@lru_cache(maxsize=1)
def load() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


_LINE = re.compile(r"^(?P<ind>\s*)(?P<key>[A-Za-z_][\w]*):\s*(?P<val>[^#]*?)\s*(#\s*(?P<note>.*))?$")


def assumptions() -> pd.DataFrame:
    """Every config key with its value and comment, in file order.

    Parent keys that only group others keep their comment and show no value. The timetable rows are listed
    on their own (see timetable()).
    """
    rows, stack = [], []
    for raw in CONFIG_PATH.read_text(encoding="utf-8").splitlines():
        if not raw.strip() or raw.lstrip().startswith("#") or raw.lstrip().startswith("-"):
            continue
        m = _LINE.match(raw)
        if not m:
            continue
        indent = len(m["ind"])
        while stack and stack[-1][0] >= indent:
            stack.pop()
        stack.append((indent, m["key"]))
        path = ".".join(k for _, k in stack)
        val = m["val"].strip().strip('"')
        rows.append({"key": path, "value": val, "note": (m["note"] or "").strip(), "group": stack[0][1]})
    return pd.DataFrame(rows)


def timetable() -> pd.DataFrame:
    return pd.DataFrame(load()["timetable"])


def sla_minutes() -> dict[str, float]:
    return {p: h * 60.0 for p, h in load()["sla_hours"].items()}


def legacy_roster():
    """Legacy headcount as a 7 x 3 array: weekday (Monday first) by shift (morning, afternoon, night)."""
    import numpy as np

    c = load()
    return np.array([c["legacy_roster"][s] for s in c["shifts"]["names"]], dtype=int).T


def cutoff() -> pd.Timestamp:
    return pd.Timestamp(load()["window"]["cutoff"]) + pd.Timedelta(days=1)  # end of the cut-off day


def start() -> pd.Timestamp:
    return pd.Timestamp(load()["window"]["start"])
