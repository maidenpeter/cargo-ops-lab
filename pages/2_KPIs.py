import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lab import config as C
from lab import kpis
from lab import ui

ui.page("kpis", lede="Before anyone can say the terminal is late, someone has to say what late means. Eight measures on "
                     "the Cargo iQ import milestones, each with a formula, the SQL that computes it, an owner, and the "
                     "decision it informs.")

# ---------------------------------------------------------------- dictionary
ui.section("The KPI dictionary", "The table interviewers should read first. Owner says whose clock the measure runs on.")
kd = pd.read_csv(C.DATA / "kpi_dictionary.csv")
ui.ledger(kd[["name", "definition", "formula", "owner", "decision"]].rename(columns={
    "name": "Measure", "definition": "Definition", "formula": "Formula", "owner": "Owner", "decision": "Decision it informs"}),
    doc=True, cls="kd-table")
st.markdown('<div class="kd-cards">' + "".join(
    f'<div class="kd-card"><b>{ui.esc(r.name)}</b><span class="own">{ui.esc(r.owner)}</span><p>{ui.esc(r.definition)}</p>'
    f'<p class="f">{ui.esc(r.formula)}</p><p>Informs: {ui.esc(r.decision)}</p></div>' for r in kd.itertuples()) + "</div>",
    unsafe_allow_html=True)
c1, c2 = st.columns([0.62, 0.38], vertical_alignment="bottom")
pick = c1.selectbox("Show the SQL for", kd["name"].tolist(), index=0)
c2.download_button("Download the dictionary (CSV)", (C.DATA / "kpi_dictionary.csv").read_bytes(),
                   file_name="kpi_dictionary.csv", mime="text/csv", width="stretch")
st.code(kd.set_index("name").loc[pick, "sql"], language="sql")

# ---------------------------------------------------------------- live measures
ui.section("The measures, filtered", "Pick products, carriers or arrival shifts. The numbers below rerun the same SQL on "
                                     "the cleaned AWBs.")
con = ui.db()
f1, f2, f3 = st.columns(3)
prods = list(ui.PRODUCT_LABELS)
sel_p = f1.multiselect("Product", prods, format_func=ui.PRODUCT_LABELS.get, placeholder="All products")
carriers = sorted(C.timetable()["carrier"].unique())
sel_c = f2.multiselect("Carrier", carriers, placeholder="All carriers")
sel_s = f3.multiselect("Arrival shift", ui.SHIFTS, placeholder="All shifts")
src = ui.filtered(sel_p, sel_c, sel_s)
fmt = {"awb": src}
ot = kpis.run(con, "kpis.sql", "nfd_on_time", fmt).iloc[0]
if ot["scored"] == 0:
    st.info("No AWBs match these filters.")
    st.stop()
ht = kpis.run(con, "kpis.sql", "handler_time", fmt).iloc[0]
lp = kpis.run(con, "kpis.sql", "late_per_1000", fmt).iloc[0]
ui.proof([
    {"k": "NFD on time", "v": ui.pct(ot["value"]), "d": f"{ui.num(ot['scored'])} AWBs scored"},
    {"k": "Handler time p50", "v": ui.hrs(ht["p50_h"]), "d": "Arrival to freight ready, median"},
    {"k": "Handler time p90", "v": ui.hrs(ht["p90_h"]), "d": "The slowest tenth take longer than this"},
    {"k": "Late per 1,000", "v": ui.num(lp["value"]), "d": "Late AWBs per thousand scored", "tone": "loss"},
])

mo = kpis.run(con, "kpis.sql", "monthly", fmt)
fig = go.Figure(go.Scatter(x=mo["arr_month"], y=mo["on_time"], mode="lines+markers", line=dict(color=ui.GAIN, width=2),
                           marker=dict(size=6, color=ui.GAIN), hovertemplate="%{x|%B %Y}<br>%{y:.1%} on time<extra></extra>"))
fig.update_yaxes(tickformat=".0%", title_text="NFD on time")
fig.update_xaxes(tickformat="%b<br>%Y", dtick="M2")
with ui.plate("NFD on time, month by month", "Share of AWBs ready within the promise, by month of arrival"):
    ui.show(fig, 280)
    worst = mo.loc[mo["on_time"].idxmin()]
    ui.takeaway(f"The weakest month was {worst['arr_month']:%B %Y} at {ui.pct(worst['on_time'])}; the best was "
                f"{ui.pct(mo['on_time'].max())}. The roster is the same every week of the history, so the swings come from the arrivals.")

hm = kpis.run(con, "kpis.sql", "on_time_hour_weekday", fmt)
grid = hm.pivot(index="arr_weekday", columns="arr_hour", values="value").reindex(index=range(7), columns=range(24))
cnt = hm.pivot(index="arr_weekday", columns="arr_hour", values="scored").reindex(index=range(7), columns=range(24))
fig = go.Figure(go.Heatmap(z=grid.values, x=[f"{h:02d}" for h in range(24)], y=ui.WEEKDAYS, customdata=cnt.values,
                           colorscale=ui.diverging(ot["value"], float(hm["value"].min()), 1.0), zmin=float(hm["value"].min()),
                           zmax=1.0, xgap=2, ygap=2, colorbar=dict(tickformat=".0%", outlinewidth=0, thickness=10, len=0.9,
                                                                  tickfont=dict(color=ui.MUTED, size=12)),
                           hovertemplate="%{y} %{x}:00<br>%{z:.1%} on time<br>%{customdata:,} AWBs<extra></extra>"))
