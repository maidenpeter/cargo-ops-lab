import io

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lab import config as C
from lab import kpis
from lab import ui

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
# each measure in everyday words: name, what it means, whose clock it runs on, what it helps decide
PLAIN = {
    "nfd_on_time": ("Ready on time", "The share of shipments ready to collect within the promise for their type of cargo, "
                    "counted from the moment the plane lands.", "Terminal",
                    "How many staff each shift needs, and which arrivals supervisors should watch."),
    "handler_time": ("Terminal time", "Hours from landing to ready to collect, for the typical shipment and for the "
                     "slowest tenth.", "Terminal",
                     "Whether the promise is realistic, and whether the slow few or the typical shipment needs work."),
    "customer_time": ("Customer time", "Hours from ready to collected: customs holds, paperwork and the customer's pickup.",
                      "Customer", "Storage charges and pickup reminders. It is not a measure of the terminal."),
    "dwell_split": ("Terminal share of the wait", "Of all the time freight spends at the airport, the share on the "
                    "terminal's clock.", "Both", "Who to talk to about long waits: the terminal floor or the customer."),
    "throughput": ("Unpacking speed", "Kilograms unpacked for each staff hour worked.", "Terminal",
                   "How productive each shift is, and the work rate a staffing plan should assume."),
    "backlog_at_shift_end": ("Work handed over", "Shipments that had landed but were still waiting to be unpacked when a "
                             "shift ended.", "Terminal", "Whether one shift is leaving its work to the next."),
    "late_per_1000": ("Late per 1,000 shipments", "The same measure as ready on time, read as a count of late shipments.",
                      "Terminal", "A number operations and sales can both quote without converting percentages."),
    "completeness": ("Complete records", "The share of shipments whose record has all four steps, in the right order.",
                     "Data team", "Whether this month's records can be trusted for the other measures."),
}

con = ui.db()
kd = pd.read_csv(C.DATA / "kpi_dictionary.csv")
k = ui.table("kpi_summary").set_index("kpi")["value"]
by = ui.table("kpi_by")
bp = by[by["dim"] == "Product"].set_index("level")
ht_p = ui.table("handler_time_by_product").set_index("product")
la = ht_p.loc["live_animals"]
everything = {"awb": ui.filtered([], [], [])}
hm_all = kpis.run(con, "kpis.sql", "on_time_hour_weekday", everything)
w = hm_all[hm_all["scored"] >= 30].sort_values("value").iloc[0]

ui.page("kpis")
ui.short(
    "What does &ldquo;on time&rdquo; mean, and how often is the terminal on time?",
    f"On time means ready to collect within the promise for that type of cargo, counted from landing. "
    f"<b>{ui.pct(k['nfd_on_time'])}</b> of shipments make it. The weakest moment is planes landing on "
    f"{DAYS[int(w['arr_weekday'])]}s at {int(w['arr_hour']):02d}:00 ({ui.pct(w['value'])} on time), and the hardest promise "
    f"is the {int(la['sla_h'])}-hour one for live animals: only {ui.pct(bp.loc['live_animals', 'value'])} make it.",
    "Without one agreed definition, operations, sales and finance quote different numbers. And the terminal should be "
    "judged only on its own clock: once freight is ready, the waiting belongs to customs and the customer.",
)

# ---------------------------------------------------------------- dictionary
ui.section("Eight measures, one definition each", "What each measure means, whose clock it runs on, and the decision it "
                                                  "helps make. The exact formulas and SQL are under the hood.")
plain = kd.assign(p_name=kd["kpi"].map(lambda x: PLAIN[x][0]), p_def=kd["kpi"].map(lambda x: PLAIN[x][1]),
                  p_own=kd["kpi"].map(lambda x: PLAIN[x][2]), p_dec=kd["kpi"].map(lambda x: PLAIN[x][3]))
