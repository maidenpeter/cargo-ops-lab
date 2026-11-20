"""Page frame, theme, number formats, chart helpers and data access shared by every page.

The look follows the portfolio site (maidenpeter.github.io): an ink plate with grain, IM Fell English for headings,
Old Standard TT for labels, EB Garamond for prose and numbers, IBM Plex Sans Condensed for the interface,
double-ruled frames, gold for emphasis, teal for good and oxblood for bad.
"""
from __future__ import annotations

import html
import json
import re
from contextlib import contextmanager

import duckdb
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

from lab import config as C
from lab import headline as H

APP = "Cargo Ops Lab"
TAGLINE = ("When a plane lands with cargo, how often is the freight ready for the customer on time, and how many "
           "people does each shift need to make sure it is?")
SYNTHETIC = "Synthetic terminal. Illustrative only."
PORTFOLIO = "https://maidenpeter.github.io/"
REPO = "https://github.com/maidenpeter/cargo-ops-lab"
SIBLINGS = [("Instalment Persistency Lab", "https://instalment-persistency-lab.streamlit.app/"),
            ("Health IBNR Lab", "https://maidenpeter.shinyapps.io/health-ibnr-lab/")]

# tokens from the site's ink theme
GROUND, SURFACE, SUNK = "#15253b", "#1c2f46", "#0f1d2f"
INK, INK2, MUTED = "#ede7d8", "#c4c0b4", "#9c9b94"
RULE, RULE_SOFT, RULE_STRONG = "rgba(237,231,216,.17)", "rgba(237,231,216,.09)", "rgba(237,231,216,.34)"
GOLD, GOLD_SOFT = "#f0a63a", "rgba(240,166,58,.11)"
GAIN, LOSS, GAIN_INK, LOSS_INK = "#25a3a4", "#d9694f", "#5cc9c9", "#ee8a72"
CTX, NEU = "#5e6873", "#8f98a3"
HATCH = "rgba(10,20,32,.30)"
SERIF = "'EB Garamond', Garamond, Georgia, serif"
UI = "'IBM Plex Sans Condensed', 'Arial Narrow', Arial, sans-serif"

# "q" is the plain question each page answers; the overview lists them in order
PAGES = [
    {"key": "terminal", "file": "pages/1_Terminal.py", "nav": "Overview", "url": "terminal", "icon": ":material/flight_land:",
     "num": "", "eyebrow": "A simulated airport cargo terminal", "title": APP, "q": ""},
    {"key": "kpis", "file": "pages/2_KPIs.py", "nav": "Measures", "url": "kpis", "icon": ":material/monitoring:",
     "num": "I", "eyebrow": "Measures", "title": "What counts as on time",
     "q": "How often is the freight ready on time?"},
    {"key": "dq", "file": "pages/3_Data_Quality.py", "nav": "Data checks", "url": "data-quality", "icon": ":material/rule:",
     "num": "II", "eyebrow": "Data checks", "title": "Check the records before you believe them",
     "q": "Can the records be trusted as they arrive?"},
    {"key": "risk", "file": "pages/4_Risk.py", "nav": "Early warning", "url": "risk", "icon": ":material/crisis_alert:",
     "num": "III", "eyebrow": "Early warning", "title": "Which shipments will be late",
     "q": "Can late shipments be spotted the moment the plane lands?"},
    {"key": "roster", "file": "pages/5_Roster.py", "nav": "Staffing", "url": "roster", "icon": ":material/groups:",
     "num": "IV", "eyebrow": "Staffing", "title": "How many people each shift needs",
     "q": "How many people should work each shift?"},
    {"key": "disruption", "file": "pages/6_Disruption.py", "nav": "Disruption", "url": "disruption", "icon": ":material/thunderstorm:",
     "num": "V", "eyebrow": "The twist", "title": "When the Schedule Breaks",
     "q": "What happens when the flight schedule suddenly changes?"},
    {"key": "legal", "file": "pages/8_Legal.py", "nav": "Legal desk", "url": "legal", "icon": ":material/gavel:",
     "num": "", "eyebrow": "For the legal team", "title": "Was the terminal at fault?", "q": ""},
    {"key": "ask", "file": "pages/9_Ask.py", "nav": "Ask the lab", "url": "ask", "icon": ":material/forum:",
     "num": "", "eyebrow": "Questions in plain words", "title": "Ask the lab", "q": ""},
    {"key": "methods", "file": "pages/7_Methods.py", "nav": "Methods", "url": "methods", "icon": ":material/menu_book:",
     "num": "", "eyebrow": "Appendix", "title": "Methods, assumptions and glossary", "q": ""},
]
PAGE = {p["key"]: p for p in PAGES}


# ---------------------------------------------------------------- formats
def pct(x: float, d: int = 1) -> str:
    return f"{100 * x:.{d}f}%"


def pts(x: float, d: int = 1) -> str:
    return f"{100 * x:+.{d}f} points"


def hrs(x: float, d: int = 1) -> str:
    return f"{x:.{d}f} h"


def num(x: float, d: int = 0) -> str:
    return f"{x:,.{d}f}"


def usd(x: float) -> str:
    return f"${x:,.0f}"


def weight(kg: float) -> str:
    return f"{kg / 1000:,.1f} t" if abs(kg) >= 1000 else f"{kg:,.0f} kg"


def esc(s: str) -> str:
    return html.escape(str(s), quote=False)


# ---------------------------------------------------------------- data
def _mtime(name: str) -> float:
    p = C.DATA / name
    return p.stat().st_mtime if p.exists() else 0.0


