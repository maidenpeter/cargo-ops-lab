import pandas as pd
import streamlit as st

from lab import config as C
from lab import ui

cfg = C.load()
ui.page("methods", lede="Every assumption with its reason, the method choices and why, what the lab leaves out, and the "
                        "tests that guard it. Every number in the config is an illustrative assumption, not an industry "
                        "standard.")

# ---------------------------------------------------------------- assumptions
ui.section("Every assumption", "Read straight from config.yml, with the one-line comment each value carries.")
a = C.assumptions()
groups = {"seed": "General", "hub_utc_offset_hours": "General", "window": "Data window", "split": "Model split",
          "shifts": "Shifts", "timetable": "Flights", "flights": "Flights", "products": "Shipments",
          "handling_units": "Shipments", "pieces_mean": "Shipments", "kg_per_piece_median": "Shipments",
          "kg_per_piece_sigma": "Shipments", "weight_check_noise": "Shipments", "weight_check_clip": "Shipments",
          "tow_min": "Terminal process", "offload_spread_min": "Terminal process", "intact_checkin_min": "Terminal process",
          "work": "Terminal process", "priority_products": "Terminal process", "doc_check_median_min": "Terminal process",
          "doc_check_sigma": "Terminal process", "absence_rate": "Terminal process", "sla_hours": "Promise (SLA)",
          "customer": "Customer time", "legacy_roster": "Staffing and cost", "hourly_cost_usd": "Staffing and cost",
          "late_penalty_usd": "Staffing and cost", "roster_opt": "Roster optimization", "flex": "Call-in pool",
          "disruption": "Disruption", "defects": "Data quality", "manual_channel_share": "Data quality",
          "weight_tolerance": "Data quality", "weight_tolerance_min_kg": "Data quality", "missing_grace_hours": "Data quality",
          "dq_min_recall": "Data quality", "model": "Risk model"}
a["Area"] = a["group"].map(groups).fillna("Other")
a = a[(a["value"] != "") | (a["note"] != "")]  # grouping keys without a value or a comment add nothing
area = st.selectbox("Area", ["All"] + list(dict.fromkeys(a["Area"])), index=0)
view = a if area == "All" else a[a["Area"] == area]
ui.ledger(view[["Area", "key", "value", "note"]].rename(columns={"key": "Setting", "value": "Value", "note": "Why"}),
          doc=True)

tt = C.timetable().rename(columns={"flight": "Flight", "carrier": "Carrier", "type": "Aircraft", "region": "Origin region",
                                    "sta": "Scheduled arrival", "days": "Days (1 is Monday)", "awbs": "Mean AWBs"})
with st.expander(f"The weekly timetable: {len(tt)} flight lines"):
    st.dataframe(tt, hide_index=True, width="stretch")

# ---------------------------------------------------------------- methods
ui.section("Method choices, and why")
choices = [
    ("A simulation generates the history", "History comes from running a discrete-event model of the floor (SimPy), not "
     "from sampling milestone gaps, so the same engine can score a new roster and a broken schedule. One seed fixes "
     "every draw; the same seed gives every roster the same work (common random numbers), so rosters are compared on "
     "identical freight."),
    ("Breakdown is the one bottleneck", "ULDs to break down wait in one priority queue for the shift's present crew. "
     "Live animals, pharma, express and perishables jump the queue in that order (an assumption). Intact ULDs skip "
     "breakdown. The document check after RCF is not staff constrained."),
    ("Two clocks", "The promise runs from arrival (ARR) to freight ready (NFD) only. Time from NFD to delivery belongs to "
     "customs and the forwarder and is never counted against the terminal."),
    ("SQL for the measures and the rules", "Every KPI and every data quality rule is a DuckDB query in sql/, so it can be "
     "read, reviewed and moved to a warehouse unchanged. Python handles generation, models and the solver."),
    ("Repair only what is certain", "Duplicates are dropped and time zone stamps re-stamped from UTC, or moved by the hub "
     "offset only when that puts freight back after its aircraft. Anything else is quarantined, not guessed."),
    ("Scored at arrival, split by time", "The risk model only sees what is known when the aircraft blocks on; a test "
     "fails the build if a later field enters. Train, validation and test are consecutive blocks of months, never a "
     "random split. The model is picked on validation AUC before the test months are opened."),
    ("A grid, an integer program, and a re-simulation", "Each shift's headcount is scored by simulation, PuLP and CBC "
     "pick one headcount per cell, and the chosen roster is simulated end to end because backlog carries between "
     "shifts. The grid is rebuilt once around the first answer."),
    ("The disruption is a transform of the same arrivals", "Flights move to the nearest wave and AWBs are thinned with "
     "fixed draws, so scenarios are nested and 0% moved with 0% volume change reproduces the base case exactly (tested)."),
]
for t, body in choices:
    st.markdown(f'<div class="prose"><p><b style="font-family:var(--ui);font-weight:600">{ui.esc(t)}.</b> {ui.esc(body)}</p></div>',
                unsafe_allow_html=True)

ui.section("What the lab leaves out")
limits = [
    "It is a synthetic terminal: the numbers show a method, not any real operation.",
    "Import only. No export, transfer or mail flows.",
    "One bottleneck resource. No forklifts, docks, storage positions, cool rooms or truck slots.",
    "Crews are interchangeable and every job takes one person; real breakdown needs teams and equipment.",
    "No revenue model. Late penalties are config values, not contract terms.",
    "The roster grid scores each shift on its own; the re-simulation corrects it but does not search further.",
    "Defects are assigned at random and one per AWB. Real defects cluster by system, channel and shift.",
    "Overtime when a job runs past the shift end is not costed.",
]
st.markdown('<div class="prose"><ul>' + "".join(f"<li>{ui.esc(x)}</li>" for x in limits) + "</ul></div>", unsafe_allow_html=True)

# ---------------------------------------------------------------- tests
ui.section("Tests", "Run by the build script; the results file is committed with the data.")
tr = pd.read_csv(C.DATA / "test_results.csv") if (C.DATA / "test_results.csv").exists() else pd.DataFrame()
if len(tr):
    passed = int((tr["status"] == "passed").sum())
    ui.proof([{"k": "Tests passed", "v": f"{passed} of {len(tr)}", "tone": "gain" if passed == len(tr) else "loss"},
              {"k": "Test files", "v": ui.num(tr["file"].nunique())},
              {"k": "Run time", "v": f"{tr['seconds'].sum():.0f} s"}])
    tr["test"] = tr["test"].str.replace("test_", "", regex=False).str.replace("_", " ").str.capitalize()
    st.dataframe(tr.rename(columns={"test": "Test", "file": "File", "status": "Status", "seconds": "Seconds"}),
                 hide_index=True, width="stretch")

ui.section("Data files", "Everything the app reads is precomputed by scripts/build_results.py and committed.")
files = sorted(p for p in C.DATA.glob("*") if p.is_file())
size = lambda b: f"{b / 1e6:.1f} MB" if b >= 1e6 else f"{b / 1e3:,.0f} KB"  # noqa: E731
st.dataframe(pd.DataFrame({"File": [p.name for p in files], "Size": [size(p.stat().st_size) for p in files]}),
             hide_index=True, width="stretch", height=300)
ui.footer()