ui.ledger(plain[["p_name", "p_def", "p_own", "p_dec"]].rename(columns={
    "p_name": "Measure", "p_def": "What it means", "p_own": "Whose clock", "p_dec": "What it helps decide"}),
    doc=True, cls="kd-table")
st.markdown('<div class="kd-cards">' + "".join(
    f'<div class="kd-card"><b>{ui.esc(r.p_name)}</b><span class="own">{ui.esc(r.p_own)}</span><p>{ui.esc(r.p_def)}</p>'
    f'<p>Helps decide: {ui.esc(r.p_dec)}</p></div>' for r in plain.itertuples()) + "</div>", unsafe_allow_html=True)

# ---------------------------------------------------------------- live measures
ui.section("Explore the measures", "Pick types of cargo, airlines or shifts. The figures recalculate from the shipment "
                                   "records each time.")
f1, f2, f3 = st.columns(3)
prods = list(ui.PRODUCT_LABELS)
sel_p = f1.multiselect("Type of cargo", prods, format_func=ui.PRODUCT_LABELS.get, placeholder="All types")
carriers = sorted(C.timetable()["carrier"].unique())
sel_c = f2.multiselect("Airline", carriers, placeholder="All airlines")
sel_s = f3.multiselect("Shift when the plane landed", ui.SHIFTS, placeholder="All shifts")
src = ui.filtered(sel_p, sel_c, sel_s)
fmt = {"awb": src}
ot = kpis.run(con, "kpis.sql", "nfd_on_time", fmt).iloc[0]
if ot["scored"] == 0:
    st.info("No shipments match these choices.")
    st.stop()
ht = kpis.run(con, "kpis.sql", "handler_time", fmt).iloc[0]
lp = kpis.run(con, "kpis.sql", "late_per_1000", fmt).iloc[0]
ui.proof([
    {"k": "Ready on time", "v": ui.pct(ot["value"]), "d": f"of {ui.num(ot['scored'])} shipments counted"},
    {"k": "Typical terminal time", "v": ui.hrs(ht["p50_h"]), "d": "landing to ready, for the middle shipment"},
    {"k": "Slowest tenth", "v": ui.hrs(ht["p90_h"]), "d": "take longer than this from landing to ready"},
    {"k": "Late per 1,000", "v": ui.num(lp["value"]), "d": "late shipments in every thousand", "tone": "loss"},
])

mo = kpis.run(con, "kpis.sql", "monthly", fmt)
fig = go.Figure(go.Scatter(x=mo["arr_month"], y=mo["on_time"], mode="lines+markers", line=dict(color=ui.GAIN, width=2),
                           marker=dict(size=6, color=ui.GAIN), hovertemplate="%{x|%B %Y}<br>%{y:.1%} on time<extra></extra>"))
fig.update_yaxes(tickformat=".0%", title_text="Ready on time")
fig.update_xaxes(tickformat="%b<br>%Y", dtick="M2")
with ui.plate("Ready on time, month by month", "The share of shipments ready within the promise, by month of landing"):
    ui.show(fig, 280)
    worst = mo.loc[mo["on_time"].idxmin()]
    ui.takeaway(f"The weakest month was {worst['arr_month']:%B %Y} at {ui.pct(worst['on_time'])}; the best was "
                f"{ui.pct(mo['on_time'].max())}. The roster is the same every week of the history, so the rises and falls "
                f"come from the flights and the freight, not from the staffing.")

hm = kpis.run(con, "kpis.sql", "on_time_hour_weekday", fmt)
grid = hm.pivot(index="arr_weekday", columns="arr_hour", values="value").reindex(index=range(7), columns=range(24))
cnt = hm.pivot(index="arr_weekday", columns="arr_hour", values="scored").reindex(index=range(7), columns=range(24))
fig = go.Figure(go.Heatmap(z=grid.values, x=[f"{h:02d}" for h in range(24)], y=ui.WEEKDAYS, customdata=cnt.values,
                           colorscale=ui.diverging(ot["value"], float(hm["value"].min()), 1.0), zmin=float(hm["value"].min()),
                           zmax=1.0, xgap=2, ygap=2, colorbar=dict(tickformat=".0%", outlinewidth=0, thickness=10, len=0.9,
                                                                  tickfont=dict(color=ui.MUTED, size=12)),
                           hovertemplate="%{y} %{x}:00<br>%{z:.1%} on time<br>%{customdata:,} shipments<extra></extra>"))