@st.cache_data(show_spinner=False)
def _table(name: str, stamp: float) -> pd.DataFrame:
    return pd.read_parquet(C.DATA / f"{name}.parquet")


def table(name: str) -> pd.DataFrame:
    return _table(name, _mtime(f"{name}.parquet"))


@st.cache_data(show_spinner=False)
def _headline(stamp: float) -> dict:
    return json.loads((C.DATA / "headline.json").read_text(encoding="utf-8"))


def headline() -> dict:
    return _headline(_mtime("headline.json"))


@st.cache_resource(show_spinner=False)
def _db(stamp: float) -> duckdb.DuckDBPyConnection:
    from lab import kpis

    con = duckdb.connect()
    kpis.register_reference(con)
    con.execute("CREATE TABLE awb_src AS SELECT CAST(carrier AS VARCHAR) AS carrier, CAST(product AS VARCHAR) AS product, "
                "CAST(handling_unit AS VARCHAR) AS handling_unit, pieces, weight_kg, arr_ts, rcf_ts, nfd_ts, dlv_ts "
                f"FROM read_parquet('{(C.DATA / 'awb_clean.parquet').as_posix()}')")
    con.execute(f"CREATE TABLE shift_log AS SELECT * FROM read_parquet('{(C.DATA / 'shift_log.parquet').as_posix()}')")
    kpis.prepare(con, "awb_all", "awb_src")
    return con


def filtered(products: list[str], carriers: list[str], shifts: list[str]) -> str:
    """A subquery over the cleaned AWBs for the KPI SQL's {awb} slot. Values come from fixed option lists."""
    q = lambda vals: ", ".join("'" + v.replace("'", "''") + "'" for v in vals)  # noqa: E731
    conds = ["TRUE"]
    if products:
        conds.append(f"product IN ({q(products)})")
    if carriers:
        conds.append(f"carrier IN ({q(carriers)})")
    if shifts:
        conds.append(f"arr_shift IN ({q(shifts)})")
    return f"(SELECT * FROM awb_all WHERE {' AND '.join(conds)}) AS f"


def db() -> duckdb.DuckDBPyConnection:
    """A cursor on the cleaned AWB table (shared, read only)."""
    return _db(_mtime("awb_clean.parquet")).cursor()


# ---------------------------------------------------------------- page frame
_FONTS = ("https://fonts.googleapis.com/css2?family=EB+Garamond:ital,wght@0,400;0,500;0,600;1,400"
          "&family=IBM+Plex+Sans+Condensed:wght@400;500;600&family=IM+Fell+English:ital@0;1&family=IM+Fell+English+SC"
          "&family=Old+Standard+TT:ital,wght@0,400;0,700;1,400&family=Pinyon+Script&display=swap")

_GRAIN = ("url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='260' height='260'%3E%3Cfilter id='n'%3E"
          "%3CfeTurbulence type='fractalNoise' baseFrequency='.85' numOctaves='3' stitchTiles='stitch'/%3E%3CfeColorMatrix "
          "values='0 0 0 0 .93 0 0 0 0 .90 0 0 0 0 .84 0 0 0 .055 0'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' "
          "filter='url(%23n)'/%3E%3C/svg%3E\")")

