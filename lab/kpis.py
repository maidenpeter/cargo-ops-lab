"""KPI computations. The SQL lives in sql/kpis.sql; this module runs it and holds the KPI dictionary."""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import duckdb
import pandas as pd

from lab import config as C

_PARAM = re.compile(r"\$([A-Za-z_]\w*)")


@lru_cache(maxsize=None)
def blocks(path: str | Path) -> dict[str, str]:
    """Named SQL blocks from a file. A block starts at a line '-- name: <key>' and runs to the next one."""
    out, name, buf = {}, None, []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        m = re.match(r"^--\s*name:\s*(\w+)", line)
        if m:
            if name:
                out[name] = "\n".join(buf).strip()
            name, buf = m.group(1), []
        elif name is not None:
            buf.append(line)
    if name:
        out[name] = "\n".join(buf).strip()
    return out


def body(sql: str) -> str:
    """The SQL without its leading comment lines (for display)."""
    return "\n".join(l for l in sql.splitlines() if not l.startswith("--")).strip()


def params(sql: str, **extra) -> dict:
    """Named parameters a statement uses, filled from the config (plus any extras)."""
    cfg = C.load()
    known = {"cutoff": C.cutoff().to_pydatetime(), "offset_h": int(cfg["hub_utc_offset_hours"]),
             "tol": float(cfg["weight_tolerance"]), "tol_kg": float(cfg["weight_tolerance_min_kg"]), "grace_h": int(cfg["missing_grace_hours"]),
             "shift_hours": int(cfg["shifts"]["hours"]), "window_h": int(cfg["model"]["wave_window_hours"]), **extra}
    return {k: known[k] for k in dict.fromkeys(_PARAM.findall(sql))}


def run(con: duckdb.DuckDBPyConnection, file: str, name: str, fmt: dict | None = None, **extra) -> pd.DataFrame | None:
    sql = blocks(C.SQL / file)[name]
    if fmt:
        sql = sql.format(**fmt)
    p = params(sql, **extra)
    rel = con.execute(sql, p) if p else con.execute(sql)
    try:
        return rel.df()
    except duckdb.Error:
        return None


def register_reference(con: duckdb.DuckDBPyConnection) -> None:
    """Promise per product and the product code list, as tables."""
    from lab.defects import PRODUCT_CODES

    sla = pd.DataFrame({"product": list(C.load()["sla_hours"]), "sla_h": list(C.load()["sla_hours"].values())})
    con.register("sla_df", sla)
    con.execute("CREATE OR REPLACE TABLE sla AS SELECT * FROM sla_df")
    pc = pd.DataFrame({"code": list(PRODUCT_CODES.values()), "product": list(PRODUCT_CODES.keys())})
    con.register("pc_df", pc)
    con.execute("CREATE OR REPLACE TABLE product_codes AS SELECT * FROM pc_df")


def prepare(con: duckdb.DuckDBPyConnection, name: str, source: str) -> None:
    run(con, "kpis.sql", "prepare", {"name": name, "source": source})


def kpi(con, name: str, awb: str = "awb", shifts: str = "shift_log", **fmt) -> pd.DataFrame:
    return run(con, "kpis.sql", name, {"awb": awb, "shifts": shifts, **fmt})


def on_time(con, awb: str) -> float:
    return float(kpi(con, "nfd_on_time", awb)["value"].iloc[0])


# ---------------------------------------------------------------- the KPI dictionary
DICTIONARY = [
    {"kpi": "nfd_on_time", "name": "NFD on time %",
     "definition": "Share of AWBs notified ready for pickup within the promise for their product, counted from aircraft arrival.",
     "formula": "AWBs with NFD at or before ARR + promise / AWBs whose promise fell due before the cut-off",
     "owner": "Handler", "decision": "How many staff each shift needs, and which arrivals supervisors should watch.",
     "cut_by": "product, carrier, arrival shift, arrival hour"},
    {"kpi": "handler_time", "name": "Handler time p50 and p90",
     "definition": "Hours from aircraft arrival to freight ready (ARR to NFD): the median and the slowest tenth.",
     "formula": "50th and 90th percentile of NFD - ARR, in hours, over AWBs with an NFD",
     "owner": "Handler", "decision": "Whether the promise is realistic, and whether the tail or the typical AWB needs work.",
     "cut_by": "product"},
    {"kpi": "customer_time", "name": "Customer time p50 and p90",
     "definition": "Hours from freight ready to delivery (NFD to DLV): customs holds, document checks and forwarder pickup.",
     "formula": "50th and 90th percentile of DLV - NFD, in hours, over AWBs notified at least 7 days before the cut-off",
     "owner": "Customer", "decision": "Storage pricing and pickup reminders; not a terminal performance measure.",
     "cut_by": "product"},
    {"kpi": "dwell_split", "name": "Handler share of dwell",
     "definition": "Of the total time freight sits between arrival and delivery, the share on the handler's clock.",
     "formula": "Sum of (NFD - ARR) / sum of (DLV - ARR)",
     "owner": "Both", "decision": "Who to talk to about long dwell: the floor or the forwarder.",
     "cut_by": "product"},
    {"kpi": "throughput", "name": "Breakdown throughput",
     "definition": "Kilograms broken down per present staff hour.",
     "formula": "Kg broken down in the shift / (present staff x shift hours)",
     "owner": "Handler", "decision": "Productivity by shift, and the work rate a roster plan should assume.",
     "cut_by": "shift"},
    {"kpi": "backlog_at_shift_end", "name": "Backlog at shift end",
     "definition": "AWBs that had arrived but were not yet received from the flight (no RCF) when a shift ended.",
     "formula": "AWBs with ARR before the shift end - AWBs with RCF before the shift end",
     "owner": "Handler", "decision": "Whether one shift is handing its work to the next.",
     "cut_by": "shift"},
    {"kpi": "late_per_1000", "name": "Late shipments per 1,000 AWBs",
     "definition": "Late AWBs for every thousand scored, the same measure as on-time % read as a count.",
     "formula": "1,000 x late AWBs / scored AWBs",
     "owner": "Handler", "decision": "A count that operations and sales can both quote without converting percentages.",
     "cut_by": "product"},
    {"kpi": "completeness", "name": "Data completeness",
     "definition": "Share of AWBs with all four milestones present and in order (ARR, RCF, NFD, DLV).",
     "formula": "AWBs with ARR <= RCF <= NFD <= DLV all present / AWBs that arrived at least 14 days before the cut-off",
     "owner": "Data", "decision": "Whether the milestone feed can be trusted for the other measures this month.",
     "cut_by": "feed as received, and after cleaning"},
]


def dictionary() -> pd.DataFrame:
    sql = blocks(C.SQL / "kpis.sql")
    d = pd.DataFrame(DICTIONARY)
    d["sql"] = d["kpi"].map(lambda k: body(sql[k]))
    return d