fig.update_yaxes(autorange="reversed", showgrid=False)
fig.update_xaxes(showgrid=False, title_text="Hour the plane landed (hub local time)")
with ui.plate("When late freight lands", "The share ready on time by hour of landing and day of the week. Red is worse "
                                         "than the average for your selection, teal is better."):
    ui.show(fig, 330)
    hh = hm[hm["scored"] >= 30]
    lo = hh.loc[hh["value"].idxmin()]
    why = (" Planes landing early in the morning join a queue that the night's cargo flights left behind."
           if 3 <= int(lo["arr_hour"]) <= 9 and not sel_s else "")
    ui.takeaway(f"The weakest hour is {DAYS[int(lo['arr_weekday'])]} at {int(lo['arr_hour']):02d}:00, with "
                f"{ui.pct(lo['value'])} on time.{why}")

# ---------------------------------------------------------------- products
ui.section("Which types of cargo miss their promise", "Each type has its own promise, shown in hours in brackets. The "
                                                      "hours are illustrative assumptions, set in the lab's settings.")
bpp = by[by["dim"] == "Product"].copy()
bpp["label"] = bpp["level"].map(ui.PRODUCT_LABELS) + "  (" + bpp["level"].map(ht_p["sla_h"]).astype(int).astype(str) + " h)"
bpp = bpp.sort_values("value")
overall = k["nfd_on_time"]
colors = [ui.LOSS if v < overall else ui.GAIN for v in bpp["value"]]
fig = go.Figure()
fig.add_trace(go.Scatter(x=bpp["value"], y=bpp["label"], mode="markers+text", marker=dict(size=13, color=colors),
                         text=[ui.pct(v) for v in bpp["value"]], textposition="middle right",
                         textfont=dict(color=ui.INK, size=13), hovertemplate="%{y}<br>%{x:.1%} on time<extra></extra>"))
for v, y in zip(bpp["value"], bpp["label"]):
    fig.add_shape(type="line", x0=0.5, x1=v, y0=y, y1=y, line=dict(color=ui.RULE_STRONG, width=1))
fig.add_vline(x=overall, line=dict(color=ui.GOLD, width=1, dash="dot"))
fig.add_annotation(x=overall, y=1.06, yref="paper", text=f"All cargo {ui.pct(overall)}", showarrow=False,
                   font=dict(color=ui.GOLD, size=12))
fig.update_xaxes(range=[0.5, 1.04], tickformat=".0%")
fig.update_layout(showlegend=False, margin=dict(t=30))
with ui.plate("Ready on time by type of cargo", "All shipments that passed the data checks"):
    ui.show(fig, 300)
    ui.takeaway(f"Live animals make their {int(la['sla_h'])}-hour promise only "
                f"{ui.pct(bp.loc['live_animals', 'value'])} of the time, even though they go to the front of the queue. "
                f"Getting them off the plane and checked in takes {la['arr_to_rcf_min']:.0f} minutes on average, and the "
                f"paperwork adds {la['rcf_to_nfd_min']:.0f}. The promise, not the crew, is the first thing to question.")

ts = ui.table("time_split").copy()
ts["label"] = ts["product"].map(ui.PRODUCT_LABELS)
ts = ts.sort_values("customer_h")
fig = go.Figure()
fig.add_trace(go.Bar(y=ts["label"], x=ts["handler_h"], orientation="h", name="Terminal: landing to ready",
                     marker=ui.hatched(ui.GOLD), hovertemplate="%{y}<br>terminal %{x:.1f} h<extra></extra>"))
