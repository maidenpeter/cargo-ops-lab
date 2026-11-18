import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lab import model
from lab import ui

h = ui.headline()
ui.page("risk", lede="Score every AWB the moment its aircraft blocks on, using only what is known then, and supervisors "
                     "can expedite the few most likely to miss the promise.")

m = ui.table("model_metrics")
meta = ui.table("model_meta").set_index("key")["value"]
pred = ui.table("model_predictions")
chosen = meta["chosen"]
col = {"Logistic regression": "p_lr", "Gradient boosting": "p_hgb"}

# ---------------------------------------------------------------- inputs
ui.section("What the model may use", "Only what the terminal knows when the aircraft arrives. A test fails the build if "
                                     "anything from later enters the feature list.")
allowed = [ui.esc(model.LABELS[f]) for f in model.FEATURES]
forbidden = ["RCF, NFD or DLV time", "Present headcount (known only after the shift starts)", "Actual breakdown start",
             "Checked-in weight", "Customs hold", "Handler or customer time"]
c1, c2 = st.columns(2)
with c1:
    with ui.plate("Known at arrival", "Used as features"):
        st.markdown('<p class="small" style="font-size:.98rem;color:var(--ink)">' + " &middot; ".join(allowed) + "</p>",
                    unsafe_allow_html=True)
        ui.note("Backlog at arrival counts AWBs already landed and not yet received from the flight, which the terminal "
                "can see at that moment. AWBs due in the next two hours come from the schedule.")
with c2:
    with ui.plate("Known only later", "Never used"):
        st.markdown('<p class="small" style="font-size:.98rem;color:var(--ink)">' + " &middot; ".join(forbidden) + "</p>",
                    unsafe_allow_html=True)
        ui.note("Rostered headcount is allowed because the roster is published in advance. Present headcount is not: "
                "absences are only known when the shift starts.")

# ---------------------------------------------------------------- comparison
ui.section("Two models, scored on months they never saw",
           f"Trained on arrivals from {pd.Timestamp(meta['train_from']):%B %Y} to {pd.Timestamp(meta['train_to']):%B %Y}, "
           f"compared on {pd.Timestamp(meta['valid_from']):%B} to {pd.Timestamp(meta['valid_to']):%B %Y}, and tested on "
           f"{pd.Timestamp(meta['test_from']):%B} to {pd.Timestamp(meta['test_to']):%B %Y}. No random split.")
rows = []
for r in m.sort_values(["split", "model"], ascending=[False, True]).itertuples():
    rows.append([r.model, "Validation" if r.split == "valid" else "Test", ui.num(r.n), ui.pct(r.late_rate), ui.pct(r.mean_pred),
                 f"{r.auc:.3f}", f"{r.brier:.4f}", ui.pct(r.catch_top)])
test_rows = [i for i, r in enumerate(m.sort_values(["split", "model"], ascending=[False, True]).itertuples())
             if r.split == "test" and r.model == chosen]
with ui.plate("Model comparison", "AUC ranks risk (1 is perfect, 0.5 is a coin); Brier is the squared error of the "
                                  "probability (lower is better)"):
    ui.ledger(pd.DataFrame(rows, columns=["Model", "Months", "AWBs", "Late rate", "Mean predicted", "AUC", "Brier",
                                          f"Late caught in top {ui.pct(h['expedite_share'], 0)}"]), em_rows=test_rows)
    mt = m[(m["model"] == chosen) & (m["split"] == "test")].iloc[0]
    lr = m[(m["model"] == "Logistic regression") & (m["split"] == "test")].iloc[0]
    ui.takeaway(f"{chosen} was picked on the validation months. On the test months it ranks risk with an AUC of "
                f"<b>{mt['auc']:.3f}</b> against {lr['auc']:.3f} for the logistic baseline, and its Brier score is "
                f"{mt['brier']:.4f}.")
    ui.note("Scores this high come from a synthetic floor, which is less noisy than a real one: here the queue an AWB "
            "lands into decides most outcomes. Expect a lower AUC on real milestone data.")

