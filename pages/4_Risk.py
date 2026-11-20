import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lab import model
from lab import ui

h = ui.headline()
m = ui.table("model_metrics")
meta = ui.table("model_meta").set_index("key")["value"]
pred = ui.table("model_predictions")
imp_all = ui.table("model_importance")
chosen = meta["chosen"]
col = {"Logistic regression": "p_lr", "Gradient boosting": "p_hgb"}
NAME = {n: f"{'Chosen' if n == chosen else 'Runner-up'} model ({n.lower()})" for n in col}
COLOR = {n: ui.GOLD if n == chosen else ui.NEU for n in col}
F = ui.FEATURE_LABELS
top, sec = imp_all.iloc[0], imp_all.iloc[1]
sign = "how long the queue is when the plane lands" if top["feature"] == "backlog_at_arr" else F[top["feature"]].lower()
test = f"{pd.Timestamp(meta['test_from']):%B} to {pd.Timestamp(meta['test_to']):%B %Y}"

ui.page("risk")
ui.short(
    "When a plane lands, can we tell which of its shipments will be late?",
    f"Largely, yes. An early-warning model scores every shipment the moment its plane lands, using only what is known "
    f"then. Flagging the riskiest <b>{ui.pct(h['expedite_share'], 0)}</b> would catch <b>{ui.pct(h['model_catch'], 0)}</b> "
    f"of the shipments that end up late; a random pick of the same size would catch {ui.pct(h['expedite_share'], 0)}.",
    f"Supervisors can move flagged shipments to the front of the queue before they become late, instead of explaining "
    f"afterwards. The biggest warning sign is a simple one: {sign}.",
)

# ---------------------------------------------------------------- expedite
ui.section("Try it: how many shipments could supervisors fast-track?",
           f"Pick the share of arriving shipments that can be pushed to the front of the queue. The results use the "
           f"model's stored scores for {test}, months it never saw while it was being built.")
share = st.slider("Share of shipments flagged when their plane lands", 1, 50, int(round(100 * h["expedite_share"])),
                  format="%d%%") / 100
y = pred["late"].to_numpy()
days = (pd.to_datetime(pred["arr_ts"]).max() - pd.to_datetime(pred["arr_ts"]).min()).days + 1
res = {name: model.capture(y, pred[c].to_numpy(), share) for name, c in col.items()}
catch, rate = res[chosen]
n_exp = int(round(share * len(y)))
ui.proof([
    {"k": "Flagged per day", "v": ui.num(n_exp / days), "d": f"{ui.pct(share, 0)} of {ui.num(len(y) / days)} shipments a day"},
    {"k": "Late shipments caught", "v": ui.pct(catch, 0), "d": "of all the shipments that end up late", "tone": "gain"},
    {"k": "Late among the flagged", "v": ui.pct(rate), "d": f"against {ui.pct(y.mean())} of all shipments"},
    {"k": "A random pick would catch", "v": ui.pct(share, 0), "d": "of the late shipments, for comparison"},
])
cc = ui.table("model_capture")
fig = go.Figure()
fig.add_trace(go.Scatter(x=[0, 0.5], y=[0, 0.5], mode="lines", line=dict(color=ui.RULE_STRONG, width=1, dash="dot"),
                         name="Random pick", hoverinfo="skip"))
for name in sorted(col, key=lambda n: n == chosen):
    c = cc[cc["model"] == name]
    fig.add_trace(go.Scatter(x=c["share"], y=c["catch"], mode="lines", name=NAME[name], line=dict(color=COLOR[name], width=2),
                             hovertemplate="flag %{x:.0%}<br>catch %{y:.1%} of late<extra>" + NAME[name] + "</extra>"))
fig.add_trace(go.Scatter(x=[share], y=[catch], mode="markers", marker=dict(size=11, color=ui.GOLD, line=dict(color=ui.INK, width=1.5)),
                         showlegend=False, hoverinfo="skip"))