fig.add_trace(go.Bar(y=ts["label"], x=ts["customer_h"], orientation="h", name="Customer: ready to collected",
                     marker=ui.hatched(ui.CTX), hovertemplate="%{y}<br>customer %{x:.1f} h<extra></extra>"))
fig.update_layout(barmode="stack", margin=dict(t=36))
fig.update_xaxes(title_text="Average hours")
with ui.plate("Whose clock is the waiting on?", "Average hours on the terminal's clock and on the customer's, by type of cargo"):
    ui.show(fig, 300)
    dg = ts.set_index("product").loc["dangerous_goods"]
    ui.takeaway(f"Dangerous goods wait {dg['customer_h']:.1f} hours on the customer's clock against {dg['handler_h']:.1f} on "
                f"the terminal's. Across all cargo, the terminal accounts for {ui.pct(k['handler_share'])} of the wait.")

# ---------------------------------------------------------------- floor
ui.section("Each shift's workload", "How much each shift unpacks, and how much it leaves for the next, under the current "
                                    "roster.")
tp = ui.table("throughput").set_index("level")
bl = ui.table("backlog").set_index("level")
rows = [[s, ui.num(tp.loc[s, "staff_hours"]), ui.num(tp.loc[s, "value"]), ui.num(bl.loc[s, "value"]),
         ui.num(bl.loc[s, "p90"]), ui.num(bl.loc[s, "max"])] for s in ui.SHIFTS]
with ui.plate("Unpacking speed, and work handed to the next shift", "The whole history. Shipments left waiting are counted "
                                                                     "at the moment the shift ends"):
    ui.ledger(pd.DataFrame(rows, columns=["Shift", "Staff hours worked", "Kg unpacked per staff hour",
                                          "Left waiting: average", "On a bad day (1 in 10)", "Worst"]))
    hi, lo = tp["value"].idxmax(), tp["value"].idxmin()
    ui.takeaway(f"The {hi.lower()} shift unpacks {ui.num(tp.loc[hi, 'value'])} kg for each staff hour; the "
                f"{lo.lower()} shift {ui.num(tp.loc[lo, 'value'])} kg, because less freight lands then. The night shift "
                f"leaves the morning an average of {ui.num(bl.loc['Night', 'value'])} shipments still waiting to be unpacked.")

# ---------------------------------------------------------------- under the hood
ui.hood("The KPI dictionary as an analyst would write it: the formal definition, the formula over the milestone codes, "
        "and the DuckDB SQL that computes each measure. The milestones are ARR (aircraft arrival), RCF (received from "
        "flight), NFD (notified for delivery) and DLV (delivered); an AWB (air waybill) is one shipment.")
ui.ledger(kd[["name", "definition", "formula", "cut_by"]].rename(columns={
    "name": "KPI", "definition": "Definition", "formula": "Formula", "cut_by": "Cut by"}), doc=True)


@st.cache_data(show_spinner=False)
def dictionary_xlsx(csv: bytes) -> bytes:
    return kpis.dictionary_xlsx(pd.read_csv(io.BytesIO(csv)))


raw = (C.DATA / "kpi_dictionary.csv").read_bytes()
c1, c2, c3 = st.columns([0.5, 0.3, 0.2], vertical_alignment="bottom")
pick = c1.selectbox("Show the SQL for", kd["name"].tolist(), index=0)
c2.download_button("Download the dictionary (Excel)", dictionary_xlsx(raw), file_name="kpi_dictionary.xlsx",
                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary",
                   width="stretch")
c3.download_button("Or as CSV", raw, file_name="kpi_dictionary.csv", mime="text/csv", width="stretch")
st.code(kd.set_index("name").loc[pick, "sql"], language="sql")
ui.footer()
