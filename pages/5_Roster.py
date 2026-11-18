import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lab import config as C
from lab import ui

h = ui.headline()
cfg = C.load()
o = cfg["roster_opt"]
ui.page("roster", lede="The floor's main lever is how many people stand on each shift. Simulate each choice on the test "
                       "months, price labor against late freight, and let an integer program pick one headcount per "
                       "weekday and shift.")

ros = ui.table("rosters")
ev = ui.table("roster_eval").set_index("policy")
grid = {p: ros[ros["policy"] == p].pivot(index="shift", columns="weekday", values="headcount").to_numpy()
        for p in ("legacy", "optimized")}

# ---------------------------------------------------------------- rosters
ui.section("Legacy against optimized", f"Same weekly budget ({ui.num(ev.loc['legacy', 'staff_hours_per_week'])} staff "
                                       f"hours), no shift moved by more than {o['max_change']} people, at least "
                                       f"{o['min_headcount']} on any shift.")
lo, hi = min(g.min() for g in grid.values()), max(g.max() for g in grid.values())
scale = [[0, ui.SURFACE], [0.5, "#5e5440"], [1, ui.GOLD]]


def heat(z, text):
    fig = go.Figure(go.Heatmap(z=z, x=ui.WEEKDAYS, y=ui.SHIFTS, text=text, texttemplate="%{text}", colorscale=scale,
                               zmin=lo, zmax=hi, xgap=3, ygap=3, showscale=False,
                               textfont=dict(color=ui.INK, size=15, family=ui.SERIF),
                               hovertemplate="%{y}, %{x}<br>%{z} rostered<extra></extra>"))
    fig.update_yaxes(autorange="reversed", showgrid=False)
    fig.update_xaxes(showgrid=False, side="top")
    fig.update_layout(margin=dict(t=30, l=6, r=6, b=6))
    return fig


delta = grid["optimized"] - grid["legacy"]
c1, c2 = st.columns(2)
with c1:
    with ui.plate("Legacy roster", "Headcount by shift and weekday; flat across the week"):
        ui.show(heat(grid["legacy"], grid["legacy"].astype(str)), 230)
with c2:
    txt = np.vectorize(lambda v, d: f"{v} ({d:+d})" if d else f"{v}")(grid["optimized"], delta)
    with ui.plate("Optimized roster", "Change from legacy in brackets"):
        ui.show(heat(grid["optimized"], txt), 230)
night = grid["optimized"][2]
ui.takeaway(f"The optimizer takes staff off the afternoon, which handles the fewest arrivals, and moves night crews with "
            f"the freighter pattern: {night.min()} on the lightest nights, {night.max()} on {ui.WEEKDAYS[int(night.argmax())]}.")

rows = [
    ["NFD on time", ui.pct(ev.loc["legacy", "on_time"]), ui.pct(ev.loc["optimized", "on_time"]),
     ui.pts(ev.loc["optimized", "on_time"] - ev.loc["legacy", "on_time"])],
    ["Late AWBs per week", ui.num(ev.loc["legacy", "late_per_week"]), ui.num(ev.loc["optimized", "late_per_week"]),
     f"{ev.loc['optimized', 'late_per_week'] - ev.loc['legacy', 'late_per_week']:+,.0f}"],
    ["Staff hours per week", ui.num(ev.loc["legacy", "staff_hours_per_week"]), ui.num(ev.loc["optimized", "staff_hours_per_week"]),
     f"{ev.loc['optimized', 'staff_hours_per_week'] - ev.loc['legacy', 'staff_hours_per_week']:+,.0f}"],
    ["Labor cost per week", ui.usd(ev.loc["legacy", "labor_cost_per_week"]), ui.usd(ev.loc["optimized", "labor_cost_per_week"]),
     f"{ev.loc['optimized', 'labor_cost_per_week'] - ev.loc['legacy', 'labor_cost_per_week']:+,.0f}"],
    ["Late penalty per week", ui.usd(ev.loc["legacy", "penalty_per_week"]), ui.usd(ev.loc["optimized", "penalty_per_week"]),
     f"{ev.loc['optimized', 'penalty_per_week'] - ev.loc['legacy', 'penalty_per_week']:+,.0f}"],
    ["Total cost per week", ui.usd(ev.loc["legacy", "total_cost_per_week"]), ui.usd(ev.loc["optimized", "total_cost_per_week"]),
     f"{ev.loc['optimized', 'total_cost_per_week'] - ev.loc['legacy', 'total_cost_per_week']:+,.0f}"],
]
better = {0: ev.loc["optimized", "on_time"] >= ev.loc["legacy", "on_time"],
          5: ev.loc["optimized", "total_cost_per_week"] <= ev.loc["legacy", "total_cost_per_week"]}
tones = {(i, 3): ("gain" if b else "loss") for i, b in better.items()}
with ui.plate("Service and cost, test months", f"Re-simulated end to end, mean of {o['seeds']} seeds. Costs in synthetic "
                                                f"USD at ${cfg['hourly_cost_usd']} an hour and a penalty per late AWB by product"):
    ui.ledger(pd.DataFrame(rows, columns=["", "Legacy", "Optimized", "Change"]), em_rows=[0], tones=tones)
    ui.takeaway(h["sentences"]["roster"])
    opt = ev.loc["optimized"]
    ui.note(f"The grid behind the integer program predicted {opt['grid_late_per_week']:,.0f} late AWBs a week for this "
            f"roster; the end-to-end run gives {opt['late_per_week']:,.0f}. The gap is the cost of scoring each shift "
            f"on its own while backlog really carries from one shift to the next.")