CSS = f"""
<style>
@import url('{_FONTS}');
:root {{
  --ground:{GROUND}; --surface:{SURFACE}; --sunk:{SUNK}; --ink:{INK}; --ink-2:{INK2}; --muted:{MUTED};
  --rule:{RULE}; --rule-soft:{RULE_SOFT}; --rule-strong:{RULE_STRONG}; --accent:{GOLD}; --accent-soft:{GOLD_SOFT};
  --gain:{GAIN}; --loss:{LOSS}; --gain-ink:{GAIN_INK}; --loss-ink:{LOSS_INK};
  --serif:"EB Garamond",Garamond,Georgia,serif; --ui:"IBM Plex Sans Condensed","Arial Narrow",Arial,sans-serif;
  --display:"IM Fell English","EB Garamond",Georgia,serif; --display-sc:"IM Fell English SC","IM Fell English",Georgia,serif;
  --label:"Old Standard TT","EB Garamond",Georgia,serif; --script:"Pinyon Script","IM Fell English",cursive;
}}
/* the ink plate: grain on every page, foxed at the edges */
.stApp {{ background-color:var(--ground); background-image:{_GRAIN}; }}
.stApp::before {{ content:""; position:fixed; inset:0; pointer-events:none; z-index:0;
  background:radial-gradient(ellipse at 50% 42%, transparent 58%, rgba(0,0,0,.30) 100%); }}
[data-testid="stMain"] {{ position:relative; z-index:1; }}

/* top bar: the seal, the app name in small capitals, the byline in script */
header[data-testid="stHeader"] {{ background:var(--ground); background-image:{_GRAIN}; height:4.4rem;
  border-bottom:3px double var(--rule-strong); }}
[data-testid="stToolbar"] {{ height:4.4rem; align-items:center; }}
img[data-testid="stHeaderLogo"] {{ height:2.9rem !important; max-height:2.9rem !important; width:auto; }}
:is([data-testid="stLogoLink"], div:has(> img.stLogo)) {{ display:grid !important; grid-template-columns:auto auto;
  grid-template-rows:auto auto; column-gap:.7rem; row-gap:0; align-items:center; text-decoration:none; height:auto !important; }}
:is([data-testid="stLogoLink"], div:has(> img.stLogo)) img {{ grid-column:1; grid-row:1 / span 2; }}
:is([data-testid="stLogoLink"], div:has(> img.stLogo))::after {{ content:"{APP}"; grid-column:2; grid-row:1; align-self:end;
  font-family:var(--display-sc); font-size:1.5rem; line-height:1.05; letter-spacing:.02em; color:var(--ink); white-space:nowrap; }}
:is([data-testid="stLogoLink"], div:has(> img.stLogo))::before {{ content:"by Marion Peter"; grid-column:2; grid-row:2;
  align-self:start; font-family:var(--script); font-size:1.15rem; line-height:1.15; color:var(--accent); white-space:nowrap; }}
a[data-testid="stTopNavLink"] {{ border-radius:2px; padding:0 .42rem !important; gap:.3rem; color:var(--ink-2) !important; }}
a[data-testid="stTopNavLink"] p {{ color:inherit !important; font-family:var(--ui); font-size:.93rem; }}
/* nine pages: below a wide screen the icons go, so every page name stays in the bar */
@media (max-width:1500px) {{ a[data-testid="stTopNavLink"] > span:has([data-testid="stIconMaterial"]) {{ display:none; }} }}
a[data-testid="stTopNavLink"] [data-testid="stIconMaterial"] {{ font-size:1.05rem !important; color:var(--accent) !important; opacity:.8; }}
a[data-testid="stTopNavLink"]:hover {{ color:var(--ink) !important; background:var(--accent-soft) !important; }}
a[data-testid="stTopNavLink"][aria-current="page"] {{ color:var(--ink) !important; background:transparent !important;
  box-shadow:inset 0 -2px 0 var(--accent); }}
@media (max-width:640px) {{
  :is([data-testid="stLogoLink"], div:has(> img.stLogo))::after {{ font-size:1.2rem; }}
  :is([data-testid="stLogoLink"], div:has(> img.stLogo))::before {{ font-size:1rem; }}
}}

.block-container {{ padding-top:6.4rem; padding-bottom:3rem; padding-left:clamp(1rem,3vw,3rem);
  padding-right:clamp(1rem,3vw,3rem); max-width:1240px; }}

/* lettering */
h1, h2 {{ font-family:var(--display) !important; font-weight:400 !important; letter-spacing:0; }}
h1 {{ font-size:clamp(2.25rem,4vw,3.15rem) !important; line-height:1.04 !important; padding-bottom:.2rem !important; }}
h2 {{ font-size:clamp(1.65rem,2.6vw,2.1rem) !important; line-height:1.1 !important; }}
h3 {{ font-family:var(--serif) !important; font-weight:500 !important; font-size:1.32rem !important; line-height:1.2 !important; }}
.stMarkdown p, .stMarkdown li {{ font-size:1.02rem; }}
.stMarkdown p.lede {{ font-size:clamp(1.15rem,1.7vw,1.32rem); }}
.stMarkdown .prose p, .stMarkdown .prose li {{ font-size:1.12rem; }}
.eyebrow {{ font-family:var(--label); font-size:.8rem; letter-spacing:.16em; text-transform:uppercase; color:var(--muted);
  margin:0 0 .35rem 0; display:flex; align-items:baseline; gap:.6rem; }}
.eyebrow .n {{ font-family:var(--display); font-size:1.25rem; letter-spacing:0; color:var(--accent); text-transform:none; }}
.synthetic {{ font-family:var(--ui); font-size:.85rem; color:var(--muted); margin:.15rem 0 1rem 0; display:flex; gap:.5rem;
  align-items:center; }}
.synthetic::before {{ content:""; width:7px; height:7px; border:1px solid var(--accent); transform:rotate(45deg); flex:none; }}
.lede {{ font-family:var(--serif); font-size:clamp(1.15rem,1.7vw,1.32rem); line-height:1.5; color:var(--ink-2); max-width:62ch;
  margin:0 0 .6rem 0; }}
.prose {{ font-family:var(--serif); font-size:1.12rem; line-height:1.55; color:var(--ink); max-width:68ch; }}
.prose p {{ margin:0 0 .8rem 0; }}
.small {{ font-family:var(--ui); font-size:.88rem; color:var(--muted); line-height:1.45; }}
.num {{ font-variant-numeric:tabular-nums lining-nums; }}

/* engraved section rule: a heavy line over a hairline, with the gold mark */
.sechead {{ position:relative; border-top:3px double var(--rule-strong); padding-top:1.1rem; margin:2.4rem 0 .9rem 0;
  max-width:72ch; }}
.sechead::before {{ content:""; position:absolute; top:-3px; left:0; width:56px; border-top:3px solid var(--accent); }}
.sechead h2 {{ margin:0 0 .35rem 0; padding:0; }}
.sechead p {{ font-family:var(--serif); font-size:1.12rem; line-height:1.5; color:var(--ink-2); margin:0; }}

/* plates: every framed box gets the double rule of a copperplate */
div[class*="st-key-plate"] {{ border:1px solid var(--rule-strong); outline:1px solid var(--rule); outline-offset:-6px;
  border-radius:2px; padding:1.15rem 1.35rem 1.1rem 1.35rem; background:color-mix(in srgb, var(--surface) 88%, transparent); }}
.plate-head h3 {{ margin:0 0 .15rem 0; padding:0; }}
.plate-head p {{ font-family:var(--ui); font-size:.92rem; color:var(--ink-2); line-height:1.45; margin:0 0 .3rem 0; }}
.note {{ border-left:3px solid var(--accent); background:var(--accent-soft); padding:.7rem 1rem; border-radius:0;
  font-family:var(--ui); font-size:.98rem; line-height:1.5; color:var(--ink); margin:.35rem 0 .2rem 0; max-width:86ch; }}
.note b {{ font-weight:600; }}
.vz-note {{ font-family:var(--ui); font-size:.84rem; line-height:1.45; color:var(--muted); border-top:1px solid var(--rule-soft);
  padding-top:.55rem; margin-top:.2rem; }}

/* the proof strip: big serif numbers in ruled cells */
.proof {{ display:grid; grid-template-columns:repeat(var(--cols,4), minmax(0,1fr)); gap:1px; background:var(--rule);
  border:1px solid var(--rule-strong); outline:1px solid var(--rule); outline-offset:-5px; border-radius:2px; overflow:hidden;
  margin:.4rem 0 .8rem 0; }}
.proof > div {{ background:var(--surface); padding:1rem 1.15rem 1.05rem 1.15rem; display:flex; flex-direction:column; gap:.2rem; min-width:0; }}
.proof .k {{ font-family:var(--label); font-size:.72rem; letter-spacing:.14em; text-transform:uppercase; color:var(--muted); }}
.proof b {{ font-family:var(--serif); font-weight:400; font-size:clamp(1.9rem,3vw,2.4rem); line-height:1.05;
  font-variant-numeric:tabular-nums lining-nums; color:var(--ink); white-space:nowrap; }}
.proof b.gain {{ color:var(--gain-ink); }} .proof b.loss {{ color:var(--loss-ink); }} .proof b.gold {{ color:var(--accent); }}
.proof span.d {{ font-family:var(--ui); font-size:.88rem; color:var(--ink-2); line-height:1.4; }}
.proof a.teaser {{ text-decoration:none; color:inherit; display:flex; flex-direction:column; gap:.3rem; height:100%; }}
.proof a.teaser .t {{ font-family:var(--serif); font-size:1.08rem; line-height:1.4; color:var(--ink); }}
.proof a.teaser .go {{ font-family:var(--label); font-size:.78rem; letter-spacing:.1em; text-transform:uppercase; color:var(--accent);
  margin-top:auto; }}
.proof a.teaser:hover .go {{ text-decoration:underline; }}
@media (max-width:900px) {{ .proof {{ grid-template-columns:repeat(2, minmax(0,1fr)); }} }}
@media (max-width:480px) {{ .proof {{ grid-template-columns:minmax(0,1fr); }} }}

/* contents cards, like the parts on the site */
.parts {{ display:grid; grid-template-columns:repeat(2, minmax(0,1fr)); gap:14px; margin:.4rem 0; }}
.part-card {{ position:relative; display:flex; flex-direction:column; gap:.25rem; padding:1rem 1.2rem 1.1rem 4.4rem;
  border:1px solid var(--rule-strong); outline:1px solid var(--rule); outline-offset:-6px; text-decoration:none !important;
  color:var(--ink) !important; transition:border-color .2s, background-color .2s; min-height:6.2rem; }}
.part-card:hover {{ border-color:var(--accent); background:var(--accent-soft); }}
.part-card .pn {{ position:absolute; left:1.2rem; top:.75rem; font-family:var(--display); font-size:2.3rem; line-height:1;
  color:var(--accent); }}
.part-card .pe {{ font-family:var(--label); font-size:.7rem; letter-spacing:.15em; text-transform:uppercase; color:var(--muted); }}
.part-card b {{ font-family:var(--display); font-weight:400; font-size:1.4rem; line-height:1.1; }}
.part-card .ps {{ font-family:var(--ui); font-size:.92rem; line-height:1.4; color:var(--ink-2); }}
@media (max-width:760px) {{ .parts {{ grid-template-columns:minmax(0,1fr); }} }}

/* two clocks */
.clocks {{ margin:.3rem 0 .2rem 0; font-family:var(--ui); }}
.clocks svg {{ width:100%; height:auto; display:block; overflow:visible; }}
.clocks-m {{ display:none; font-family:var(--ui); }}
.clocks-m .bar {{ display:flex; height:22px; border:1px solid var(--rule); margin:.2rem 0 .7rem 0; }}
.clocks-m .bar i {{ display:block; height:100%; background-image:repeating-linear-gradient(135deg, rgba(10,20,32,.35) 0 1px, transparent 1px 4px); }}
.clocks-m dl {{ display:grid; grid-template-columns:max-content minmax(0,1fr) max-content; gap:.35rem .7rem; margin:0; font-size:.95rem; }}
.clocks-m dt {{ font-family:var(--label); letter-spacing:.06em; color:var(--ink); }}
.clocks-m dd {{ margin:0; color:var(--ink-2); }}
.clocks-m dd.v {{ text-align:right; font-variant-numeric:tabular-nums; color:var(--ink); }}
.clocks-m .sw {{ display:inline-block; width:10px; height:10px; margin-right:6px; vertical-align:0; }}
@media (max-width:640px) {{ .clocks {{ display:none; }} .clocks-m {{ display:block; }} }}
.kd-cards {{ display:none; }}
.kd-card {{ border-top:1px solid var(--rule); padding:.8rem 0 .9rem 0; font-family:var(--ui); }}
.kd-card b {{ font-family:var(--serif); font-weight:500; font-size:1.15rem; color:var(--ink); }}
.kd-card .own {{ font-family:var(--label); font-size:.7rem; letter-spacing:.14em; text-transform:uppercase; color:var(--accent);
  margin-left:.5rem; }}
.kd-card p {{ margin:.3rem 0 0 0; font-size:.95rem; line-height:1.45; color:var(--ink-2); }}
.kd-card p.f {{ font-family:ui-monospace,Consolas,monospace; font-size:.82rem; color:var(--ink); }}
@media (max-width:640px) {{ .kd-table {{ display:none; }} .kd-cards {{ display:block; }} }}

/* tables and widgets */
[data-testid="stButtonGroup"] > div {{ flex-wrap:wrap; row-gap:.35rem; }}
[data-testid="stDataFrame"] {{ font-family:var(--ui); }}
.stButton button, .stDownloadButton button, [data-testid="stPageLink"] a {{ font-family:var(--label); letter-spacing:.04em; }}
[data-testid="stExpander"] details {{ border:1px solid var(--rule) !important; border-radius:2px; }}
[data-testid="stExpander"] summary p {{ font-family:var(--ui); font-size:.95rem; color:var(--ink-2); }}
label[data-testid="stWidgetLabel"] p {{ font-family:var(--label); font-size:.78rem !important; letter-spacing:.12em;
  text-transform:uppercase; color:var(--muted) !important; }}
table.ledger {{ border-collapse:collapse; width:100%; font-family:var(--ui); font-size:.95rem; }}
table.ledger th {{ font-family:var(--label); font-weight:400; font-size:.72rem; letter-spacing:.12em; text-transform:uppercase;
  color:var(--muted); text-align:right; padding:.45rem .6rem; border-bottom:1px solid var(--rule-strong); white-space:nowrap; }}
table.ledger th:first-child, table.ledger td:first-child {{ text-align:left; }}
table.ledger td {{ padding:.45rem .6rem; border-bottom:1px solid var(--rule-soft); text-align:right; color:var(--ink);
  font-variant-numeric:tabular-nums lining-nums; }}
table.ledger tr.em td {{ color:var(--ink); font-weight:600; background:var(--accent-soft); }}
table.ledger td.gain {{ color:var(--gain-ink); }} table.ledger td.loss {{ color:var(--loss-ink); }}
table.ledger th.l, table.ledger td.l {{ text-align:left; }}
table.ledger.doc {{ min-width:860px; }}
table.ledger.doc th, table.ledger.doc td {{ text-align:left; white-space:normal; vertical-align:top; line-height:1.4; }}
table.ledger.doc td:first-child {{ font-family:var(--serif); font-size:1.05rem; white-space:nowrap; }}
.scroll {{ overflow-x:auto; max-width:100%; -webkit-overflow-scrolling:touch; }}

/* the short version: question, answer and why it matters, at the top of every page */
.short {{ display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1.5fr) minmax(0,1fr); gap:1px; background:var(--rule);
  border:1px solid var(--rule-strong); outline:1px solid var(--rule); outline-offset:-6px; border-radius:2px;
  margin:.6rem 0 1.4rem 0; }}
.short > div {{ background:var(--surface); padding:1.1rem 1.3rem 1.2rem 1.3rem; min-width:0; }}
.short .k {{ display:block; font-family:var(--label); font-size:.72rem; letter-spacing:.15em; text-transform:uppercase;
  color:var(--muted); margin-bottom:.45rem; }}
.stMarkdown .short p {{ font-family:var(--serif); font-size:1.1rem; line-height:1.5; color:var(--ink-2); margin:0; }}
.short > div.a {{ background:color-mix(in srgb, var(--accent) 6%, var(--surface)); }}
.short .a .k {{ color:var(--accent); }}
.stMarkdown .short .a p {{ font-size:1.24rem; line-height:1.45; color:var(--ink); }}
.short b {{ font-weight:500; color:var(--accent); font-variant-numeric:tabular-nums lining-nums; }}
@media (max-width:900px) {{ .short {{ grid-template-columns:minmax(0,1fr); }} }}

/* under the hood: where the analyst detail starts */
.hood {{ position:relative; margin:3.2rem 0 1rem 0; padding:1.1rem 0 0 0; border-top:1px dashed var(--rule-strong); max-width:74ch; }}
.hood .k {{ font-family:var(--label); font-size:.75rem; letter-spacing:.16em; text-transform:uppercase; color:var(--accent); }}
.hood h2 {{ margin:.25rem 0 .35rem 0 !important; padding:0 !important; }}
.hood p {{ font-family:var(--serif); font-size:1.08rem; line-height:1.5; color:var(--ink-2); margin:0; }}

/* five questions, five answers on the overview */
.findings {{ border-top:3px double var(--rule-strong); margin:.5rem 0 .4rem 0; }}
a.finding {{ display:grid; grid-template-columns:3.4rem minmax(0,1fr) minmax(0,1.35fr); gap:.5rem 1.6rem; align-items:start;
  padding:1.25rem .8rem 1.3rem .6rem; border-bottom:1px solid var(--rule); text-decoration:none !important;
  color:var(--ink) !important; transition:background-color .2s; }}
a.finding:hover {{ background:var(--accent-soft); }}
.finding .pn {{ font-family:var(--display); font-size:2.4rem; line-height:.95; color:var(--accent); }}
.finding .pe {{ display:block; font-family:var(--label); font-size:.7rem; letter-spacing:.15em; text-transform:uppercase;
  color:var(--muted); margin-bottom:.35rem; }}
.finding .q {{ display:block; font-family:var(--display); font-size:clamp(1.35rem,2.1vw,1.6rem); line-height:1.15; color:var(--ink); }}
.finding .v {{ display:block; font-family:var(--serif); font-size:clamp(2rem,3.2vw,2.6rem); line-height:1;
  font-variant-numeric:tabular-nums lining-nums; color:var(--ink); }}
.finding .v.gain {{ color:var(--gain-ink); }} .finding .v.loss {{ color:var(--loss-ink); }} .finding .v.gold {{ color:var(--accent); }}
.finding .s {{ display:block; font-family:var(--serif); font-size:1.1rem; line-height:1.5; color:var(--ink-2); margin-top:.45rem; }}
.finding .go {{ display:block; font-family:var(--label); font-size:.74rem; letter-spacing:.1em; text-transform:uppercase;
  color:var(--accent); margin-top:.6rem; }}
a.finding:hover .go {{ text-decoration:underline; }}
@media (max-width:760px) {{ a.finding {{ grid-template-columns:2.4rem minmax(0,1fr); }} .finding .ans {{ grid-column:2; }}
  .finding .pn {{ font-size:2rem; }} }}

/* the story on the overview: one chapter at a time, over the shipment's own timeline */
.story {{ max-width:70ch; min-height:8.4rem; }}
.story .dots {{ display:flex; align-items:center; gap:.4rem; margin:.2rem 0 .6rem 0; }}
.story .dots i {{ width:22px; height:3px; background:var(--rule-strong); display:block; }}
.story .dots i.on {{ background:var(--accent); }}
.story .dots span {{ font-family:var(--label); font-size:.72rem; letter-spacing:.14em; text-transform:uppercase;
  color:var(--muted); margin-left:.5rem; }}
.story h3 {{ font-family:var(--display) !important; font-size:clamp(1.5rem,2.4vw,1.85rem) !important; margin:0 0 .4rem 0 !important;
  padding:0 !important; }}
.stMarkdown .story p {{ font-family:var(--serif); font-size:clamp(1.12rem,1.6vw,1.26rem); line-height:1.55; color:var(--ink);
  margin:0; }}
.story .chips {{ display:flex; flex-wrap:wrap; gap:.4rem; margin:.9rem 0 .2rem 0; }}
.story .chips span {{ font-family:var(--ui); font-size:.88rem; color:var(--ink); border:1px solid var(--rule-strong);
  background:var(--accent-soft); border-radius:999px; padding:.18rem .7rem; white-space:nowrap; }}
.journey {{ margin:.3rem 0 .6rem 0; border-bottom:1px solid var(--rule-soft); padding-bottom:.2rem; }}
.journey svg {{ width:100%; height:auto; display:block; overflow:visible; }}
.journey a, .scene a {{ cursor:pointer; text-decoration:none !important; }}
.journey a text, .scene a text {{ text-decoration:none; }}
.scene a:hover rect:first-of-type {{ stroke:var(--accent); }}
.journey a:hover circle:first-of-type {{ stroke-width:2.4; }}
.scene svg {{ width:100%; height:auto; display:block; overflow:visible; }}
@media (max-width:640px) {{ .journey, .scene {{ overflow-x:auto; -webkit-overflow-scrolling:touch; }}
  .journey svg {{ min-width:620px; }} .scene svg {{ min-width:540px; }} }}

/* glossary, and the plain legend of the staffing responses */
.gloss {{ display:grid; grid-template-columns:repeat(2, minmax(0,1fr)); gap:0 2rem; margin:.3rem 0 .8rem 0; }}
.gloss.four {{ grid-template-columns:repeat(4, minmax(0,1fr)); gap:0 1.4rem; }}
.gloss > div {{ border-top:1px solid var(--rule); padding:.8rem 0 .9rem 0; min-width:0; }}
.gloss b {{ font-family:var(--serif); font-weight:500; font-size:1.16rem; color:var(--ink); }}
.gloss .aka {{ font-family:var(--ui); font-size:.85rem; color:var(--muted); margin-left:.45rem; }}
.gloss .sw {{ display:inline-block; width:10px; height:10px; margin-right:.5rem; vertical-align:.05rem; }}
.stMarkdown .gloss p {{ font-family:var(--ui); font-size:.98rem; line-height:1.5; color:var(--ink-2); margin:.3rem 0 0 0; }}
@media (max-width:1000px) {{ .gloss.four {{ grid-template-columns:repeat(2, minmax(0,1fr)); }} }}
@media (max-width:640px) {{ .gloss {{ grid-template-columns:minmax(0,1fr); }} }}

/* footer */
.site-foot {{ border-top:3px double var(--rule-strong); margin-top:3rem; padding-top:1rem; display:flex; flex-wrap:wrap;
  gap:.4rem 1.6rem; justify-content:space-between; font-family:var(--ui); font-size:.9rem; color:var(--muted); }}
.site-foot .links {{ display:flex; flex-wrap:wrap; gap:.3rem 1.2rem; }}
.site-foot a {{ color:var(--accent); text-decoration:none; }}
.site-foot a:hover {{ text-decoration:underline; }}
</style>
"""


