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
fx = cfg["flex"]
dis = ui.table("disruption")
drift = ui.table("drift").set_index("scenario")
prof = ui.table("arrival_profile")
NAME, SHORT = ui.POLICY_NAMES, ui.POLICY_SHORT
COLOR = {"legacy": ui.NEU, "static": ui.GOLD, "replanned": ui.GAIN, "flex": ui.INK2}
BASE = X.key(0.0, 0.0)
test0 = pd.Timestamp(cfg["split"]["valid_end"]) + pd.Timedelta(days=1)
test = f"{test0:%B} to {pd.Timestamp(cfg['window']['cutoff']):%B %Y}"
waves = " and ".join(d["wave_centers"])

ui.page("disruption")
ui.short(
    "What happens when the flight schedule suddenly changes?",
    ui.esc(h["sentences"]["headline"] + " " + h["sentences"]["flex"]),
    "A roster built for normal times can fail quietly when flights bunch together, as they do when airspace closes and "
    "airlines re-route. Testing it in a simulation shows how far service falls, and which fix works, before it happens "
    "for real.",
)

# ---------------------------------------------------------------- controls
ui.section("Try it: break the schedule", f"Move flights into rush hours, take freight away, and pick how the terminal "
                                         f"responds. Every number below is a stored simulation result for {test}.")
c1, c2, c3 = st.columns([0.3, 0.3, 0.4])
share = c1.select_slider("Flights moved into rush hours", options=d["rescheduled_shares"], value=0.0,
                         format_func=lambda v: f"{v:.0%}")
vol = c2.select_slider("Change in freight", options=sorted(d["volume_changes"], reverse=True), value=0.0,
                       format_func=lambda v: f"{v:+.0%}" if v else "0%")
pol = c3.segmented_control("How the terminal responds", list(NAME), format_func=SHORT.get, default="static",
                           selection_mode="single") or "static"
legend = {
    "legacy": "The current roster, unchanged.",
    "static": "The roster recommended for the normal timetable, kept as it is.",
    "replanned": f"The roster rebuilt for the new schedule, given {d['notice_hours']} hours' notice.",
    "flex": f"The recommended roster, plus {fx['pool_size']} on-call staff called in whenever {fx['backlog_trigger']} or "
            f"more shipments are waiting.",
}
st.markdown('<div class="gloss four">' + "".join(
    f'<div><b><span class="sw" style="background:{COLOR[p]}"></span>{ui.esc(SHORT[p])}</b><p>{ui.esc(t)}</p></div>'
    for p, t in legend.items()) + "</div>", unsafe_allow_html=True)
key = X.key(share, vol)
cur = dis[dis["scenario"] == key].set_index("policy")
base = dis[dis["scenario"] == BASE].set_index("policy")


def scenario_sentence(share: float, vol: float, cur: pd.DataFrame) -> str:
    if share == 0 and vol == 0:
        return (f"This is the normal timetable: the recommended roster gets {ui.pct(cur.loc['static', 'on_time'])} of "
                f"shipments ready on time, and re-planning returns the same roster. Move the first slider to break the "
                f"schedule.")
    v = f" and there is {-vol:.0%} less freight" if vol else ""
    if share == 0:
        start = (f"On the normal timetable with {-vol:.0%} less freight, the recommended roster gets "
                 f"{ui.pct(cur.loc['static', 'on_time'])} ready on time.")
    else:
        start = (f"When {share:.0%} of flights bunch into rush hours{v}, the recommended roster gets "
                 f"{ui.pct(cur.loc['static', 'on_time'])} ready on time.")
    extra = cur.loc["replanned", "staff_hours_per_week"] - cur.loc["static", "staff_hours_per_week"]
    cost = ("with the same staff hours" if abs(extra) < 0.5 else
            f"for {extra:,.0f} more staff hours a week" if extra > 0 else f"with {-extra:,.0f} fewer staff hours a week")
    rp = cur.loc["replanned", "on_time"]
    end = (f"Re-planning for the new schedule gets to {ui.pct(rp)} {cost}." if rp > cur.loc["static", "on_time"] else
           f"Re-planning does not beat it: {ui.pct(rp)} {cost}.")
    return f"{start} {end}"


