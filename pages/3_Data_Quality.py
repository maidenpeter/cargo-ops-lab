import json

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lab import config as C
from lab import kpis
from lab import ui

h = ui.headline()
cfg = C.load()
off = cfg["hub_utc_offset_hours"]
words = {4: "four"}.get(off, str(off))
sc = ui.table("dq_scorecard")
ver = ui.table("dq_versions").set_index("version")
out = ui.table("dq_outcome").set_index("reason")["awbs"]
rep = json.loads((C.DATA / "dq_repair.json").read_text(encoding="utf-8"))
k = ui.table("kpi_summary").set_index("kpi")["value"]

# each error in everyday words: name, what it looks like in the records
ERRORS = {
    "missing_rcf": ("Check-in message missing", "The record never says the freight was checked in."),
    "missing_nfd": ("Ready message missing", "The record never says the freight was ready, so it looks late."),
    "out_of_sequence": ("Steps out of order", "The freight is marked ready before it was checked in."),
    "duplicate_resend": ("Sent twice", "The same shipment arrives twice, so it is counted twice."),
    "weight_mismatch": ("Weight keyed wrong", "The weight on the paperwork is far from the weight measured at check-in."),
    "invalid_product": ("Unknown cargo code", "The type-of-cargo code is not one the terminal uses, so its promise is unknown."),
    "timezone": ("Wrong time zone", f"Times recorded in world time (UTC) but labeled as local, so they read {words} hours early."),
}
VERSIONS = {  # the stored version name: plain name, what it is
    "Raw feed": ("Records as received", "Every record, errors and all"),
    "Time zone defect only": ("Only the time zone error", "Clean records with just the wrong time zones added"),
    "Quarantine only": ("Set aside every flagged record", "Drop every flagged shipment, fix nothing"),
    "Repaired": ("Fix what is safe, set aside the rest", "The version every later page uses"),
    "Truth": ("The truth", "What the simulated floor really did"),
}
OUTCOMES = {"kept": "Kept for the measures", "NFD before RCF": "Set aside: steps out of order",
            "missing NFD": "Set aside: ready message missing", "missing RCF": "Set aside: check-in message missing",
            "unknown product": "Set aside: unknown cargo code", "weight mismatch": "Set aside: weight keyed wrong"}
caught_all = sc["true_pos"].sum() / sc["injected"].sum()
truth = ver.loc["Truth", "on_time"]

ui.page("dq")
ui.short(
    "Can the records be trusted as they arrive?",
    f"Not quite. A copy of the records was given {len(sc)} kinds of everyday error on purpose, such as times in the "
    f"wrong time zone and messages sent twice. Taken at face value, it says <b>{ui.pct(ver.loc['Raw feed', 'on_time'])}</b> "
    f"of shipments were on time; the truth is {ui.pct(truth)}. Automatic checks catch {ui.pct(caught_all, 0)} of the "
    f"errors, and after fixing what is safe and setting the rest aside, the figure is {ui.pct(ver.loc['Repaired', 'on_time'])}.",
    "A wrong headline number leads to wrong decisions, such as hiring staff to fix a problem that is really in the data. "
    "Checking the records before reporting them is far cheaper.",
)
ui.proof([
    {"k": "Shipments flagged", "v": ui.num(sc["flagged"].sum()), "d": f"of {ui.num(ver.loc['Truth', 'rows'])}, by at least one check"},
    {"k": "Times corrected", "v": ui.num(rep["restamped"]), "d": f"wrong time zones fixed; {ui.num(rep['restamped_exact'])} land exactly on the true time"},
    {"k": "Set aside", "v": ui.num(out.drop("kept").sum()), "d": "held back from every measure until someone reviews them"},
    {"k": "Complete and in order", "v": ui.pct(k["completeness_feed"]), "d": f"of records as received; {ui.pct(k['completeness_cleaned'])} after cleaning"},
])

# ---------------------------------------------------------------- scorecard
ui.section(f"{len(sc)} errors, {len(sc)} checks", "Each error was planted at a known rate, with a hidden list of which shipment "
                                                  "got which. Each check is scored against that list, which it never sees. "
                                                  "A good check catches its error and raises no false alarms on clean records.")