def css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def page(key: str, lede: str | None = None) -> dict:
    """Page header: eyebrow (part number and name), title, the synthetic label, and an optional lede."""
    p = PAGE[key]
    n = f'<span class="n">{p["num"]}</span>' if p["num"] else ""
    st.markdown(f'<div class="eyebrow">{n}<span>{esc(p["eyebrow"])}</span></div>', unsafe_allow_html=True)
    st.title(p["title"], anchor=False)
    st.markdown(f'<div class="synthetic">{SYNTHETIC}</div>', unsafe_allow_html=True)
    if lede:
        st.markdown(f'<p class="lede">{lede}</p>', unsafe_allow_html=True)
    return p


def section(title: str, intro: str | None = None) -> None:
    body = f"<p>{intro}</p>" if intro else ""
    st.markdown(f'<div class="sechead"><h2>{esc(title)}</h2>{body}</div>', unsafe_allow_html=True)


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:48]


@contextmanager
def plate(title: str, sub: str | None = None, key: str | None = None):
    """A framed panel with a title and a one-line subtitle; put a chart or a table inside."""
    with st.container(key=f"plate-{key or _slug(title)}"):
        s = f"<p>{sub}</p>" if sub else ""
        st.markdown(f'<div class="plate-head"><h3>{esc(title)}</h3>{s}</div>', unsafe_allow_html=True)
        yield