st.markdown(f'<p class="lede" style="color:var(--ink);max-width:80ch;margin-top:.6rem">'
            f'{ui.esc(scenario_sentence(share, vol, cur))}</p>', unsafe_allow_html=True)
p = cur.loc[pol]
hours = p["staff_hours_per_week"] + p["flex_hours_per_week"]
dl = p["on_time"] - base.loc[pol, "on_time"]
ui.proof([
    {"k": f"{SHORT[pol]}: ready on time", "v": ui.pct(p["on_time"]), "tone": "gain" if dl >= 0 else "loss",
     "d": f"{ui.pts(dl)} against the normal timetable" if key != BASE else "on the normal timetable"},
    {"k": "Late shipments per week", "v": ui.num(p["late_per_week"]), "d": f"of {ui.num(p['awbs_per_week'])} landing each week"},
    {"k": "Staff hours per week", "v": ui.num(hours),
     "d": f"including {ui.num(p['flex_hours_per_week'])} on-call hours" if pol == "flex" else "rostered hours"},
    {"k": "Cost per week", "v": ui.usd(p["total_cost_per_week"]), "d": "wages plus late penalties, illustrative dollars"},
])

rows, em = [], []
for i, k in enumerate(["legacy", "static", "replanned", "flex"]):
    r = cur.loc[k]
    rows.append([NAME[k], ui.pct(r["on_time"]), ui.num(r["late_per_week"]),
                 ui.num(r["staff_hours_per_week"] + r["flex_hours_per_week"]),
                 ui.num(r["callins_per_week"], 1) if k == "flex" else "", ui.usd(r["total_cost_per_week"])])
    if k == pol:
        em.append(i)
with ui.plate("Four responses to the same flights", f"Average of {cfg['roster_opt']['seeds']} runs over {test}"):
    ui.ledger(pd.DataFrame(rows, columns=["Response", "On time", "Late per week", "Staff hours per week",
                                          "Call-ins per week", "Cost per week"]), em_rows=em)
    order = cur["on_time"].sort_values(ascending=False)
    ui.takeaway("Ranked by on time here: " + ", then ".join(f"{SHORT[k].lower()} {ui.pct(v)}" for k, v in order.items()) + ".")
    rp_, st_ = cur.loc["replanned"], cur.loc["static"]
    if rp_["staff_hours_per_week"] < st_["staff_hours_per_week"] - 0.5 and rp_["on_time"] < st_["on_time"]:
        ui.note(f"Re-planning weighs wages against late penalties, as the recommended roster does. With less freight it "
                f"gives back {st_['staff_hours_per_week'] - rp_['staff_hours_per_week']:,.0f} staff hours a week and "
                f"accepts lateness the illustrative penalties do not cover: its total cost here is "
                f"{ui.usd(rp_['total_cost_per_week'])} a week against {ui.usd(st_['total_cost_per_week'])}.")

# ---------------------------------------------------------------- arrivals
pb = prof[prof["scenario"] == BASE].set_index("hour")["awbs_per_day"]
ps = prof[prof["scenario"] == key].set_index("hour")["awbs_per_day"]
fig = go.Figure()
fig.add_trace(go.Bar(x=ps.index, y=ps.values, name="This scenario", marker=ui.hatched(ui.GOLD),
                     hovertemplate="%{x}:00<br>%{y:.0f} shipments a day<extra>scenario</extra>"))
fig.add_trace(go.Scatter(x=pb.index, y=pb.values, name="Normal timetable", mode="lines", line=dict(color=ui.INK2, width=2, shape="hvh"),
                         hovertemplate="%{x}:00<br>%{y:.0f} shipments a day<extra>normal</extra>"))