fig.update_yaxes(autorange="reversed", showgrid=False)
fig.update_xaxes(showgrid=False, title_text="Hour of aircraft arrival (hub local)")
with ui.plate("When late freight arrives", "NFD on time by hour of arrival and weekday. Oxblood is below the average for "
                                           "the filter, teal above."):
    ui.show(fig, 330)
    h = hm[hm["scored"] >= 30]
    lo = h.loc[h["value"].idxmin()]
    why = (" Flights landing as the night bank ends queue behind the freighters' backlog."
           if 3 <= int(lo["arr_hour"]) <= 9 and not sel_s else "")
    ui.takeaway(f"The weakest hour is {ui.WEEKDAYS[int(lo['arr_weekday'])]} at {int(lo['arr_hour']):02d}:00, with "
                f"{ui.pct(lo['value'])} on time.{why}")

# ---------------------------------------------------------------- products
ui.section("Which products miss the promise", "Each product has its own promise from arrival to ready (an illustrative "
                                               "assumption, set in the config).")
by = ui.table("kpi_by")
bp = by[by["dim"] == "Product"].copy()
ht_p = ui.table("handler_time_by_product").set_index("product")
bp["label"] = bp["level"].map(ui.PRODUCT_LABELS) + "  (" + bp["level"].map(ht_p["sla_h"]).astype(int).astype(str) + " h)"
bp = bp.sort_values("value")
overall = ui.table("kpi_summary").set_index("kpi")["value"]["nfd_on_time"]
colors = [ui.LOSS if v < overall else ui.GAIN for v in bp["value"]]
fig = go.Figure()
fig.add_trace(go.Scatter(x=bp["value"], y=bp["label"], mode="markers+text", marker=dict(size=13, color=colors),
                         text=[ui.pct(v) for v in bp["value"]], textposition="middle right",
                         textfont=dict(color=ui.INK, size=13), hovertemplate="%{y}<br>%{x:.1%} on time<extra></extra>"))
for v, y in zip(bp["value"], bp["label"]):
    fig.add_shape(type="line", x0=0.5, x1=v, y0=y, y1=y, line=dict(color=ui.RULE_STRONG, width=1))
fig.add_vline(x=overall, line=dict(color=ui.GOLD, width=1, dash="dot"))
fig.add_annotation(x=overall, y=1.06, yref="paper", text=f"All products {ui.pct(overall)}", showarrow=False,
                   font=dict(color=ui.GOLD, size=12))
fig.update_xaxes(range=[0.5, 1.04], tickformat=".0%")
fig.update_layout(showlegend=False, margin=dict(t=30))
with ui.plate("NFD on time by product", "Promise in hours in brackets. All AWBs scored, cleaned data"):
    ui.show(fig, 300)
    la = ht_p.loc["live_animals"]
    ui.takeaway(f"Live animals meet their {int(la['sla_h'])}-hour promise only {ui.pct(bp.set_index('level').loc['live_animals', 'value'])} "
                f"of the time, though they jump the queue. Arrival to RCF alone averages {la['arr_to_rcf_min']:.0f} minutes "
                f"(tow, offload and breakdown), and the document check adds {la['rcf_to_nfd_min']:.0f}. The promise, not the "
                f"floor, is the first thing to question.")

ts = ui.table("time_split").copy()
ts["label"] = ts["product"].map(ui.PRODUCT_LABELS)
ts = ts.sort_values("customer_h")
fig = go.Figure()
fig.add_trace(go.Bar(y=ts["label"], x=ts["handler_h"], orientation="h", name="Handler: arrival to ready",
                     marker=ui.hatched(ui.GOLD), hovertemplate="%{y}<br>handler %{x:.1f} h<extra></extra>"))
fig.add_trace(go.Bar(y=ts["label"], x=ts["customer_h"], orientation="h", name="Customer: ready to delivered",
                     marker=ui.hatched(ui.CTX), hovertemplate="%{y}<br>customer %{x:.1f} h<extra></extra>"))
fig.update_layout(barmode="stack", margin=dict(t=36))
fig.update_xaxes(title_text="Mean hours")
with ui.plate("Handler time against customer time", "Mean hours on each clock, by product"):
    ui.show(fig, 300)
    dg = ts.set_index("product").loc["dangerous_goods"]
    ui.takeaway(f"Dangerous goods sit {dg['customer_h']:.1f} hours on the customer's clock against {dg['handler_h']:.1f} on "
                f"the handler's. Across all products the handler holds {ui.pct(ui.table('kpi_summary').set_index('kpi')['value']['handler_share'])} of dwell.")

# ---------------------------------------------------------------- floor
ui.section("The floor, shift by shift", "Throughput and the work each shift hands to the next, from the shift log.")
tp = ui.table("throughput").set_index("level")
bl = ui.table("backlog").set_index("level")
rows = []
for s in ui.SHIFTS:
    rows.append([s, ui.num(tp.loc[s, "staff_hours"]), ui.num(tp.loc[s, "value"]), ui.num(bl.loc[s, "value"]),
                 ui.num(bl.loc[s, "p90"]), ui.num(bl.loc[s, "max"])])
with ui.plate("Breakdown throughput and backlog at shift end", "Legacy roster, the whole history"):
    ui.ledger(pd.DataFrame(rows, columns=["Shift", "Present staff hours", "Kg per staff hour", "Backlog at end, mean",
                                          "Backlog p90", "Backlog max"]))
    hi, lo = tp["value"].idxmax(), tp["value"].idxmin()
    ui.takeaway(f"The {hi.lower()} shift breaks down {ui.num(tp.loc[hi, 'value'])} kg per present staff hour; the "
                f"{lo.lower()} shift {ui.num(tp.loc[lo, 'value'])} kg. The night shift hands the morning an average of "
                f"{ui.num(bl.loc['Night', 'value'])} AWBs still waiting for breakdown.")
ui.footer()
