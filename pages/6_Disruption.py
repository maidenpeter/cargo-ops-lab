import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lab import config as C
from lab import scenarios as X
from lab import ui

h = ui.headline()
cfg = C.load()
d = cfg["disruption"]
ui.page("disruption", lede="A regional disruption forces schedule changes: a share of flights is moved into compressed "
                           "arrival waves while volume falls. The roster and the risk model were both built on the normal "
                           "timetable. How far does each drift, and what does re-planning recover?")

dis = ui.table("disruption")
drift = ui.table("drift").set_index("scenario")
prof = ui.table("arrival_profile")
LABEL = X.POLICIES
SHORT = {"legacy": "Legacy", "static": "Static", "replanned": "Re-planned", "flex": "Call-in pool"}
COLOR = {"legacy": ui.NEU, "static": ui.GOLD, "replanned": ui.GAIN, "flex": ui.INK2}

st.markdown(f'<p class="note" style="font-family:var(--serif);font-size:1.18rem;line-height:1.5">'
            f'{ui.esc(h["sentences"]["headline"])} {ui.esc(h["sentences"]["flex"])} {ui.esc(h["sentences"]["volume"])}</p>',
            unsafe_allow_html=True)

# ---------------------------------------------------------------- controls
ui.section("Break the schedule", "Sliders snap to the precomputed grid. Every number below is a stored simulation result.")
c1, c2, c3 = st.columns([0.3, 0.3, 0.4])
share = c1.select_slider("Flights moved into waves", options=d["rescheduled_shares"], value=0.0,
                         format_func=lambda v: f"{v:.0%}")
vol = c2.select_slider("Change in volume", options=sorted(d["volume_changes"], reverse=True), value=0.0,
                       format_func=lambda v: f"{v:+.0%}" if v else "0%")
pol = c3.segmented_control("Policy", list(LABEL), format_func=SHORT.get, default="static", selection_mode="single") or "static"
key = X.key(share, vol)
cur = dis[dis["scenario"] == key].set_index("policy")
base = dis[dis["scenario"] == X.key(0.0, 0.0)].set_index("policy")


def scenario_sentence(share: float, vol: float, cur: pd.DataFrame) -> str:
    if share == 0 and vol == 0:
        return (f"This is the normal timetable: the roster built on it delivers {ui.pct(cur.loc['static', 'on_time'])} on "
                f"time, and re-planning returns the same roster. Move the first slider to break the schedule.")
    v = f" and {-vol:.0%} less freight" if vol else ""
    if share == 0:
        start = f"On the normal timetable{v}, the roster built on the normal timetable delivers {ui.pct(cur.loc['static', 'on_time'])} on time."
    else:
        start = (f"When {share:.0%} of flights bunch into waves{v}, the roster built on the normal timetable delivers "
                 f"{ui.pct(cur.loc['static', 'on_time'])} on time.")
    extra = cur.loc["replanned", "staff_hours_per_week"] - cur.loc["static", "staff_hours_per_week"]
    cost = ("with the same staff hours" if abs(extra) < 0.5 else
            f"for {extra:,.0f} more staff hours a week" if extra > 0 else f"with {-extra:,.0f} fewer staff hours a week")
    rp = cur.loc["replanned", "on_time"]
    if rp > cur.loc["static", "on_time"]:
        end = f"Re-planning from the live schedule gets to {ui.pct(rp)} {cost}."
    else:
        end = f"Re-planning does not beat it: {ui.pct(rp)} {cost}."
    return f"{start} {end}"


st.markdown(f'<p class="lede" style="color:var(--ink);max-width:80ch">{ui.esc(scenario_sentence(share, vol, cur))}</p>',
            unsafe_allow_html=True)
p = cur.loc[pol]
hours = p["staff_hours_per_week"] + p["flex_hours_per_week"]
dl = p["on_time"] - base.loc[pol, "on_time"]
ui.proof([
    {"k": f"{SHORT[pol]}: NFD on time", "v": ui.pct(p["on_time"]), "tone": "gain" if dl >= 0 else "loss",
     "d": f"{ui.pts(dl)} against the normal timetable" if key != X.key(0.0, 0.0) else "the normal timetable"},
    {"k": "Late AWBs per week", "v": ui.num(p["late_per_week"]), "d": f"of {ui.num(p['awbs_per_week'])} landing each week"},
    {"k": "Staff hours per week", "v": ui.num(hours),
     "d": f"including {ui.num(p['flex_hours_per_week'])} call-in hours" if pol == "flex" else "rostered hours"},
    {"k": "Cost per week", "v": ui.usd(p["total_cost_per_week"]), "d": "labor plus late penalties, synthetic USD"},
])

