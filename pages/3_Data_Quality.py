import json

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lab import config as C
from lab import kpis
from lab import ui

h = ui.headline()
cfg = C.load()
ui.page("dq", lede="The milestone feed an analyst receives is not the event log the floor produced. Six kinds of defect "
                   "go into a copy of the feed at known rates, with a record of which AWB got which, kept away from the "
                   "detector. One SQL rule per defect, then repair where it is safe and quarantine where it is not.")

sc = ui.table("dq_scorecard")
ver = ui.table("dq_versions").set_index("version")
out = ui.table("dq_outcome").set_index("reason")["awbs"]
rep = json.loads((C.DATA / "dq_repair.json").read_text(encoding="utf-8"))
k = ui.table("kpi_summary").set_index("kpi")["value"]

ui.proof([
    {"k": "AWBs flagged", "v": ui.num(sc["flagged"].sum()), "d": f"of {ui.num(ver.loc['Truth', 'rows'])} in the window, by at least one rule"},
    {"k": "Re-stamped", "v": ui.num(rep["restamped"]), "d": f"time zone repairs; {ui.num(rep['restamped_exact'])} land exactly on the truth"},
    {"k": "Quarantined", "v": ui.num(out.drop("kept").sum()), "d": "held back from every measure until reviewed"},
    {"k": "Complete and in order", "v": ui.pct(k["completeness_feed"]), "d": f"in the feed as received; {ui.pct(k['completeness_cleaned'])} after cleaning"},
])

# ---------------------------------------------------------------- scorecard
ui.section("A rule for each defect", "Precision and recall are measured against the injected truth, which the rules never see. "
                                     "The last column runs each rule on the clean log, where it should find nothing.")
rows, tones = [], {}
for i, r in enumerate(sc.itertuples()):
    rows.append([r.label, ui.num(r.injected), ui.num(r.flagged), ui.num(r.true_pos), ui.pct(r.precision),
                 ui.pct(r.recall), ui.num(r.flagged_on_clean)])
    if r.recall < 0.99:
        tones[(i, 5)] = "loss"
with ui.plate("Defect scorecard", "Rates set in the config; an AWB gets at most one defect"):
    ui.ledger(pd.DataFrame(rows, columns=["Defect", "Injected", "Flagged", "Caught", "Precision", "Recall",
                                          "Flagged on clean log"]), tones=tones)
    tz = sc.set_index("rule").loc["timezone"]
    ui.takeaway(f"Every rule except one catches its defect almost completely. The time zone rule misses "
                f"{ui.num(rep['tz_missed'])} AWBs, all from the manual channel, which carries no UTC stamp "
                f"({ui.pct(rep['manual_share'], 0)} of AWBs). For {ui.num(rep['tz_missed_arr_no_utc'])} the arrival was stamped "
                f"in UTC: handler time reads four hours too long but stays in order. For the other "
                f"{ui.num(rep['tz_missed_terminal_no_utc'])} the terminal stamps were, on freight that waited more than four "
                f"hours, so even four hours early they still fall after the arrival. Nothing in the record gives either away.")

blocks = kpis.blocks(C.SQL / "dq_rules.sql")
names = {r: lab for r, lab in zip(sc["rule"], sc["label"])}
c1, _ = st.columns([0.5, 0.5])
pick = c1.selectbox("Show the rule for", list(names), format_func=names.get)
st.code(blocks[f"rule_{pick}"], language="sql")
ex = ui.table("dq_examples")
e = ex[ex["rule"] == pick].drop(columns=["rule", "label"]).copy()
for c in ["arr_ts", "rcf_ts", "nfd_ts", "arr_utc", "rcf_utc", "nfd_utc"]:
    e[c] = pd.to_datetime(e[c]).dt.strftime("%d %b %H:%M").fillna("")
e["weight_kg"] = e["weight_kg"].map(lambda v: f"{v:,.1f}")
e["weight_checked_kg"] = e["weight_checked_kg"].map(lambda v: f"{v:,.1f}")
e = e.rename(columns={"awb_id": "AWB", "product_code": "Product code", "weight_kg": "Manifest kg", "weight_checked_kg": "Checked kg",
                      "arr_ts": "ARR local", "rcf_ts": "RCF local", "nfd_ts": "NFD local", "arr_utc": "ARR UTC",
                      "rcf_utc": "RCF UTC", "nfd_utc": "NFD UTC", "records": "Records"})
st.markdown('<p class="small">Records the rule caught, as they arrived in the feed. Hub local time is UTC plus '
            f'{cfg["hub_utc_offset_hours"]} hours.</p>', unsafe_allow_html=True)
st.dataframe(e, hide_index=True, width="stretch")