def takeaway(text: str) -> None:
    st.markdown(f'<p class="note">{text}</p>', unsafe_allow_html=True)


def note(text: str) -> None:
    st.markdown(f'<p class="vz-note">{text}</p>', unsafe_allow_html=True)


def prose(*paras: str) -> None:
    st.markdown('<div class="prose">' + "".join(f"<p>{p}</p>" for p in paras) + "</div>", unsafe_allow_html=True)


def proof(cells: list[dict], cols: int | None = None) -> None:
    """A ruled strip of big numbers. Each cell: k (label), v (value), d (detail), tone (gain, loss, gold) or html."""
    parts = []
    for c in cells:
        if "html" in c:
            parts.append(f"<div>{c['html']}</div>")
            continue
        tone = f' class="{c["tone"]}"' if c.get("tone") else ""
        d = f'<span class="d">{c["d"]}</span>' if c.get("d") else ""
        parts.append(f'<div><span class="k">{esc(c["k"])}</span><b{tone}>{c["v"]}</b>{d}</div>')
    st.markdown(f'<div class="proof" style="--cols:{cols or len(cells)}">{"".join(parts)}</div>', unsafe_allow_html=True)


def ledger(df: pd.DataFrame, em_rows: list[int] | None = None, tones: dict | None = None, doc: bool = False,
           left: list[int] | None = None, cls: str = "") -> None:
    """A plain ruled table (for small result tables). `tones` maps (row, col) to gain or loss; `doc` wraps text;
    `left` lists extra text columns to align left (the first always is)."""
    lft = set(left or [])
    head = "".join(f'<th{" class=\"l\"" if j in lft else ""}>{esc(c)}</th>' for j, c in enumerate(df.columns))
    rows = []
    for i, r in enumerate(df.itertuples(index=False)):
        cls = ' class="em"' if em_rows and i in em_rows else ""
        tds = []
        for j, v in enumerate(r):
            cls = " ".join(x for x in ((tones or {}).get((i, j)), "l" if j in lft else None) if x)
            tds.append(f'<td{f" class={chr(34)}{cls}{chr(34)}" if cls else ""}>{esc(v)}</td>')
        rows.append(f"<tr{cls}>{''.join(tds)}</tr>")
    st.markdown(f'<div class="scroll {cls}"><table class="ledger{" doc" if doc else ""}"><thead><tr>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>',
                unsafe_allow_html=True)