fig.update_xaxes(tickformat=".0%", title_text="Share of shipments flagged, riskiest first", range=[0, 0.5])
fig.update_yaxes(tickformat=".0%", title_text="Share of late shipments caught", range=[0, 1])
fig.update_layout(margin=dict(t=36))
with ui.plate("How many late shipments a watch list catches", f"{test}. The marker follows the slider"):
    ui.show(fig, 340)
    ui.takeaway(f"Flagging the riskiest {ui.pct(share, 0)} of shipments catches <b>{ui.pct(catch, 0)}</b> of those that "
                f"end up late, against {ui.pct(share, 0)} for a random pick. Whether fast-tracking then saves them is a "
                f"separate question: this shows who to look at, not what looking does.")
    ui.note("A real terminal is messier than this simulated one, where the queue a shipment lands into decides most "
            "outcomes. Expect a real model to catch fewer.")

# ---------------------------------------------------------------- inputs
ui.section("What the model is allowed to know", "Only what the terminal knows when the plane lands. A test stops the build "
                                                "if anything from later sneaks in.")
allowed = [ui.esc(F[f]) for f in model.FEATURES]
forbidden = ["When it was actually checked in, ready or collected", "How many staff actually turned up",
             "When unpacking actually started", "The weight measured at check-in", "Customs holds",
             "How long it ended up taking"]
c1, c2 = st.columns(2)
with c1:
    with ui.plate("Known when the plane lands", "Used"):
        st.markdown('<p class="small" style="font-size:1rem;color:var(--ink)">' + " &middot; ".join(allowed) + "</p>",
                    unsafe_allow_html=True)
        ui.note("The queue counts shipments already landed and not yet checked in, which the terminal can see at that "
                "moment. Shipments due in the next two hours come from the timetable.")
with c2:
    with ui.plate("Known only later", "Never used"):
        st.markdown('<p class="small" style="font-size:1rem;color:var(--ink)">' + " &middot; ".join(forbidden) + "</p>",
                    unsafe_allow_html=True)
        ui.note("The staff scheduled on a shift can be used, because the roster is published in advance. How many "
                "actually turn up cannot: absences are known only once the shift starts.")

# ---------------------------------------------------------------- drivers
ui.section("What makes a shipment risky", "How much the model's ranking accuracy drops when one input is scrambled. The "
                                          "bigger the drop, the more the model leans on it.")
imp = imp_all.head(8).iloc[::-1]
fig = go.Figure(go.Bar(x=imp["mean"], y=imp["feature"].map(F), orientation="h", marker=ui.hatched(ui.GOLD),
                       error_x=dict(type="data", array=imp["std"], color=ui.MUTED, thickness=1, width=3),
                       hovertemplate="%{y}<br>accuracy drop %{x:.3f}<extra></extra>"))
fig.update_xaxes(title_text="Drop in ranking accuracy (AUC) when scrambled")
c1, c2 = st.columns([0.55, 0.45])
with c1:
    with ui.plate("The eight inputs it leans on most", f"{NAME[chosen]}, {test}"):
        ui.show(fig, 320)
        why_top = (": the queue a shipment lands into says more than anything about the shipment itself"
                   if top["feature"] == "backlog_at_arr" else "")
        why_sec = ", because each type of cargo has a different promise" if sec["feature"] == "product" else ""
        ui.takeaway(f"{F[top['feature']]} matters most{why_top}. {F[sec['feature']]} comes second{why_sec}.")
bins = pd.qcut(pred["backlog_at_arr"].rank(method="first"), 10, labels=False)
g = pred.groupby(bins).agg(backlog=("backlog_at_arr", "median"), observed=("late", "mean"),
                           predicted=(col[chosen], "mean")).reset_index(drop=True)
xs = [f"{i + 1}" for i in range(len(g))]
fig = go.Figure()
fig.add_trace(go.Bar(x=xs, y=g["observed"], name="Actually late", marker=ui.hatched(ui.LOSS),
                     customdata=g["backlog"], hovertemplate="queue about %{customdata:.0f}<br>late %{y:.1%}<extra></extra>"))
fig.add_trace(go.Scatter(x=xs, y=g["predicted"], name="Model's prediction", mode="lines+markers",
                         line=dict(color=ui.GOLD, width=2), marker=dict(size=6),
                         hovertemplate="predicted %{y:.1%}<extra></extra>"))
fig.update_xaxes(title_text="Shipments already waiting when the plane landed", tickvals=xs,
                 ticktext=[f"{b:.0f}" for b in g["backlog"]])
