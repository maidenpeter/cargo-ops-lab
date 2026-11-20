import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lab import config as C
from lab import ui

h = ui.headline()
cfg = C.load()
o = cfg["roster_opt"]
ros = ui.table("rosters")
ev = ui.table("roster_eval").set_index("policy")
grid = {p: ros[ros["policy"] == p].pivot(index="shift", columns="weekday", values="headcount").to_numpy()
        for p in ("legacy", "optimized")}
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
test0 = pd.Timestamp(cfg["split"]["valid_end"]) + pd.Timedelta(days=1)
test = f"{test0:%B} to {pd.Timestamp(cfg['window']['cutoff']):%B %Y}"
saved = ev.loc["legacy", "staff_hours_per_week"] - ev.loc["optimized", "staff_hours_per_week"]
flat = bool((grid["legacy"] == grid["legacy"][:, :1]).all())  # the same headcount every day of the week

ui.page("roster")
ui.short(
    "How many people should work each shift, on each day of the week?",
    ("The current roster puts the same number of people on each shift every day. " if flat else "")
    + f"A recommended roster, found by trying "
    f"staff levels in the simulation and weighing wages against late penalties, gets <b>{ui.pct(h['opt_on_time'])}</b> "
    f"of shipments ready on time against {ui.pct(h['legacy_on_time'])} today"
    + (f", with {saved:,.0f} fewer staff hours a week." if saved > 0.5 else "."),
    "Putting people where the freight actually lands can improve service and cost less at the same time. The same "
    "method can test any proposed roster before anyone's shift changes.",
)

# ---------------------------------------------------------------- rosters
ui.section("The current roster against the recommended one",
           f"Both stay within the same weekly budget of {ui.num(ev.loc['legacy', 'staff_hours_per_week'])} staff hours. "
           f"No shift changes by more than {o['max_change']} people, and every shift keeps at least {o['min_headcount']}.")
lo, hi = min(g.min() for g in grid.values()), max(g.max() for g in grid.values())
scale = [[0, ui.SURFACE], [0.5, "#5e5440"], [1, ui.GOLD]]


def heat(z, text):
    fig = go.Figure(go.Heatmap(z=z, x=ui.WEEKDAYS, y=ui.SHIFTS, text=text, texttemplate="%{text}", colorscale=scale,
                               zmin=lo, zmax=hi, xgap=3, ygap=3, showscale=False,
                               textfont=dict(color=ui.INK, size=15, family=ui.SERIF),
                               hovertemplate="%{y}, %{x}<br>%{z} people<extra></extra>"))
    fig.update_yaxes(autorange="reversed", showgrid=False)
    fig.update_xaxes(showgrid=False, side="top")
    fig.update_layout(margin=dict(t=30, l=6, r=6, b=6))
    return fig


delta = grid["optimized"] - grid["legacy"]
c1, c2 = st.columns(2)
with c1:
    with ui.plate("Current roster", "People on each shift" + (", the same every day" if flat else "")):
        ui.show(heat(grid["legacy"], grid["legacy"].astype(str)), 230)
with c2:
    txt = np.vectorize(lambda v, d: f"{v} ({d:+d})" if d else f"{v}")(grid["optimized"], delta)
    with ui.plate("Recommended roster", "Change from the current roster in brackets"):
        ui.show(heat(grid["optimized"], txt), 230)
prof = ui.table("arrival_profile")
pb = prof[prof["scenario"] == "s00_v00"].set_index("hour")["awbs_per_day"]
starts, hours = cfg["shifts"]["starts"], cfg["shifts"]["hours"]
land = [sum(pb.get((s + i) % 24, 0.0) for i in range(hours)) for s in starts]
quiet = int(np.argmin(land))
wk = delta.sum(axis=1)
night = grid["optimized"][2]
parts = []
if wk[quiet] < 0:
    parts.append(f"takes people off the {ui.SHIFTS[quiet].lower()}, when the least freight lands")
if (night != night[0]).any():
    parts.append(f"varies the night crew with the flights: {night.min()} on the lightest nights, {night.max()} on "
                 f"{DAYS[int(night.argmax())]}s")
ui.takeaway("The recommended roster " + " and ".join(parts) + "." if parts else
            "The recommended roster keeps the shape of the current one.")