rows, tones = [], {}
for i, r in enumerate(sc.itertuples()):
    name, looks = ERRORS[r.rule]
    rows.append([name, looks, ui.num(r.injected), ui.num(r.true_pos), ui.pct(r.recall), ui.num(r.flagged - r.true_pos),
                 ui.num(r.flagged_on_clean)])
    if r.recall < 0.99:
        tones[(i, 4)] = "loss"
with ui.plate("How well each check works", "No shipment got more than one error. Rates are illustrative, set in the lab's settings"):
    ui.ledger(pd.DataFrame(rows, columns=["Error", "What it looks like", "Planted", "Caught", "Share caught",
                                          "False alarms", "Alarms on clean records"]), tones=tones, left=[1])
    ui.takeaway(f"Every check catches its error almost completely, except one. The time zone check misses "
                f"{ui.num(rep['tz_missed'])} shipments, all keyed in by hand, a route that carries no world-time stamp to "
                f"compare against ({ui.pct(rep['manual_share'], 0)} of shipments). For {ui.num(rep['tz_missed_arr_no_utc'])} "
                f"of them only the landing time was wrong: the terminal's time reads {words} hours too long, but nothing "
                f"looks out of order. For the other {ui.num(rep['tz_missed_terminal_no_utc'])}, the terminal's own times "
                f"were wrong, but the freight had waited more than {words} hours, so even {words} hours early they still "
                f"come after the landing. Nothing in the record gives either away.")

# ---------------------------------------------------------------- KPI under each version
ui.section("What bad data does to the headline", "The share ready on time, worked out the same way on five versions of "
                                                 "the records.")
order = list(VERSIONS)
v = ver.loc[order]
fig = go.Figure()
for o in order:
    lab = VERSIONS[o][0]
    val = v.loc[o, "on_time"]
    col = {"Truth": ui.GOLD, "Repaired": ui.GAIN}.get(o, ui.LOSS)  # the truth, the version the lab uses, the rest
    fig.add_shape(type="line", x0=truth, x1=val, y0=lab, y1=lab, line=dict(color=ui.RULE_STRONG, width=2))
    fig.add_trace(go.Scatter(x=[val], y=[lab], mode="markers+text", marker=dict(size=14, color=col),
                             text=[f"{ui.pct(val, 2)}  ({100 * (val - truth):+.2f})" if o != "Truth" else ui.pct(val, 2)],
                             textposition="middle right", textfont=dict(color=ui.INK, size=13),
                             hovertemplate=f"{lab}<br>%{{x:.2%}} on time<extra></extra>"))
fig.add_vline(x=truth, line=dict(color=ui.GOLD, width=1, dash="dot"))
lo = min(v["on_time"].min(), truth) - 0.004
fig.update_xaxes(range=[lo, truth + 0.014], tickformat=".1%")
fig.update_yaxes(autorange="reversed")
fig.update_layout(showlegend=False, margin=dict(l=8))
with ui.plate("Ready on time under each version of the records", "Percentage points away from the truth in brackets. "
                                                                 "Teal is the version every later page uses"):
    ui.show(fig, 300)
    ui.ledger(pd.DataFrame([[VERSIONS[o][0], VERSIONS[o][1], ui.num(v.loc[o, "scored"]), ui.pct(v.loc[o, "on_time"], 2),
                             "" if o == "Truth" else f"{100 * (v.loc[o, 'on_time'] - truth):+.2f}"] for o in order],
                           columns=["Version", "What it is", "Shipments counted", "On time", "Points from the truth"]),
              em_rows=[order.index("Truth")], left=[1])
    ui.takeaway(h["sentences"]["timezone"] + f" Taken as received, all the records together read "
                f"{ui.pct(ver.loc['Raw feed', 'on_time'])} against a true {ui.pct(truth)}: missing ready messages count as "
                f"late once the promise has passed, shipments sent twice count twice, and landing times in world time add "
                f"{words} hours. Fixing and setting aside brings it to {ui.pct(ver.loc['Repaired', 'on_time'])}.")
    kept_truth = ver.loc["Truth, kept AWBs", "on_time"]
    ui.note(f"Setting records aside has a cost: it drops the shipments that carry an error, and if errors were more common "
            f"on slow freight, the cleaned figure would flatter the terminal. Here errors were planted at random, so it "
            f"costs almost nothing: on their true times the kept shipments score {ui.pct(kept_truth, 2)} against "
            f"{ui.pct(truth, 2)} for all. The gap that remains comes from wrong time zones no check can see, mostly on "
            f"the landing time.")