fig.update_yaxes(tickformat=".0%")
fig.update_layout(margin=dict(t=36), bargap=0.25)
with c2:
    with ui.plate("The longer the queue, the more end up late", "Shipments split into ten equal groups by the queue when "
                                                                "their plane landed"):
        ui.show(fig, 320)
        ui.takeaway(f"With the shortest queues, {ui.pct(g['observed'].iloc[0])} of shipments end up late; with the "
                    f"longest, {ui.pct(g['observed'].iloc[-1])}.")

# ---------------------------------------------------------------- under the hood
ui.hood(f"Two models, logistic regression and gradient boosting, trained on arrivals from "
        f"{pd.Timestamp(meta['train_from']):%B %Y} to {pd.Timestamp(meta['train_to']):%B %Y}, compared on "
        f"{pd.Timestamp(meta['valid_from']):%B} to {pd.Timestamp(meta['valid_to']):%B %Y} and tested on {test}. No random "
        f"split. AUC ranks risk (1 is perfect, 0.5 is a coin); Brier is the squared error of the probability (lower is better).")
order = m.sort_values(["split", "model"], ascending=[False, True])
rows = [[r.model, "Validation" if r.split == "valid" else "Test", ui.num(r.n), ui.pct(r.late_rate), ui.pct(r.mean_pred),
         f"{r.auc:.3f}", f"{r.brier:.4f}", ui.pct(r.catch_top)] for r in order.itertuples()]
test_rows = [i for i, r in enumerate(order.itertuples()) if r.split == "test" and r.model == chosen]
with ui.plate("Model comparison", "Picked on the validation months before the test months were opened"):
    ui.ledger(pd.DataFrame(rows, columns=["Model", "Months", "AWBs", "Late rate", "Mean predicted", "AUC", "Brier",
                                          f"Late caught in top {ui.pct(h['expedite_share'], 0)}"]), em_rows=test_rows)
    mt = m[(m["model"] == chosen) & (m["split"] == "test")].iloc[0]
    other = m[(m["model"] != chosen) & (m["split"] == "test")].iloc[0]
    ui.takeaway(f"{chosen} was picked on the validation months. On the test months it ranks risk with an AUC of "
                f"<b>{mt['auc']:.3f}</b> against {other['auc']:.3f} for {other['model'].lower()}, and its Brier score is "
                f"{mt['brier']:.4f}. Scores this high come from a synthetic floor, which is less noisy than a real one.")

cal = ui.table("model_calibration")
fig = go.Figure()
fig.add_trace(go.Scatter(x=[0, 1], y=[0, 1], mode="lines", line=dict(color=ui.RULE_STRONG, width=1, dash="dot"),
                         hoverinfo="skip", showlegend=False))
for name in sorted(col, key=lambda n: n == chosen):
    c = cal[cal["model"] == name]
    fig.add_trace(go.Scatter(x=c["mean_pred"], y=c["observed"], mode="lines+markers", name=name,
                             line=dict(color=COLOR[name], width=2), marker=dict(size=7, color=COLOR[name]),
                             hovertemplate="predicted %{x:.1%}<br>observed %{y:.1%}<extra>" + name + "</extra>"))
hi_ = float(max(cal["mean_pred"].max(), cal["observed"].max())) * 1.05
fig.update_xaxes(range=[0, hi_], tickformat=".0%", title_text="Mean predicted late rate (decile of risk)")
fig.update_yaxes(range=[0, hi_], tickformat=".0%", title_text="Observed late rate")
fig.update_layout(margin=dict(t=36))
with ui.plate("Calibration on the test months", "Each point is a tenth of AWBs ranked by predicted risk. On the dotted "
                                                 "line, predicted equals observed"):
    ui.show(fig, 360)
    c = cal[cal["model"] == chosen].sort_values("bin")
    last = c.iloc[-1]
    ui.takeaway(f"In the riskiest tenth, {chosen.lower()} predicts {ui.pct(last['mean_pred'])} late and "
                f"{ui.pct(last['observed'])} turn out late. In the safest half, predicted and observed rates both stay under "
                f"{ui.pct(max(c.iloc[:5]['mean_pred'].max(), c.iloc[:5]['observed'].max()))}.")
ui.footer()