rows, em = [], []
for i, k in enumerate(["legacy", "static", "replanned", "flex"]):
    r = cur.loc[k]
    rows.append([LABEL[k], ui.pct(r["on_time"]), ui.num(r["late_per_week"]),
                 ui.num(r["staff_hours_per_week"] + r["flex_hours_per_week"]),
                 ui.num(r["callins_per_week"], 1) if k == "flex" else "", ui.usd(r["total_cost_per_week"])])
    if k == pol:
        em.append(i)
with ui.plate("Four policies against the same arrivals", f"Mean of {cfg['roster_opt']['seeds']} seeds over the test months. Re-planning "
                                                         f"assumes the disrupted schedule is known {d['notice_hours']} hours ahead"):
    ui.ledger(pd.DataFrame(rows, columns=["Policy", "On time", "Late per week", "Staff hours per week", "Call-ins per week",
                                          "Cost per week"]), em_rows=em)
    order = cur["on_time"].sort_values(ascending=False)
    ui.takeaway(f"Ranked on time here: " + ", then ".join(f"{SHORT[k].lower()} {ui.pct(v)}" for k, v in order.items()) + ".")
    rp_, st_ = cur.loc["replanned"], cur.loc["static"]
    if rp_["staff_hours_per_week"] < st_["staff_hours_per_week"] - 0.5 and rp_["on_time"] < st_["on_time"]:
        ui.note(f"Re-planning minimizes labor cost plus late penalties, like the plan does. With less freight it gives back "
                f"{st_['staff_hours_per_week'] - rp_['staff_hours_per_week']:,.0f} staff hours a week and accepts lateness "
                f"the illustrative penalties do not cover: its total cost here is {ui.usd(rp_['total_cost_per_week'])} a week "
                f"against {ui.usd(st_['total_cost_per_week'])}.")

# ---------------------------------------------------------------- arrivals
pb = prof[prof["scenario"] == X.key(0.0, 0.0)].set_index("hour")["awbs_per_day"]
ps = prof[prof["scenario"] == key].set_index("hour")["awbs_per_day"]
fig = go.Figure()
fig.add_trace(go.Bar(x=ps.index, y=ps.values, name="This scenario", marker=ui.hatched(ui.GOLD),
                     hovertemplate="%{x}:00<br>%{y:.0f} AWBs a day<extra>scenario</extra>"))
fig.add_trace(go.Scatter(x=pb.index, y=pb.values, name="Normal timetable", mode="lines", line=dict(color=ui.INK2, width=2, shape="hvh"),
                         hovertemplate="%{x}:00<br>%{y:.0f} AWBs a day<extra>normal</extra>"))
fig.update_xaxes(title_text="Hour of aircraft arrival (hub local)", dtick=2)
fig.update_yaxes(title_text="AWBs a day")
fig.update_layout(margin=dict(t=36), bargap=0.12)
waves = ", ".join(d["wave_centers"])
with ui.plate("When the freight lands", f"Average AWBs arriving in each hour. Waves center on {waves}"):
    ui.show(fig, 300)
    hr = int((ps - pb).idxmax())
    ui.takeaway(f"At {hr:02d}:00 the scenario lands {ps[hr]:.0f} AWBs a day against {pb[hr]:.0f} on the normal timetable."
                if share else "This is the normal timetable. Move the first slider to bunch flights into waves.")

# ---------------------------------------------------------------- fragility
sub = dis[dis["volume_change"] == vol]
fig = go.Figure()
for k in ["legacy", "static", "flex", "replanned"]:
    s = sub[sub["policy"] == k].sort_values("share")
    fig.add_trace(go.Scatter(x=s["share"], y=s["on_time"], mode="lines+markers", name=SHORT[k],
                             line=dict(color=COLOR[k], width=3 if k == pol else 1.6),
                             marker=dict(size=9 if k == pol else 6, color=COLOR[k]),
                             hovertemplate="%{x:.0%} moved<br>%{y:.1%} on time<extra>" + SHORT[k] + "</extra>"))