# ---------------------------------------------------------------- KPI under each version
ui.section("What dirty data does to the headline", "NFD on time %, the same SQL, run on four versions of the data.")
order = ["Raw feed", "Time zone defect only", "Quarantine only", "Repaired", "Truth"]
desc = {"Raw feed": "Every record as received", "Time zone defect only": "Clean feed with only the UTC stamps added",
        "Quarantine only": "Drop every flagged AWB, repair nothing", "Repaired": "Repair what is safe, quarantine the rest",
        "Truth": "The clean event log"}
v = ver.loc[order]
truth = v.loc["Truth", "on_time"]
fig = go.Figure()
labels = order
for o, lab in zip(order, labels):
    val = v.loc[o, "on_time"]
    col = {"Truth": ui.GOLD, "Repaired": ui.GAIN}.get(o, ui.LOSS)  # truth, the version the lab uses, the rest
    fig.add_shape(type="line", x0=truth, x1=val, y0=lab, y1=lab, line=dict(color=ui.RULE_STRONG, width=2))
    fig.add_trace(go.Scatter(x=[val], y=[lab], mode="markers+text", marker=dict(size=14, color=col),
                             text=[f"{ui.pct(val, 2)}  ({100 * (val - truth):+.2f})" if o != "Truth" else ui.pct(val, 2)],
                             textposition="middle right", textfont=dict(color=ui.INK, size=13),
                             hovertemplate=f"{o}<br>%{{x:.2%}} on time<extra></extra>"))
fig.add_vline(x=truth, line=dict(color=ui.GOLD, width=1, dash="dot"))
lo = min(v["on_time"].min(), truth) - 0.004
fig.update_xaxes(range=[lo, truth + 0.012], tickformat=".1%")
fig.update_yaxes(autorange="reversed")
fig.update_layout(showlegend=False, margin=dict(l=8))
with ui.plate("NFD on time under each version of the data", "Points from the truth in brackets. Teal is the "
                                                                    "version every later page uses"):
    ui.show(fig, 300)
    ui.ledger(pd.DataFrame([[o, desc[o], ui.num(v.loc[o, "scored"]), ui.pct(v.loc[o, "on_time"], 2),
                             "" if o == "Truth" else f"{100 * (v.loc[o, 'on_time'] - truth):+.2f}"] for o in order],
                           columns=["Version", "What it is", "AWBs scored", "On time", "Points from truth"]),
              em_rows=[4], left=[1])
    ui.takeaway(h["sentences"]["timezone"] + f" Taken as received, the whole feed reads {ui.pct(ver.loc['Raw feed', 'on_time'])} "
                f"against a true {ui.pct(truth)}: missing NFD messages count as late once the promise has passed, resent "
                f"records count twice, and arrival stamps in UTC add four hours. Repair and quarantine bring it to "
                f"{ui.pct(ver.loc['Repaired', 'on_time'])}.")
    kept_truth = ver.loc["Truth, kept AWBs", "on_time"]
    ui.note(f"Quarantine is not free: it drops the AWBs that carry a defect, and if defects were more common on slow freight "
            f"the cleaned measure would flatter the floor. Here defects are assigned at random, so it costs almost nothing: on "
            f"their true timestamps the kept AWBs score {ui.pct(kept_truth, 2)} against {ui.pct(truth, 2)} for all. The gap "
            f"that remains comes from UTC stamps no rule can see, mostly on the arrival.")

# ---------------------------------------------------------------- outcome
ui.section("Repair or quarantine", "Repairs only where the right answer is certain. Everything else is held back.")
o = out.reset_index()
o["what"] = o["reason"].map(lambda r: "Kept" if r == "kept" else "Quarantined")
o = o.sort_values(["what", "awbs"], ascending=[True, False])
rows = [[("Kept for analysis" if r.reason == "kept" else f"Quarantined: {r.reason}"), ui.num(r.awbs),
         ui.pct(r.awbs / o["awbs"].sum(), 2)] for r in o.itertuples()]
with ui.plate("Where each AWB ended up", "Every AWB in the window appears once"):
    ui.ledger(pd.DataFrame(rows, columns=["Outcome", "AWBs", "Share"]), em_rows=[0])
    ui.takeaway(f"Of the AWBs kept, {ui.num(rep['restamped'])} were re-stamped from UTC, or moved forward by the hub offset "
                f"where the freight was otherwise received before its aircraft landed. All {ui.num(rep['restamped_exact'])} "
                f"came back to the true timestamps. Every measure on the later pages uses the kept AWBs.")
ui.show_sql(blocks["repaired"], "Show the repair and quarantine SQL")
ui.footer()