def show_sql(sql: str, label: str = "Show the SQL") -> None:
    with st.expander(label):
        st.code(sql, language="sql")


def short(question: str, answer: str, why: str) -> None:
    """The short version, for a reader with no cargo or data background: the question, the answer, why it matters."""
    st.markdown(f'<div class="short"><div><span class="k">The question</span><p>{question}</p></div>'
                f'<div class="a"><span class="k">The answer</span><p>{answer}</p></div>'
                f'<div><span class="k">Why it matters</span><p>{why}</p></div></div>', unsafe_allow_html=True)


def hood(intro: str) -> None:
    """Marks where the plain story ends and the analyst detail (SQL, scores, math) begins."""
    st.markdown(f'<div class="hood"><span class="k">Under the hood</span><h2>For analysts</h2><p>{intro}</p></div>',
                unsafe_allow_html=True)


def in100(x: float) -> str:
    """A rate as a count out of a hundred, which reads more easily than a percentage."""
    return f"{round(100 * x)} in 100"


def glossary_terms() -> list[tuple[str, str, str]]:
    """Plain definitions of the words the lab uses: (term, the industry or technical name, definition)."""
    cfg = C.load()
    sla = cfg["sla_hours"]
    lo = min(sla, key=sla.get)
    top = " and ".join(PRODUCT_NOUNS[p] for p in sla if sla[p] == max(sla.values()))
    sh = cfg["shifts"]
    times = ", ".join(f"{n.lower()} {s:02d}:00 to {(s + sh['hours']) % 24:02d}:00" for n, s in zip(sh["names"], sh["starts"]))
    fx = cfg["flex"]
    waves = " and ".join(cfg["disruption"]["wave_centers"])
    return [
        ("Shipment", "air waybill, AWB", "One customer's consignment, with its own paperwork number. The lab counts shipments."),
        ("Ready to collect", "NFD, notified for delivery", "The moment the terminal tells the customer the freight can be "
         "picked up. The terminal's promise ends here."),
        ("The promise", "service level, SLA", f"How many hours the terminal has from landing to ready, set by type of cargo: "
         f"{sla[lo]} hours for {PRODUCT_NOUNS[lo]} up to {max(sla.values())} for {top}. "
         f"The hours are illustrative."),
        ("On time", None, "Ready to collect within the promise, counted from the moment the plane lands."),
        ("Container", "ULD, unit load device", "The metal box or pallet freight flies in. Some go to one customer unopened; "
         "the rest have to be unpacked."),
        ("Unpacking", "breakdown", "Taking freight out of a container so it can be checked and stored. This is the work the "
         "shift crew does, so it is where staff numbers matter."),
        ("Queue", "backlog", "Shipments that have landed and are still waiting to be unpacked."),
        ("Roster", None, f"How many people work each shift on each day of the week. Shifts run {times}, hub local time."),
        ("Percentage point", None, "The gap between two percentages. Going from 85% to 91% is a rise of 6 points."),
        ("Simulation", None, "A computer model that plays out every flight and shipment minute by minute, so different "
         "rosters can be tried on exactly the same freight."),
        ("Synthetic", None, "Made by the simulation, not taken from any real terminal. Every number here is illustrative."),
        ("Carrier", None, "An airline. The lab's carriers are labeled A to T."),
        ("Early-warning model", "risk model", "A formula that learned from past shipments how likely a new one is to be "
         "late, using only what is known when its plane lands."),
        ("Ranking accuracy", "AUC", "The chance the model scores a late shipment above one that turns out on time. 0.5 is a "
         "coin toss and 1 is perfect."),
        ("Set aside", "quarantine", "Records held back from every measure because they cannot be trusted or safely fixed."),
        ("Optimizer", "integer program", "A method that searches every allowed combination of staff numbers and picks the "
         "one with the lowest total of wages and late penalties."),
        ("Rush hour", "arrival wave", f"In the disruption scenarios, flights moved to land close together around {waves}."),
        ("On-call staff", "call-in pool", f"A team of {fx['pool_size']} extra people, called in for {fx['block_hours']} "
         f"hours whenever {fx['backlog_trigger']} or more shipments are waiting to be unpacked. They arrive "
         f"{fx['lead_time_min']} minutes after the call and are paid {fx['cost_multiplier']:g} times the hourly rate."),
    ]


