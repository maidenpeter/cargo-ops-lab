import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lab import config as C
from lab import scenarios as X
from lab import shipments as S
from lab import ui

cfg = C.load()
start, cut = pd.Timestamp(cfg["window"]["start"]), C.cutoff()
weeks = (cut - start).days / 7

ui.page("legal")
ui.short(
    "A customer says the terminal made their shipment late. What does the record show?",
    "Look up any shipment to see its timeline, the promise that applied, whether it was kept, and whose clock any "
    "delay was on. Below that, test a promise before it goes into a contract, and see how much lateness a broken "
    "schedule causes on its own.",
    "Claims, penalty clauses and disruption clauses all turn on the same facts: what was promised, when the freight "
    "was ready, and who held it. The records answer that, provided they can be trusted.",
)
ui.takeaway("<b>Not legal advice.</b> Everything here comes from a simulated terminal. It shows how the data could "
            "support legal work; no real contract, law or company is modeled.")

# ---------------------------------------------------------------- shipment file
ui.section("Look up a shipment", "Type a shipment number, or pick one of the examples. Each kind of case reads "
                                 "differently.")
ex = S.examples()
c1, c2 = st.columns([0.45, 0.55], vertical_alignment="bottom")
pick = c1.selectbox("Example", list(ex), index=0)
typed = c2.text_input("Or type a shipment number", placeholder="for example AWB0192080")
awb_id = S.find_id(typed) or (typed.strip().upper() if typed.strip() else ex[pick])
rec = S.record(awb_id)

if rec["status"] == "kept":
    if not rec["scored"]:
        tone, word = "gold", "Not judged"
    else:
        tone, word = ("gain", "Kept") if rec["on_time"] else ("loss", "Missed")
    ui.proof([
        {"k": "The promise", "v": word, "tone": tone,
         "d": (f"{S.dur(rec['margin_min'])} {'inside' if rec['margin_min'] >= 0 else 'past'} the {rec['sla_h']:g}-hour promise"
               if rec["scored"] else "the promise had not run out when the data ends")},
        {"k": "Terminal's time", "v": S.dur(rec["terminal_min"]) if rec["terminal_min"] is not None else "n/a",
         "d": "landing to ready to collect"},
        {"k": "Customer's time", "v": S.dur(rec["customer_min"]) if rec["customer_min"] is not None else "n/a",
         "d": "ready to collected, not covered by the promise"},
        {"k": "The record", "v": "Passed", "tone": "gain", "d": "every data check"},
    ])
    c1, c2 = st.columns([0.55, 0.45])
    with c1:
        with ui.plate(f"Shipment file: {rec['id']}", f"Flight {rec['flight']}, {rec['carrier']}, a {rec['aircraft']} from "
                                                     f"{rec['region']}. Hub local time"):
            ui.prose(*[ui.esc(p) for p in S.verdict(rec)])
    with c2:
        rows = [["Cargo", f"{rec['product_label']}, {rec['pieces']} pieces, {rec['weight']:,.1f} kg"],
                ["Arrived", rec["unit"].capitalize()],
                ["Scheduled landing", S.short_when(rec['sched'], year=True)],
                ["Landed", S.short_when(rec['arr'], year=True)],
                ["Checked in", S.short_when(rec['rcf']) if pd.notna(rec["rcf"]) else "not recorded"],
                ["Ready to collect", S.short_when(rec['nfd']) if pd.notna(rec["nfd"]) else "not recorded"],
                ["Promise ran out", S.short_when(rec['due'])],
                ["Collected", S.short_when(rec['dlv']) if pd.notna(rec["dlv"]) else "not recorded"]]
        if "score" in rec:
            rows.append(["Early-warning score at landing",
                         f"{rec['score']:.0%} chance of being late"
                         + (", on the fast-track list" if rec["flagged"] else ", not on the fast-track list")])
        with ui.plate("The timeline", "Every step the record holds"):
            ui.ledger(pd.DataFrame(rows, columns=["Step", "When"]), left=[1])
else:
    with ui.plate(f"Shipment file: {rec['id']}", "What the record shows"):
        ui.prose(*[ui.esc(p) for p in S.verdict(rec)])
st.download_button("Download this shipment file (HTML)", S.file_html(rec), file_name=f"{rec['id']}.html",
                   mime="text/html", type="primary",
                   help="A page that opens in any browser. Print it, or save it as a PDF, to keep with a claim.")

# ---------------------------------------------------------------- promise tester
ui.section("Test a promise before it goes into a contract",
           "Pick a type of cargo and a promise in hours. The answer replays every shipment of that type the terminal "
           "handled, under the current roster, against the new promise.")
sla = cfg["sla_hours"]
pens = cfg["late_penalty_usd"]
c1, c2, c3 = st.columns([0.34, 0.33, 0.33])
prod = c1.selectbox("Type of cargo", list(ui.PRODUCT_LABELS), format_func=ui.PRODUCT_LABELS.get, index=0)
hours = c2.slider("Promised hours from landing to ready", 1.0, 12.0, float(sla[prod]), step=0.5, format="%.1f h")
pen = c3.number_input("Penalty per late shipment (illustrative dollars)", min_value=0, max_value=10000,
                      value=int(pens[prod]), step=5)