cal = ui.table("model_calibration")
fig = go.Figure()
fig.add_trace(go.Scatter(x=[0, 1], y=[0, 1], mode="lines", line=dict(color=ui.RULE_STRONG, width=1, dash="dot"),
                         hoverinfo="skip", showlegend=False))
for name, color in (("Logistic regression", ui.NEU), ("Gradient boosting", ui.GOLD)):
    c = cal[cal["model"] == name]
    fig.add_trace(go.Scatter(x=c["mean_pred"], y=c["observed"], mode="lines+markers", name=name,
                             line=dict(color=color, width=2), marker=dict(size=7, color=color),
                             hovertemplate="predicted %{x:.1%}<br>observed %{y:.1%}<extra>" + name + "</extra>"))
top = float(max(cal["mean_pred"].max(), cal["observed"].max())) * 1.05
fig.update_xaxes(range=[0, top], tickformat=".0%", title_text="Mean predicted late rate (decile of risk)")
fig.update_yaxes(range=[0, top], tickformat=".0%", title_text="Observed late rate")
fig.update_layout(margin=dict(t=36))
with ui.plate("Calibration on the test months", "Each point is a tenth of AWBs ranked by predicted risk. On the dotted "
                                                 "line, predicted equals observed"):
    ui.show(fig, 360)
    c = cal[cal["model"] == chosen].sort_values("bin")
    hi = c.iloc[-1]
    ui.takeaway(f"In the riskiest tenth, {chosen.lower()} predicts {ui.pct(hi['mean_pred'])} late and {ui.pct(hi['observed'])} "
                f"turn out late. In the safest half, predicted and observed rates both stay under "
                f"{ui.pct(max(c.iloc[:5]['mean_pred'].max(), c.iloc[:5]['observed'].max()))}.")

# ---------------------------------------------------------------- expedite
ui.section("Expedite the riskiest", "Pick the share of arriving AWBs supervisors can push to the front. The numbers "
                                    "below come from the stored test-month predictions.")
share = st.slider("Share of AWBs expedited at arrival", 1, 50, int(round(100 * h["expedite_share"])), format="%d%%") / 100
y = pred["late"].to_numpy()
days = (pd.to_datetime(pred["arr_ts"]).max() - pd.to_datetime(pred["arr_ts"]).min()).days + 1
res = {}
for name, cname in col.items():
    p = pred[cname].to_numpy()
    res[name] = model.capture(y, p, share)
catch, rate = res[chosen]
n_exp = int(round(share * len(y)))
ui.proof([
    {"k": "Expedited per day", "v": ui.num(n_exp / days), "d": f"{ui.pct(share, 0)} of {ui.num(len(y) / days)} AWBs a day"},
    {"k": "Late AWBs reached", "v": ui.pct(catch, 0), "d": "share of all late AWBs that were in the expedited group",
     "tone": "gain"},
    {"k": "Late rate, expedited group", "v": ui.pct(rate), "d": f"against {ui.pct(y.mean())} across all AWBs"},
    {"k": "Random pick would reach", "v": ui.pct(share, 0), "d": "of late AWBs, for comparison"},
])
cc = ui.table("model_capture")
fig = go.Figure()
fig.add_trace(go.Scatter(x=[0, 0.5], y=[0, 0.5], mode="lines", line=dict(color=ui.RULE_STRONG, width=1, dash="dot"),
                         name="Random pick", hoverinfo="skip"))
for name, color in (("Logistic regression", ui.NEU), ("Gradient boosting", ui.GOLD)):
    c = cc[cc["model"] == name]
    fig.add_trace(go.Scatter(x=c["share"], y=c["catch"], mode="lines", name=name, line=dict(color=color, width=2),
                             hovertemplate="expedite %{x:.0%}<br>reach %{y:.1%} of late<extra>" + name + "</extra>"))