def glossary(terms: list[tuple[str, str, str]] | None = None) -> None:
    terms = terms if terms is not None else glossary_terms()
    cells = "".join(f'<div><b>{esc(t)}</b>{f"<span class={chr(34)}aka{chr(34)}>{esc(a)}</span>" if a else ""}'
                    f'<p>{esc(d)}</p></div>' for t, a, d in terms)
    st.markdown(f'<div class="gloss">{cells}</div>', unsafe_allow_html=True)


def footer() -> None:
    sib = "".join(f'<a href="{u}" target="_blank">{esc(n)}</a>' for n, u in SIBLINGS)
    st.markdown(
        f'<div class="site-foot"><span>{SYNTHETIC} Built by Marion Peter with Python, SimPy, DuckDB, scikit-learn and PuLP.</span>'
        f'<span class="links"><a href="{PORTFOLIO}" target="_blank">Portfolio</a>{sib}'
        f'<a href="{REPO}" target="_blank">Source</a></span></div>', unsafe_allow_html=True)


# ---------------------------------------------------------------- charts
def _template() -> None:
    axis = dict(gridcolor=RULE_SOFT, linecolor=RULE, zerolinecolor=RULE_STRONG, ticks="", showline=False, automargin=True,
                tickfont=dict(color=MUTED, size=12, family=UI), title=dict(font=dict(color=INK2, size=13, family=UI)))
    t = go.layout.Template()
    t.layout = go.Layout(
        font=dict(family=UI, size=13, color=INK2), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        colorway=[GOLD, GAIN, LOSS, NEU, INK2], margin=dict(l=6, r=10, t=12, b=6), xaxis=axis, yaxis=axis,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, xanchor="left", font=dict(size=13, color=INK2),
                    bgcolor="rgba(0,0,0,0)", title=dict(text="")),
        hoverlabel=dict(bgcolor=SUNK, bordercolor=RULE_STRONG, font=dict(color=INK, size=13, family=UI)),
        bargap=0.28, hovermode="closest",
    )
    pio.templates["ink"] = t
    pio.templates.default = "ink"