# ---------------------------------------------------------------- outcome
ui.section("Fix or set aside", "Fix only where the right answer is certain. Hold back everything else.")
o = out.reset_index()
o["kept"] = o["reason"] == "kept"
o = o.sort_values(["kept", "awbs"], ascending=[False, False])
rows = [[OUTCOMES.get(r.reason, f"Set aside: {r.reason}"), ui.num(r.awbs), ui.pct(r.awbs / o["awbs"].sum(), 2)]
        for r in o.itertuples()]
with ui.plate("Where each shipment ended up", "Every shipment appears once"):
    ui.ledger(pd.DataFrame(rows, columns=["Outcome", "Shipments", "Share"]), em_rows=[0])
    ui.takeaway(f"Of the shipments kept, {ui.num(rep['restamped'])} had their times corrected, from the world-time stamp "
                f"where there was one, or by moving them {words} hours where the freight otherwise appeared to be checked "
                f"in before its plane landed. {ui.num(rep['restamped_exact'])} of them came back exactly to their true "
                f"times. Records sent twice were merged into one. Every measure on the later pages uses the kept shipments.")

# ---------------------------------------------------------------- under the hood
ui.hood("The scorecard in the usual terms, each rule's SQL with the records it caught, and the repair and quarantine "
        "query. Precision is the share of flags that were real errors; recall is the share of errors flagged.")
rows = [[r.label, ui.num(r.injected), ui.num(r.flagged), ui.num(r.true_pos), ui.pct(r.precision), ui.pct(r.recall),
         ui.num(r.flagged_on_clean)] for r in sc.itertuples()]
with ui.plate("Defect scorecard", "Against the injected truth; an AWB gets at most one defect"):
    ui.ledger(pd.DataFrame(rows, columns=["Defect", "Injected", "Flagged", "Caught", "Precision", "Recall",
                                          "Flagged on clean log"]))
blocks = kpis.blocks(C.SQL / "dq_rules.sql")
names = {r: lab for r, lab in zip(sc["rule"], sc["label"])}
c1, _ = st.columns([0.5, 0.5])
pick = c1.selectbox("Show the rule for", list(names), format_func=names.get)
st.code(blocks[f"rule_{pick}"], language="sql")
ex = ui.table("dq_examples")
e = ex[ex["rule"] == pick].drop(columns=["rule", "label"]).copy()
for c in ["arr_ts", "rcf_ts", "nfd_ts", "arr_utc", "rcf_utc", "nfd_utc"]:
    e[c] = pd.to_datetime(e[c]).dt.strftime("%d %b %H:%M").fillna("")
e["weight_kg"] = e["weight_kg"].map(lambda x: f"{x:,.1f}")
e["weight_checked_kg"] = e["weight_checked_kg"].map(lambda x: f"{x:,.1f}")
e = e.rename(columns={"awb_id": "AWB", "product_code": "Product code", "weight_kg": "Manifest kg", "weight_checked_kg": "Checked kg",
                      "arr_ts": "ARR local", "rcf_ts": "RCF local", "nfd_ts": "NFD local", "arr_utc": "ARR UTC",
                      "rcf_utc": "RCF UTC", "nfd_utc": "NFD UTC", "records": "Records"})
st.markdown(f'<p class="small">Records the rule caught, as they arrived in the feed. Hub local time is UTC plus {off} '
            f'hours.</p>', unsafe_allow_html=True)
st.dataframe(e, hide_index=True, width="stretch")
ui.show_sql(blocks["repaired"], "Show the repair and quarantine SQL")
ui.footer()
