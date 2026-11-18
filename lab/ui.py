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

APP = "Cargo Ops Lab"
TAGLINE = "Will the freight be ready on time, and how many hands does the floor need to make sure it is?"
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

PAGES = [
    {"key": "terminal", "file": "pages/1_Terminal.py", "nav": "Terminal", "url": "terminal", "icon": ":material/flight_land:",
     "num": "", "eyebrow": "Import cargo terminal", "title": APP,
     "teaser": "What the synthetic terminal is, and the four numbers that matter."},
    {"key": "kpis", "file": "pages/2_KPIs.py", "nav": "KPIs", "url": "kpis", "icon": ":material/monitoring:",
     "num": "I", "eyebrow": "Performance measures", "title": "What counts as on time",
     "teaser": "A KPI dictionary on cargo milestones, with the terminal's clock split from the customer's."},
    {"key": "dq", "file": "pages/3_Data_Quality.py", "nav": "Data Quality", "url": "data-quality", "icon": ":material/rule:",
     "num": "II", "eyebrow": "Data quality", "title": "Check the feed before you believe it",
     "teaser": "Six defects injected at known rates, a rule for each, and what dirty data does to the headline KPI."},
    {"key": "risk", "file": "pages/4_Risk.py", "nav": "Risk", "url": "risk", "icon": ":material/crisis_alert:",
     "num": "III", "eyebrow": "Predictive", "title": "Which shipments will be late",
     "teaser": "A late-risk score at aircraft arrival, and what expediting the riskiest tenth would catch."},
    {"key": "roster", "file": "pages/5_Roster.py", "nav": "Roster", "url": "roster", "icon": ":material/groups:",
     "num": "IV", "eyebrow": "Prescriptive", "title": "How many hands each shift needs",
     "teaser": "A roster chosen by optimization over a simulation, labor cost against late shipments."},
    {"key": "disruption", "file": "pages/6_Disruption.py", "nav": "Disruption", "url": "disruption", "icon": ":material/thunderstorm:",
     "num": "V", "eyebrow": "The twist", "title": "When the Schedule Breaks",
     "teaser": "Flights bunch into waves and volume drops. How far the plan and the model drift, and what re-planning recovers."},
    {"key": "methods", "file": "pages/7_Methods.py", "nav": "Methods", "url": "methods", "icon": ":material/menu_book:",
     "num": "", "eyebrow": "Appendix", "title": "Methods and assumptions",
     "teaser": "Every assumption with its reason, the method choices, the limits, and the test results."},
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
a[data-testid="stTopNavLink"] {{ border-radius:2px; padding:0 .55rem !important; gap:.35rem; color:var(--ink-2) !important; }}
a[data-testid="stTopNavLink"] p {{ color:inherit !important; font-family:var(--ui); font-size:.95rem; }}
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
HU_LABELS = {"bup_breakdown": "Built-up ULD, broken down", "bup_intact": "Built-up ULD, intact", "loose": "Loose"}