rows = [
    ["Ready on time", ui.pct(ev.loc["legacy", "on_time"]), ui.pct(ev.loc["optimized", "on_time"]),
     ui.pts(ev.loc["optimized", "on_time"] - ev.loc["legacy", "on_time"])],
    ["Late shipments per week", ui.num(ev.loc["legacy", "late_per_week"]), ui.num(ev.loc["optimized", "late_per_week"]),
     f"{ev.loc['optimized', 'late_per_week'] - ev.loc['legacy', 'late_per_week']:+,.0f}"],
    ["Staff hours per week", ui.num(ev.loc["legacy", "staff_hours_per_week"]), ui.num(ev.loc["optimized", "staff_hours_per_week"]),
     f"{ev.loc['optimized', 'staff_hours_per_week'] - ev.loc['legacy', 'staff_hours_per_week']:+,.0f}"],
    ["Wages per week", ui.usd(ev.loc["legacy", "labor_cost_per_week"]), ui.usd(ev.loc["optimized", "labor_cost_per_week"]),
     f"{ev.loc['optimized', 'labor_cost_per_week'] - ev.loc['legacy', 'labor_cost_per_week']:+,.0f}"],
    ["Late penalties per week", ui.usd(ev.loc["legacy", "penalty_per_week"]), ui.usd(ev.loc["optimized", "penalty_per_week"]),
     f"{ev.loc['optimized', 'penalty_per_week'] - ev.loc['legacy', 'penalty_per_week']:+,.0f}"],
    ["Total cost per week", ui.usd(ev.loc["legacy", "total_cost_per_week"]), ui.usd(ev.loc["optimized", "total_cost_per_week"]),
     f"{ev.loc['optimized', 'total_cost_per_week'] - ev.loc['legacy', 'total_cost_per_week']:+,.0f}"],
]
better = {0: ev.loc["optimized", "on_time"] >= ev.loc["legacy", "on_time"],
          5: ev.loc["optimized", "total_cost_per_week"] <= ev.loc["legacy", "total_cost_per_week"]}
tones = {(i, 3): ("gain" if b else "loss") for i, b in better.items()}
with ui.plate("Service and cost", f"Both rosters tested on the same freight, {test}, averaged over {o['seeds']} runs. "
                                  f"Costs are illustrative: ${cfg['hourly_cost_usd']} an hour, and a penalty for each late "
                                  f"shipment that is higher for urgent cargo"):
    ui.ledger(pd.DataFrame(rows, columns=["", "Current", "Recommended", "Change"]), em_rows=[0], tones=tones)
    ui.takeaway(h["sentences"]["roster"])

cells = ui.table("roster_cells")
by = cells.groupby(["policy", "shift"])["on_time"].mean().unstack(0)
fig = go.Figure()
for p, color, name in (("legacy", ui.NEU, "Current"), ("optimized", ui.GOLD, "Recommended")):
    fig.add_trace(go.Bar(x=ui.SHIFTS, y=by[p], name=name, marker=ui.hatched(color),
                         text=[ui.pct(v) for v in by[p]], textposition="outside", textfont=dict(color=ui.INK, size=12),
                         hovertemplate="%{x}<br>%{y:.1%} on time<extra>" + name + "</extra>"))
fig.update_yaxes(tickformat=".0%", range=[max(0, float(by.min().min()) - 0.08), 1.02])
fig.update_layout(barmode="group", margin=dict(t=36))
with ui.plate("Ready on time by the shift the plane lands in", f"Average over the days of the week, {test}"):
    ui.show(fig, 300)
    i = int((by["optimized"] - by["legacy"]).abs().idxmax())
    ui.takeaway(f"The biggest change is for freight landing in the {ui.SHIFTS[i].lower()} shift: "
                f"{ui.pct(by.loc[i, 'legacy'])} on time under the current roster, {ui.pct(by.loc[i, 'optimized'])} under "
                f"the recommended one.")

# ---------------------------------------------------------------- frontier
ui.section("What extra staff hours buy", "The best service each weekly budget can buy, ignoring wages, with each answer "
                                         "tested end to end in the simulation.")
fr = ui.table("frontier")
fig = go.Figure()
fig.add_trace(go.Scatter(x=fr["staff_hours_per_week"], y=fr["on_time"], mode="lines+markers+text", name="Best roster for each budget",
                         line=dict(color=ui.GOLD, width=2), marker=dict(size=8, color=ui.GOLD),
                         text=[f"{x:.0%}" for x in fr["multiplier"]], textposition="bottom right",
                         textfont=dict(color=ui.MUTED, size=12),
                         hovertemplate="%{x:,.0f} staff hours a week<br>%{y:.1%} on time<extra></extra>"))