fig.add_vline(x=share, line=dict(color=ui.RULE_STRONG, width=1, dash="dot"))
fig.update_xaxes(tickformat=".0%", title_text="Share of flights moved into waves", tickvals=d["rescheduled_shares"])
fig.update_yaxes(tickformat=".0%", title_text="NFD on time")
fig.update_layout(margin=dict(t=36))
with ui.plate("How each policy holds up as waves grow", f"Volume change {vol:+.0%}" if vol else "Volume unchanged"):
    ui.show(fig, 340)
    s0 = sub[(sub["share"] == 0) & (sub["policy"] == "static")]["on_time"].iloc[0]
    s6 = sub[(sub["share"] == max(d["rescheduled_shares"])) & (sub["policy"] == "static")]["on_time"].iloc[0]
    r6 = sub[(sub["share"] == max(d["rescheduled_shares"])) & (sub["policy"] == "replanned")]["on_time"].iloc[0]
    ui.takeaway(f"The static roster falls from {ui.pct(s0)} to {ui.pct(s6)} as the moved share goes from 0% to "
                f"{max(d['rescheduled_shares']):.0%}; re-planned, it holds {ui.pct(r6)}.")

# ---------------------------------------------------------------- re-planned roster
drs = ui.table("disruption_rosters")
ros = ui.table("rosters")
st_g = ros[ros["policy"] == "optimized"].pivot(index="shift", columns="weekday", values="headcount").to_numpy()
rp_g = drs[drs["scenario"] == key].pivot(index="shift", columns="weekday", values="headcount").to_numpy()
dlt = rp_g - st_g
txt = np.vectorize(lambda v, x: f"{v} ({x:+d})" if x else f"{v}")(rp_g, dlt)
lo, hi = min(st_g.min(), rp_g.min()), max(st_g.max(), rp_g.max())
fig = go.Figure(go.Heatmap(z=rp_g, x=ui.WEEKDAYS, y=ui.SHIFTS, text=txt, texttemplate="%{text}",
                           colorscale=[[0, ui.SURFACE], [0.5, "#5e5440"], [1, ui.GOLD]], zmin=lo, zmax=hi, xgap=3, ygap=3,
                           showscale=False, textfont=dict(color=ui.INK, size=15, family=ui.SERIF),
                           hovertemplate="%{y}, %{x}<br>%{z} rostered<extra></extra>"))
fig.update_yaxes(autorange="reversed", showgrid=False)
fig.update_xaxes(showgrid=False, side="top")
fig.update_layout(margin=dict(t=30, l=6, r=6, b=6))
with ui.plate("The re-planned roster for this scenario", "Change from the roster built on the normal timetable in brackets"):
    ui.show(fig, 230)
    moved = int(np.abs(dlt).sum())
    ui.takeaway("No change: the normal-timetable roster is already the answer here." if moved == 0 else
                f"Re-planning moves {moved} staff shifts a week. Night crews change by "
                f"{int(dlt[2].sum()):+d} in total and morning crews by {int(dlt[0].sum()):+d}.")

# ---------------------------------------------------------------- model drift
ui.section("The risk model drifts too", "The model trained on normal months, scored on the disrupted arrivals under the "
                                        "legacy roster it learned from.")
sub = drift.loc[[X.key(s, vol) for s in d["rescheduled_shares"]]].reset_index()
sub["share"] = d["rescheduled_shares"]
fig = go.Figure()
fig.add_trace(go.Scatter(x=sub["share"], y=sub["late_rate"], mode="lines+markers", name="Actual late rate",
                         line=dict(color=ui.LOSS, width=2.5), marker=dict(size=8),
                         hovertemplate="%{x:.0%} moved<br>actual %{y:.1%}<extra></extra>"))
fig.add_trace(go.Scatter(x=sub["share"], y=sub["mean_pred"], mode="lines+markers", name="Model's predicted late rate",
                         line=dict(color=ui.GOLD, width=2.5, dash="dash"), marker=dict(size=8),
                         hovertemplate="%{x:.0%} moved<br>predicted %{y:.1%}<extra></extra>"))
fig.add_vline(x=share, line=dict(color=ui.RULE_STRONG, width=1, dash="dot"))
fig.update_xaxes(tickformat=".0%", title_text="Share of flights moved into waves", tickvals=d["rescheduled_shares"])
fig.update_yaxes(tickformat=".0%", title_text="Late rate", rangemode="tozero")
fig.update_layout(margin=dict(t=36))
c1, c2 = st.columns([0.55, 0.45])
with c1:
    with ui.plate("Predicted against actual late rate", f"Volume change {vol:+.0%}" if vol else "Volume unchanged"):
        ui.show(fig, 320)
        r = drift.loc[key]
        gap = r["mean_pred"] - r["late_rate"]
        ui.takeaway(f"Here the model predicts {ui.pct(r['mean_pred'])} late against an actual {ui.pct(r['late_rate'])}: it "
                    f"{'over' if gap > 0 else 'under'}states lateness by {abs(100 * gap):.1f} points. Its AUC is "
                    f"{r['auc']:.3f}, against {drift.loc[X.key(0.0, 0.0), 'auc']:.3f} on the normal timetable.")
