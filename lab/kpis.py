"""KPI computations. The SQL lives in sql/kpis.sql; this module runs it and holds the KPI dictionary."""
from __future__ import annotations

import io
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


# column widths, in characters, for the Excel copy of the dictionary; anything longer wraps inside its cell
XLSX_WIDTHS = {"kpi": 20, "name": 28, "definition": 48, "formula": 48, "owner": 10, "decision": 44, "cut_by": 30, "sql": 80}


def dictionary_xlsx(d: pd.DataFrame) -> bytes:
    """The KPI dictionary as an Excel workbook: the same columns as kpi_dictionary.csv, the header row frozen and
    the long text wrapped so the definitions and the SQL read without resizing anything."""
    from openpyxl.styles import Alignment

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xl:
        d.to_excel(xl, sheet_name="KPI dictionary", index=False)
        ws = xl.sheets["KPI dictionary"]
        ws.freeze_panes = "A2"
        for i, col in enumerate(d.columns, start=1):
            letter = ws.cell(row=1, column=i).column_letter
            ws.column_dimensions[letter].width = XLSX_WIDTHS.get(col, 20)
            for cell in ws[letter][1:]:
                cell.alignment = Alignment(wrap_text=True, vertical="top")
    return buf.getvalue()