fig.update_xaxes(title_text="Hour the plane landed (hub local time)", dtick=2)
fig.update_yaxes(title_text="Shipments a day")
fig.update_layout(margin=dict(t=36), bargap=0.12)
with ui.plate("When the freight lands", f"Average shipments landing in each hour. Moved flights land within "
                                        f"{d['wave_half_width_min']} minutes of {waves}"):
    ui.show(fig, 300)
    hr = int((ps - pb).idxmax())
    ui.takeaway(f"At {hr:02d}:00 this scenario lands {ps[hr]:.0f} shipments a day, against {pb[hr]:.0f} on the normal "
                f"timetable." if share else "This is the normal timetable. Move the first slider to bunch flights into "
                                            "rush hours.")

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
fig.update_xaxes(tickformat=".0%", title_text="Share of flights moved into rush hours", tickvals=d["rescheduled_shares"])
fig.update_yaxes(tickformat=".0%", title_text="Ready on time")
fig.update_layout(margin=dict(t=36))
top_share = max(d["rescheduled_shares"])
with ui.plate("How each response holds up as more flights bunch", f"Freight {vol:+.0%}" if vol else "Freight unchanged"):
    ui.show(fig, 340)
    at = lambda s_, k_: sub[(sub["share"] == s_) & (sub["policy"] == k_)]["on_time"].iloc[0]  # noqa: E731
    ui.takeaway(f"The recommended roster falls from {ui.pct(at(0, 'static'))} to {ui.pct(at(top_share, 'static'))} as the "
                f"share of flights moved goes from 0% to {top_share:.0%}. Re-planned, it holds "
                f"{ui.pct(at(top_share, 'replanned'))}; with on-call staff, {ui.pct(at(top_share, 'flex'))}.")

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
                           hovertemplate="%{y}, %{x}<br>%{z} people<extra></extra>"))
fig.update_yaxes(autorange="reversed", showgrid=False)
fig.update_xaxes(showgrid=False, side="top")
fig.update_layout(margin=dict(t=30, l=6, r=6, b=6))
with ui.plate("The re-planned roster for this scenario", "People on each shift. Change from the recommended roster in brackets"):
    ui.show(fig, 230)
    moved = int(np.abs(dlt).sum())
    sh = {i: int(dlt[i].sum()) for i in range(3)}
    ui.takeaway("No change: the recommended roster is already the answer here." if moved == 0 else
                f"Re-planning changes the roster by {moved} people across the week's 21 shifts: the nights by "
                f"{sh[2]:+d} in total, the mornings by {sh[0]:+d} and the afternoons by {sh[1]:+d}.")

# ---------------------------------------------------------------- model drift
ui.section("The early-warning model drifts too", "The model learned on normal months. Here it scores the shipments on "
                                                 "the broken schedule, under the current roster it learned from.")
dsub = drift.loc[[X.key(s, vol) for s in d["rescheduled_shares"]]].reset_index()
dsub["share"] = d["rescheduled_shares"]
fig = go.Figure()
fig.add_trace(go.Scatter(x=dsub["share"], y=dsub["late_rate"], mode="lines+markers", name="Actually late",
                         line=dict(color=ui.LOSS, width=2.5), marker=dict(size=8),
                         hovertemplate="%{x:.0%} moved<br>actually late %{y:.1%}<extra></extra>"))
fig.add_trace(go.Scatter(x=dsub["share"], y=dsub["mean_pred"], mode="lines+markers", name="Model's prediction",
                         line=dict(color=ui.GOLD, width=2.5, dash="dash"), marker=dict(size=8),
                         hovertemplate="%{x:.0%} moved<br>predicted %{y:.1%}<extra></extra>"))
fig.add_vline(x=share, line=dict(color=ui.RULE_STRONG, width=1, dash="dot"))
fig.update_xaxes(tickformat=".0%", title_text="Share of flights moved into rush hours", tickvals=d["rescheduled_shares"])
fig.update_yaxes(tickformat=".0%", title_text="Share of shipments late", rangemode="tozero")
fig.update_layout(margin=dict(t=36))
r = drift.loc[key]
r0 = drift.loc[BASE]
with ui.plate("Predicted against actual share late", f"Freight {vol:+.0%}" if vol else "Freight unchanged"):
    ui.show(fig, 320)
    gap = r["mean_pred"] - r["late_rate"]
    ui.takeaway(f"Here the model expects {ui.pct(r['mean_pred'])} of shipments to be late; in fact {ui.pct(r['late_rate'])} "
                f"are, so it {'over' if gap > 0 else 'under'}states lateness by {abs(100 * gap):.1f} percentage points. Its "
                f"ranking accuracy is {r['auc']:.3f}, against {r0['auc']:.3f} on the normal timetable.")

ui.section("What was expected, and what happened",
           "The expectations going in, tested against the scenario picked above. Nothing in the simulation was tuned to "
           "make them come true.")
if share == 0:
    st.markdown('<p class="small">Move the first slider above 0% to test the expectations against a broken schedule.</p>',
                unsafe_allow_html=True)