dc = ui.table("drift_calibration")
fig = go.Figure()
fig.add_trace(go.Scatter(x=[0, 1], y=[0, 1], mode="lines", line=dict(color=ui.RULE_STRONG, width=1, dash="dot"),
                         hoverinfo="skip", showlegend=False))
for k, name, color in ((X.key(0.0, 0.0), "Normal timetable", ui.NEU), (key, "This scenario", ui.GOLD)):
    c = dc[dc["scenario"] == k]
    fig.add_trace(go.Scatter(x=c["mean_pred"], y=c["observed"], mode="lines+markers", name=name, line=dict(color=color, width=2),
                             hovertemplate="predicted %{x:.1%}<br>observed %{y:.1%}<extra>" + name + "</extra>"))
mx = float(max(dc[dc["scenario"].isin([key, X.key(0.0, 0.0)])][["mean_pred", "observed"]].max())) * 1.05
fig.update_xaxes(range=[0, mx], tickformat=".0%", title_text="Predicted")
fig.update_yaxes(range=[0, mx], tickformat=".0%", title_text="Observed")
fig.update_layout(margin=dict(t=36))
with c2:
    with ui.plate("Calibration, tenths of predicted risk", "Points above the dotted line: more late than predicted"):
        ui.show(fig, 320)
        r0 = drift.loc[X.key(0.0, 0.0)]
        auc_drop = r0["auc"] - r["auc"]
        gap_pts = 100 * abs(r["mean_pred"] - r["late_rate"])
        if not share:
            msg = "This is the normal timetable. Move the first slider to see how the curve moves."
        elif auc_drop < 0.02 and gap_pts >= 1:
            msg = (f"The ranking holds (AUC down {auc_drop:.3f}) while the probabilities drift by {gap_pts:.1f} points: the "
                   f"riskiest AWBs are still the riskiest, but the rates need re-calibrating before anyone plans with them.")
        elif auc_drop >= 0.02:
            msg = f"Both slip: the AUC falls by {auc_drop:.3f} and the probabilities are {gap_pts:.1f} points off."
        else:
            msg = f"The model holds here: AUC within {auc_drop:.3f} and probabilities within {gap_pts:.1f} points."
        ui.takeaway(msg)

ui.section("What was expected, and what came out",
           "The expectation going in, tested against the scenario selected above. Nothing in the generator was tuned to "
           "make it come true.")
if share == 0:
    st.markdown('<p class="small">Move the first slider above 0% to test the expectation against a broken schedule.</p>',
                unsafe_allow_html=True)
else:
    on = cur["on_time"]
    drop = base["on_time"] - on
    checks = [
        ("The legacy roster does worst", on.idxmin() == "legacy",
         f"lowest here is {SHORT[on.idxmin()].lower()} at {ui.pct(on.min())}"),
        ("The normal-timetable roster beats legacy in normal times", base.loc["static", "on_time"] > base.loc["legacy", "on_time"],
         f"{ui.pct(base.loc['static', 'on_time'])} against {ui.pct(base.loc['legacy', 'on_time'])}"),
        ("It is fragile in waves: it loses more than the re-planned roster", drop["static"] > drop["replanned"],
         f"down {100 * drop['static']:.1f} points against {100 * drop['replanned']:.1f}"),
        ("Re-planning does best", on.idxmax() == "replanned",
         f"best here is {SHORT[on.idxmax()].lower()} at {ui.pct(on.max())}"),
        ("The call-in pool lands close to re-planning (within a point)", abs(on["flex"] - on["replanned"]) <= 0.01,
         f"{ui.pct(on['flex'])} against {ui.pct(on['replanned'])}"),
    ]
    result = []
    for t, ok, why in checks:
        if not ok and t.startswith("The call-in pool") and on["flex"] > on["replanned"]:
            result.append("Did better than expected")
        else:
            result.append("Held" if ok else "Did not hold")
    rows = [[t, r, why] for (t, _, why), r in zip(checks, result)]
    tones = {(i, 1): ("loss" if r == "Did not hold" else "gain") for i, r in enumerate(result)}
    with ui.plate("Expectation against result", f"{share:.0%} of flights moved, volume {vol:+.0%}" if vol else f"{share:.0%} of flights moved"):
        ui.ledger(pd.DataFrame(rows, columns=["Expectation", "Result", "Numbers"]), tones=tones, left=[1, 2])
ui.prose(ui.esc(h["sentences"]["drift"]))
ui.footer()