@st.cache_data(show_spinner=False)
def promise_curve(product: str) -> pd.DataFrame:
    con = ui.db()
    return con.execute(
        """SELECT h.hours, COUNT(*) AS scored,
                  AVG(CASE WHEN a.nfd_ts <= a.arr_ts + to_minutes(CAST(h.hours * 60 AS BIGINT)) THEN 1.0 ELSE 0.0 END) AS on_time
           FROM awb_all a, (SELECT range / 2.0 AS hours FROM range(2, 25)) h
           WHERE a.product = $product AND a.arr_ts + to_minutes(CAST(h.hours * 60 AS BIGINT)) < $cutoff
           GROUP BY 1 ORDER BY 1""", {"product": product, "cutoff": cut.to_pydatetime()}).df()


curve = promise_curve(prod)
row = curve.iloc[(curve["hours"] - hours).abs().argmin()]
now = curve.iloc[(curve["hours"] - float(sla[prod])).abs().argmin()]
late_wk = row["scored"] * (1 - row["on_time"]) / weeks
ui.proof([
    {"k": "Would have been on time", "v": ui.pct(row["on_time"]), "tone": "gain" if row["on_time"] >= now["on_time"] else "loss",
     "d": f"against {ui.pct(now['on_time'])} with the lab's {sla[prod]}-hour promise"},
    {"k": "Late shipments per week", "v": ui.num(late_wk), "d": f"of {ui.num(row['scored'] / weeks)} a week"},
    {"k": "Penalties per week", "v": ui.usd(late_wk * pen), "d": f"at {ui.usd(pen)} per late shipment"},
    {"k": "Penalties per year", "v": ui.usd(late_wk * pen * 52), "d": "if the year looks like the data"},
])
fig = go.Figure()
fig.add_trace(go.Scatter(x=curve["hours"], y=curve["on_time"], mode="lines+markers", line=dict(color=ui.GAIN, width=2),
                         marker=dict(size=5, color=ui.GAIN), hovertemplate="%{x:.1f} h promise<br>%{y:.1%} on time<extra></extra>",
                         showlegend=False))
fig.add_trace(go.Scatter(x=[row["hours"]], y=[row["on_time"]], mode="markers", showlegend=False, hoverinfo="skip",
                         marker=dict(size=12, color=ui.GOLD, line=dict(color=ui.INK, width=1.5))))
fig.add_vline(x=float(sla[prod]), line=dict(color=ui.RULE_STRONG, width=1, dash="dot"))
fig.add_annotation(x=float(sla[prod]), y=1.05, yref="paper", text=f"Lab's promise, {sla[prod]} h", showarrow=False,
                   font=dict(color=ui.MUTED, size=12))
fig.update_xaxes(title_text="Promised hours from landing to ready", dtick=1)
fig.update_yaxes(tickformat=".0%", title_text="Would have been on time", rangemode="tozero")
fig.update_layout(margin=dict(t=36))
with ui.plate(f"How often a promise is kept: {ui.PRODUCT_NOUNS[prod]}", "Every shipment of this type, "
                                                                                  f"{start:%B %Y} to {pd.Timestamp(cfg['window']['cutoff']):%B %Y}. The marker follows your choice"):
    ui.show(fig, 300)
    ui.takeaway(f"A {hours:g}-hour promise for {ui.PRODUCT_NOUNS[prod]} would have been kept "
                f"{ui.pct(row['on_time'])} of the time: about {ui.num(late_wk)} late shipments and "
                f"{ui.usd(late_wk * pen)} in penalties a week. A promise the floor cannot keep becomes a steady cost, so "
                f"it is worth testing before it is signed.")

# ---------------------------------------------------------------- disruption on its own
ui.section("How much lateness does a broken schedule cause on its own?",
           "A clause that excuses delays caused by disruption (force majeure) needs a way to tell those delays apart. A "
           "simulation can: it replays the same freight, with the same roster, with and without the disruption.")
dis = ui.table("disruption")
base = dis[(dis["scenario"] == X.key(0.0, 0.0)) & (dis["policy"] == "static")].iloc[0]
rows = []
for s in cfg["disruption"]["rescheduled_shares"]:
    if not s:
        continue
    r = dis[(dis["scenario"] == X.key(s, 0.0)) & (dis["policy"] == "static")].iloc[0]
    extra = r["late_per_week"] - base["late_per_week"]
    rows.append([f"{s:.0%}", ui.num(base["late_per_week"]), ui.num(r["late_per_week"]), f"{extra:+,.0f}",
                 ui.pct(extra / r["late_per_week"], 0) if r["late_per_week"] else ""])
test0 = pd.Timestamp(cfg["split"]["valid_end"]) + pd.Timedelta(days=1)
with ui.plate("Late shipments per week, recommended roster", f"Same freight and same roster, {test0:%B} to "
                                                              f"{pd.Timestamp(cfg['window']['cutoff']):%B %Y}; only the "
                                                              f"schedule changes"):
    ui.ledger(pd.DataFrame(rows, columns=["Flights moved", "Late a week, normal", "Late a week, broken",
                                          "Caused by the disruption", "Share caused by it"]))
    last = rows[-1]
    ui.takeaway(f"With {last[0]} of flights moved, about {last[4]} of the late shipments are down to the disruption. "
                f"The rest would have been late on the normal schedule too, which is the part a disruption clause "
                f"should not excuse.")
ui.footer()