else:
    on = cur["on_time"]
    drop = base["on_time"] - on
    FLEX = "On-call staff land close to re-planning (within a point)"
    checks = [
        ("The current roster does worst", on.idxmin() == "legacy",
         f"lowest here is {SHORT[on.idxmin()].lower()} at {ui.pct(on.min())}"),
        ("The recommended roster beats the current one in normal times", base.loc["static", "on_time"] > base.loc["legacy", "on_time"],
         f"{ui.pct(base.loc['static', 'on_time'])} against {ui.pct(base.loc['legacy', 'on_time'])}"),
        ("It is fragile in rush hours: it loses more than the re-planned roster", drop["static"] > drop["replanned"],
         f"down {100 * drop['static']:.1f} points against {100 * drop['replanned']:.1f}"),
        ("Re-planning does best", on.idxmax() == "replanned",
         f"best here is {SHORT[on.idxmax()].lower()} at {ui.pct(on.max())}"),
        (FLEX, abs(on["flex"] - on["replanned"]) <= 0.01, f"{ui.pct(on['flex'])} against {ui.pct(on['replanned'])}"),
    ]
    result = []
    for t, ok, why in checks:
        if not ok and t == FLEX and on["flex"] > on["replanned"]:
            result.append("Did better than expected")
        else:
            result.append("Held" if ok else "Did not hold")
    rows = [[t, res, why] for (t, _, why), res in zip(checks, result)]
    tones = {(i, 1): ("loss" if res == "Did not hold" else "gain") for i, res in enumerate(result)}
    with ui.plate("Expectation against result", f"{share:.0%} of flights moved, freight {vol:+.0%}" if vol else f"{share:.0%} of flights moved"):
        ui.ledger(pd.DataFrame(rows, columns=["Expectation", "Result", "Numbers"]), tones=tones, left=[1, 2])
ui.prose(ui.esc(h["sentences"]["drift"]))

# ---------------------------------------------------------------- under the hood
ui.hood(f"How the scenarios are built, and the drifted model's calibration. In the technical terms, legacy is the current "
        f"roster, static the roster optimized on the normal timetable, and flex the call-in pool.")
ui.prose(
    f"Disruption is applied to the test months, {test}, after a normal warm-up. A share of flights is moved to the "
    f"nearest wave center ({waves}, landing within {d['wave_half_width_min']} minutes of it) and AWBs are thinned, both "
    f"with fixed random draws, so scenarios are nested and 0% moved with 0% volume change reproduces the base case "
    f"exactly (a test checks it). Re-planning reruns the simulation grid and the integer program on the disrupted "
    f"arrivals, assuming the new schedule is known {d['notice_hours']} hours ahead. The call-in pool watches the "
    f"breakdown queue every 15 minutes; at {fx['backlog_trigger']} or more AWBs waiting it calls all {fx['pool_size']} "
    f"staff, who arrive {fx['lead_time_min']} minutes later and work a {fx['block_hours']}-hour block at "
    f"{fx['cost_multiplier']:g} times the hourly rate.",
)
dc = ui.table("drift_calibration")
fig = go.Figure()
fig.add_trace(go.Scatter(x=[0, 1], y=[0, 1], mode="lines", line=dict(color=ui.RULE_STRONG, width=1, dash="dot"),
                         hoverinfo="skip", showlegend=False))
for kk, name, color in ((BASE, "Normal timetable", ui.NEU), (key, "This scenario", ui.GOLD)):
    c = dc[dc["scenario"] == kk]
    fig.add_trace(go.Scatter(x=c["mean_pred"], y=c["observed"], mode="lines+markers", name=name, line=dict(color=color, width=2),
                             hovertemplate="predicted %{x:.1%}<br>observed %{y:.1%}<extra>" + name + "</extra>"))
mx = float(max(dc[dc["scenario"].isin([key, BASE])][["mean_pred", "observed"]].max())) * 1.05
fig.update_xaxes(range=[0, mx], tickformat=".0%", title_text="Predicted late rate")
fig.update_yaxes(range=[0, mx], tickformat=".0%", title_text="Observed late rate")
fig.update_layout(margin=dict(t=36))
with ui.plate("Calibration, tenths of predicted risk", "Points above the dotted line: more late than predicted"):
    ui.show(fig, 340)
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
ui.footer()