cells = ui.table("roster_cells")
by = cells.groupby(["policy", "shift"])["on_time"].mean().unstack(0)
fig = go.Figure()
for p, color in (("legacy", ui.NEU), ("optimized", ui.GOLD)):
    fig.add_trace(go.Bar(x=ui.SHIFTS, y=by[p], name=p.capitalize(), marker=ui.hatched(color),
                         text=[ui.pct(v) for v in by[p]], textposition="outside", textfont=dict(color=ui.INK, size=12),
                         hovertemplate="%{x}<br>%{y:.1%} on time<extra>" + p + "</extra>"))
fig.update_yaxes(tickformat=".0%", range=[max(0, float(by.min().min()) - 0.08), 1.02])
fig.update_layout(barmode="group", margin=dict(t=36))
with ui.plate("NFD on time by arrival shift", "Mean over weekdays, test months"):
    ui.show(fig, 300)
    i = int((by["optimized"] - by["legacy"]).abs().idxmax())
    ui.takeaway(f"The biggest change is for freight arriving in the {ui.SHIFTS[i].lower()} shift: "
                f"{ui.pct(by.loc[i, 'legacy'])} on time under the legacy roster, {ui.pct(by.loc[i, 'optimized'])} optimized.")

# ---------------------------------------------------------------- frontier
ui.section("What more hours buy", "The best service each weekly budget can buy (the integer program without the labor "
                                  "term), each answer re-simulated.")
fr = ui.table("frontier")
fig = go.Figure()
fig.add_trace(go.Scatter(x=fr["staff_hours_per_week"], y=fr["on_time"], mode="lines+markers+text", name="Optimized at each budget",
                         line=dict(color=ui.GOLD, width=2), marker=dict(size=8, color=ui.GOLD),
                         text=[f"{m:.0%}" for m in fr["multiplier"]], textposition="bottom right",
                         textfont=dict(color=ui.MUTED, size=12),
                         hovertemplate="%{x:,.0f} staff hours a week<br>%{y:.1%} on time<extra></extra>"))
fig.add_trace(go.Scatter(x=[ev.loc["legacy", "staff_hours_per_week"]], y=[ev.loc["legacy", "on_time"]], mode="markers+text",
                         name="Legacy roster", marker=dict(size=12, color="rgba(0,0,0,0)", line=dict(color=ui.INK, width=2)),
                         text=["Legacy"], textposition="top left", textfont=dict(color=ui.INK, size=12),
                         hovertemplate="Legacy<br>%{x:,.0f} staff hours<br>%{y:.1%} on time<extra></extra>"))
fig.add_trace(go.Scatter(x=[ev.loc["optimized", "staff_hours_per_week"]], y=[ev.loc["optimized", "on_time"]],
                         mode="markers+text", name="The plan (labor plus penalties)",
                         marker=dict(size=13, symbol="diamond", color=ui.GAIN, line=dict(color=ui.INK, width=1)),
                         text=["Plan"], textposition="top left", textfont=dict(color=ui.GAIN_INK, size=12),
                         hovertemplate="The plan<br>%{x:,.0f} staff hours<br>%{y:.1%} on time<extra></extra>"))
fig.update_xaxes(title_text="Staff hours per week", tickformat=",")
fig.update_yaxes(title_text="NFD on time", tickformat=".1%")
fig.update_layout(margin=dict(t=36))
with ui.plate("Staff hours against on-time performance", "Labels give the budget as a share of the legacy roster's hours"):
    ui.show(fig, 340)
    f0 = fr.iloc[0]
    f1 = fr.iloc[-1]
    same = fr.iloc[(fr["multiplier"] - 1).abs().argmin()]
    ui.takeaway(f"At {f0['multiplier']:.0%} of legacy hours the best roster delivers {ui.pct(f0['on_time'])}; at "
                f"{f1['multiplier']:.0%} it reaches {ui.pct(f1['on_time'])}. Legacy spends "
                f"{ui.num(ev.loc['legacy', 'staff_hours_per_week'])} hours for {ui.pct(ev.loc['legacy', 'on_time'])}. " +
                (f"The plan stops at {ui.num(ev.loc['optimized', 'staff_hours_per_week'])} hours, below its budget, because at "
                 f"the illustrative penalties more hours would cost more than the lateness they remove."
                 if ev.loc["optimized", "staff_hours_per_week"] < ev.loc["legacy", "staff_hours_per_week"] * o["budget_multiplier"] - 1
                 else "The plan uses its whole budget."))

# ---------------------------------------------------------------- how
ui.section("How the roster is chosen")
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
ui.prose(f"Here c is the hourly cost, P is the total weekly late penalty the grid recorded with that cell at headcount h, "
         f"and B is the weekly staff-hour budget. PuLP builds the model and CBC solves it to proven optimality. Adding up "
         f"one-at-a-time effects ignores how cells interact through backlog carried from one shift to the next, so every "
         f"roster on this page is re-simulated end to end before it is reported. The frontier drops the labor term and "
         f"asks a different question: the best service each budget can buy.")
ui.footer()