fig.add_trace(go.Scatter(x=[share], y=[catch], mode="markers", marker=dict(size=11, color=ui.GOLD, line=dict(color=ui.INK, width=1.5)),
                         showlegend=False, hoverinfo="skip"))
fig.update_xaxes(tickformat=".0%", title_text="Share of AWBs expedited, riskiest first", range=[0, 0.5])
fig.update_yaxes(tickformat=".0%", title_text="Share of late AWBs reached", range=[0, 1])
fig.update_layout(margin=dict(t=36))
with ui.plate("How much lateness an expedite list reaches", "Test months; the marker follows the slider"):
    ui.show(fig, 340)
    ui.takeaway(f"Expediting the riskiest {ui.pct(share, 0)} of AWBs at arrival reaches <b>{ui.pct(catch, 0)}</b> of the "
                f"shipments that end up late, against {ui.pct(share, 0)} for a random pick. Whether expediting saves them "
                f"is a separate question: this measures who to look at, not what looking does.")

# ---------------------------------------------------------------- drivers
ui.section("What drives the score", "Permutation importance on the test months: how much the AUC drops when one input "
                                    "is shuffled.")
imp = ui.table("model_importance").head(8).iloc[::-1]
fig = go.Figure(go.Bar(x=imp["mean"], y=imp["label"], orientation="h", marker=ui.hatched(ui.GOLD),
                       error_x=dict(type="data", array=imp["std"], color=ui.MUTED, thickness=1, width=3),
                       hovertemplate="%{y}<br>AUC drop %{x:.3f}<extra></extra>"))
fig.update_xaxes(title_text="Drop in AUC when shuffled")
c1, c2 = st.columns([0.55, 0.45])
with c1:
    with ui.plate("Top eight inputs", f"{chosen}, test months"):
        ui.show(fig, 320)
        top = ui.table("model_importance").iloc[0]
        sec = ui.table("model_importance").iloc[1]
        ui.takeaway(f"{top['label']} matters most (AUC drop {top['mean']:.3f}): the queue an AWB lands in says more than "
                    f"anything about the AWB itself. {sec['label']} comes second ({sec['mean']:.3f}), because the promise "
                    f"length differs by product.")
bins = pd.qcut(pred["backlog_at_arr"].rank(method="first"), 10, labels=False)
g = pred.groupby(bins).agg(backlog=("backlog_at_arr", "median"), observed=("late", "mean"),
                           predicted=(col[chosen], "mean")).reset_index(drop=True)
xs = [f"{i + 1}" for i in range(len(g))]
fig = go.Figure()
fig.add_trace(go.Bar(x=xs, y=g["observed"], name="Observed late rate", marker=ui.hatched(ui.LOSS),
                     customdata=g["backlog"], hovertemplate="tenth %{x}, backlog about %{customdata:.0f}<br>observed %{y:.1%}<extra></extra>"))
fig.add_trace(go.Scatter(x=xs, y=g["predicted"], name="Mean predicted", mode="lines+markers",
                         line=dict(color=ui.GOLD, width=2), marker=dict(size=6),
                         hovertemplate="tenth %{x}<br>predicted %{y:.1%}<extra></extra>"))
fig.update_xaxes(title_text="Backlog at arrival, median AWBs in each tenth", tickvals=xs,
                 ticktext=[f"{b:.0f}" for b in g["backlog"]])
fig.update_yaxes(tickformat=".0%")
fig.update_layout(margin=dict(t=36), bargap=0.25)
with c2:
    with ui.plate("Late rate by backlog at arrival", "Test months, tenths of the backlog"):
        ui.show(fig, 320)
        ui.takeaway(f"With the lightest backlog {ui.pct(g['observed'].iloc[0])} of AWBs end up late; with the heaviest, "
                    f"{ui.pct(g['observed'].iloc[-1])}.")
ui.footer()