_template()


def hatched(color: str) -> dict:
    """Bar marker drawn like the site's plates: a wash of color under an engraved hatch."""
    return dict(color=color, line=dict(color=HATCH, width=1),
                pattern=dict(shape="/", fgcolor=HATCH, size=5, solidity=0.22, fillmode="overlay"))


def show(fig: go.Figure, height: int = 360) -> None:
    fig.update_layout(height=height)
    st.plotly_chart(fig, width="stretch", theme=None, config={"displayModeBar": False, "responsive": True})


def diverging(center: float, lo: float, hi: float) -> list:
    """Oxblood below the center, surface at it, teal above, for heatmaps of a rate."""
    span = max(hi - lo, 1e-9)
    mid = min(max((center - lo) / span, 0.05), 0.95)
    return [[0, LOSS], [mid * 0.55, "#8c4a3f"], [mid, SURFACE], [mid + (1 - mid) * 0.45, "#1f6f72"], [1, GAIN]]


WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
SHIFTS = C.load()["shifts"]["names"]
PRODUCT_LABELS = {"general": "General", "express": "Express", "perishable": "Perishable", "pharma": "Pharma",
                  "dangerous_goods": "Dangerous goods", "live_animals": "Live animals"}
PRODUCT_NOUNS = H.PRODUCT_NOUNS
HU_LABELS = {"bup_breakdown": "Container, unpacked here", "bup_intact": "Container, passed on unopened", "loose": "Loose pieces"}
# the risk model's inputs in everyday words
FEATURE_LABELS = {
    "product": "Type of cargo", "handling_unit": "Container or loose", "carrier": "Airline", "flight_type": "Passenger plane or freighter",
    "region": "Where it flew from", "pieces": "Number of pieces", "weight_kg": "Weight", "arr_hour": "Hour of landing",
    "arr_weekday": "Day of the week", "delay_min": "How late the plane landed", "rostered_headcount": "Staff scheduled on the shift",
    "backlog_at_arr": "Queue waiting when it lands", "sched_awbs_next_2h": "Shipments due in the next 2 hours",
}
# the four staffing responses on the disruption page
POLICY_NAMES = {"legacy": "Current roster", "static": "Recommended roster", "replanned": "Re-planned roster",
                "flex": "Recommended plus on-call staff"}
POLICY_SHORT = {"legacy": "Current", "static": "Recommended", "replanned": "Re-planned", "flex": "On-call"}