fig.add_trace(go.Scatter(x=[ev.loc["legacy", "staff_hours_per_week"]], y=[ev.loc["legacy", "on_time"]], mode="markers+text",
                         name="Current roster", marker=dict(size=12, color="rgba(0,0,0,0)", line=dict(color=ui.INK, width=2)),
                         text=["Current"], textposition="top left", textfont=dict(color=ui.INK, size=12),
                         hovertemplate="Current<br>%{x:,.0f} staff hours<br>%{y:.1%} on time<extra></extra>"))
fig.add_trace(go.Scatter(x=[ev.loc["optimized", "staff_hours_per_week"]], y=[ev.loc["optimized", "on_time"]],
                         mode="markers+text", name="Recommended (wages plus penalties)",
                         marker=dict(size=13, symbol="diamond", color=ui.GAIN, line=dict(color=ui.INK, width=1)),
                         text=["Recommended"], textposition="top left", textfont=dict(color=ui.GAIN_INK, size=12),
                         hovertemplate="Recommended<br>%{x:,.0f} staff hours<br>%{y:.1%} on time<extra></extra>"))
fig.update_xaxes(title_text="Staff hours per week", tickformat=",")
fig.update_yaxes(title_text="Ready on time", tickformat=".1%")
fig.update_layout(margin=dict(t=36))
with ui.plate("Staff hours against on-time performance", "Labels give each budget as a share of the current roster's hours"):
    ui.show(fig, 340)
    f0, f1 = fr.iloc[0], fr.iloc[-1]
    stops = (f"The recommended roster stops at {ui.num(ev.loc['optimized', 'staff_hours_per_week'])} hours, below its "
             f"budget, because at the illustrative penalties more hours would cost more than the lateness they prevent."
             if ev.loc["optimized", "staff_hours_per_week"] < ev.loc["legacy", "staff_hours_per_week"] * o["budget_multiplier"] - 1
             else "The recommended roster uses its whole budget.")
    ui.takeaway(f"With {f0['multiplier']:.0%} of today's hours, the best roster gets {ui.pct(f0['on_time'])} on time; with "
                f"{f1['multiplier']:.0%}, {ui.pct(f1['on_time'])}. The current roster spends "
                f"{ui.num(ev.loc['legacy', 'staff_hours_per_week'])} hours for {ui.pct(ev.loc['legacy', 'on_time'])}. {stops}")

# ---------------------------------------------------------------- under the hood
ui.hood("How the roster is chosen: a grid of simulations, an integer program solved with PuLP and CBC, and an end-to-end "
        "re-simulation of every answer. Legacy is the current roster; optimized is the recommended one.")
ui.prose(
    "A grid of simulations comes first. One weekday and shift at a time, the headcount moves through its allowed range "
    "while every other cell stays at a base roster; each point runs the whole test period over "
    f"{o['seeds']} seeds and records the total late AWBs and their penalty. Common random numbers keep the comparison "
    "fair: every run sees the same freight, the same work content and the same absences. A second pass rebuilds the "
    "grid around the first answer.",
    "The integer program then picks one headcount for each of the 21 weekday and shift cells:",
)
st.latex(r"\min \sum_{d,s,h} x_{dsh}\,\big(h \cdot 8 \cdot c + P_{dsh}\big) \quad \text{s.t.} \quad \sum_h x_{dsh} = 1,"
         r"\quad \sum_{d,s,h} 8\,h\,x_{dsh} \le B,\quad |h - h^{\text{legacy}}_{ds}| \le " + str(o["max_change"]) +
         r",\quad x_{dsh} \in \{0,1\}")
opt = ev.loc["optimized"]
ui.prose(f"Here c is the hourly cost, P is the total weekly late penalty the grid recorded with that cell at headcount h, "
         f"and B is the weekly staff-hour budget. PuLP builds the model and CBC solves it to proven optimality. Adding up "
         f"one-at-a-time effects ignores how cells interact through backlog carried from one shift to the next, so every "
         f"roster on this page is re-simulated end to end before it is reported. The grid predicted "
         f"{opt['grid_late_per_week']:,.0f} late AWBs a week for the optimized roster; the end-to-end run gives "
         f"{opt['late_per_week']:,.0f}. The frontier drops the labor term and asks a different question: the best service "
         f"each budget can buy.")
ui.footer()
