import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lab import config as C
from lab import scenarios as X
from lab import shipments as S
from lab import story
from lab import ui

h = ui.headline()
cfg = C.load()
k = ui.table("kpi_summary").set_index("kpi")["value"]
tt = C.timetable()
sla = cfg["sla_hours"]
start, cut = pd.Timestamp(cfg["window"]["start"]), pd.Timestamp(cfg["window"]["cutoff"])
months = (cut.year - start.year) * 12 + cut.month - start.month + 1

ui.page("terminal", lede=ui.TAGLINE)
ui.prose(
    "Picture an airport cargo terminal. Planes land with freight on board. A crew tows the containers in, unpacks "
    "them, checks the paperwork and tells each customer that their goods are ready to collect. Every type of cargo "
    f"comes with a promise of how fast that will happen: {sla['live_animals']} hours for live animals, "
    f"{sla['pharma']} for medicines, {sla['general']} for general freight. Miss it, and the shipment counts as late.",
    f"This lab builds such a terminal on a computer, with {len(tt)} regular flights from {tt['carrier'].nunique()} "
    f"airlines, and plays out {months} months of freight: {ui.num(k['awbs_total'])} shipments weighing "
    f"{ui.num(k['tonnes_total'])} tonnes. Then it asks the five questions a terminal's analyst would be asked. Nothing "
    f"here is real data, and no real company is named.",
)
ui.takeaway("<b>How to read it.</b> Start with the story below. Every page then opens with the short version: the "
            "question, the answer and why it matters. The detail for analysts (the SQL, the scores and the math) comes "
            "after, under the hood. The words used are explained at the foot of this page.")

# ---------------------------------------------------------------- the story
story_id = S.story_pick()
if story_id:
    r = S.record(story_id)
    bk = S.book()
    wd, si = S.shift_of(r["arr"])
    ros = ui.table("rosters")
    dis = ui.table("disruption")
    late_at = lambda key: float(dis[(dis["scenario"] == key) & (dis["policy"] == "static")]["late_per_week"].iloc[0])  # noqa: E731
    ctx = {
        "n_flight": int(((bk["flight"].astype(str) == r["flight"]) & (bk["arr_ts"] == r["arr"])).sum()),
        "flight_late_min": (r["arr"] - r["sched"]).total_seconds() / 60,
        "crew_now": int(C.legacy_roster()[wd][si]),
        "crew_rec": int(ros[(ros["policy"] == "optimized") & (ros["weekday"] == wd) & (ros["shift"] == si)]["headcount"].iloc[0]),
        "shift": ui.SHIFTS[si].lower(), "noun": ui.PRODUCT_NOUNS[r["product"]],
        "priority": r["product"] in cfg["priority_products"], "expedite_share": cfg["model"]["expedite_share"],
        "dis_share": h["dis_share"], "late_base": late_at(X.key(0.0, 0.0)), "late_dis": late_at(X.key(h["dis_share"], 0.0)),
    }
    noun, lm = ctx["noun"], ctx["flight_late_min"]
    hm = lambda ts: f"{ts:%H:%M}"  # noqa: E731
    behind = (f"{lm:.0f} minutes behind schedule" if lm > 5 else f"{-lm:.0f} minutes early" if lm < -5 else "on schedule")
    when = ("Shortly after midnight on " if r["arr"].hour < 3 else "On ") + S.when(r["arr"])
    higher = 100 - round(100 * r.get("rank", 0))
    top = round(100 * ctx["expedite_share"])
    late = r["margin_min"] is not None and r["margin_min"] < 0
    flagged = bool(r.get("flagged"))
    backlog, coming = f"{r.get('backlog', 0):.0f}", f"{r.get('due_next_2h', 0):.0f}"
    # (icon, step name, step caption, chapter title, the words, key facts, the time on the clock)
    chapters = [
        ("plane", "Lands", hm(r["arr"]), f"A {r['aircraft']} lands",
         f"{when}, flight {r['flight']} from {r['carrier']} touches down from {r['region']}, {behind}, with "
         f"{ctx['n_flight']} shipments on board.",
         [f"Flight {r['flight']}", f"Landed {hm(r['arr'])}", behind.replace(" behind schedule", " late")], hm(r["arr"])),
        ("crate", "One shipment", noun, f"One shipment of {noun}",
         f"We follow {r['id']}: {r['pieces']} pieces of {noun} weighing {r['weight']:,.1f} kg. Its promise: ready to "
         f"collect within {r['sla_h']:g} hours of landing, so by {hm(r['due'])}.",
         [r["id"], f"{r['sla_h']:g}-hour promise", f"Due {hm(r['due'])}"], hm(r["arr"])),
        ("queue", "The queue", f"{backlog} waiting", "It joins a queue",
         f"{backlog} shipments are already waiting to be unpacked, and {coming} more are due within two hours. The "
         f"{ctx['shift']} shift has {ctx['crew_now']} people to unpack them all.",
         [f"{backlog} waiting", f"{coming} due soon", f"{ctx['crew_now']} on shift"], hm(r["arr"])),
        ("flag", "Flagged" if flagged else "Scored", f"{r.get('score', 0):.0%} risk", "The early warning",
         f"The moment it lands, the early-warning model gives it a {r.get('score', 0):.0%} chance of being late. Only "
         f"{higher} in 100 shipments score higher, "
         + ("so it goes on the fast-track list for supervisors." if flagged else "so it stays off the list."),
         [f"{r.get('score', 0):.0%} risk", f"Riskiest {top} in 100" if flagged else "Not flagged",
          "Fast-track list" if flagged else "No alert"], hm(r["arr"])),
        ("clock", "Ready", f"{hm(r['nfd'])}, {S.dur(r['margin_min'])} {'late' if late else 'early'}", "What happened",
         f"It is checked in at {hm(r['rcf'])} and ready at {hm(r['nfd'])}: {S.dur(r['margin_min'])} "
         + ("after the promise ran out." if late else "inside the promise.")
         + (f" The customer collects it at {hm(r['dlv'])}; that wait is on the customer's clock."
            if r["customer_min"] is not None else ""),
         [f"Ready {hm(r['nfd'])}", f"{S.dur(r['margin_min'])} {'late' if late else 'early'}"]
         + ([f"Collected {hm(r['dlv'])}"] if r["customer_min"] is not None else []), hm(r["nfd"])),
        ("question", "What next", "three questions", "What would have helped?",
         "One late shipment raises three questions. Each has a page in this lab that answers it for every shipment, "
         "not just this one.", [], "afterwards"),
    ]
    q = str(st.query_params.get("story", "1"))
    step = min(max(int(q) - 1, 0), len(chapters) - 1) if q.isdigit() else 0

    def to_chapter(n: int) -> None:
        st.query_params["story"] = str(n + 1)

    _, _, _, title, words, facts, clock = chapters[step]
    with ui.plate("The story: one shipment, one night", "A real record from the simulation, picked by a fixed rule: the "
                                                        "first late shipment in the test months that the early-warning "
                                                        "model flagged. Click any step, or use Next."):
        st.markdown(story.journey([c[:3] for c in chapters], step), unsafe_allow_html=True)
        left, right = st.columns([0.6, 0.4], gap="large", vertical_alignment="center")
        with left:
            st.markdown(f'<div class="scene">{story.SCENES[step](r, ctx)}</div>', unsafe_allow_html=True)
        with right:
            chips = "".join(f"<span>{ui.esc(f)}</span>" for f in facts)
            dots = "".join(f'<i class="{"on" if i <= step else ""}"></i>' for i in range(len(chapters)))
            st.markdown(f'<div class="story"><div class="dots">{dots}<span>Chapter {step + 1} of {len(chapters)}, '
                        f'{ui.esc(clock)}</span></div><h3>{ui.esc(title)}</h3><p>{ui.esc(words)}</p>'
                        + (f'<div class="chips">{chips}</div>' if chips else "") + "</div>", unsafe_allow_html=True)
            b1, b2 = st.columns(2)
            last = step == len(chapters) - 1
            b1.button("Back", icon=":material/arrow_back:", disabled=step == 0, width="stretch", on_click=to_chapter,
                      args=(step - 1,))
            b2.button("Start again" if last else "Next", icon=":material/replay:" if last else ":material/arrow_forward:",
                      type="primary", width="stretch", on_click=to_chapter, args=(0 if last else step + 1,))
            if last:
                st.markdown(f'<p class="small">Or open <a href="legal?awb={r["id"]}" target="_self">this shipment&#39;s '
                            f'file on the Legal desk</a>.</p>', unsafe_allow_html=True)

# ---------------------------------------------------------------- the journey
a, b, c = k["arr_to_rcf_mean_h"], k["rcf_to_nfd_mean_h"], k["nfd_to_dlv_mean_h"]
tot = a + b + c
x0, w = 40, 920
xa, xb, xc = x0, x0 + w * a / tot, x0 + w * (a + b) / tot
xd = x0 + w


def tick(x, name, code, anchor="middle", above=False):
    """A step on the line: its plain name, with the industry code under it in small letters."""
    y_name, y_code = (40, 56) if above else (127, 144)
    y1, y2 = (62, 100) if above else (70, 108)
    return (f'<line x1="{x:.1f}" y1="{y1}" x2="{x:.1f}" y2="{y2}" stroke="{ui.INK}" stroke-width="1.2"/>'
            f'<text x="{x:.1f}" y="{y_name}" text-anchor="{anchor}" font-family="IBM Plex Sans Condensed, Arial Narrow, sans-serif" '
            f'font-size="15" fill="{ui.INK}">{name}</text>'
            f'<text x="{x:.1f}" y="{y_code}" text-anchor="{anchor}" font-family="Old Standard TT, Georgia, serif" font-size="11" '
            f'letter-spacing="1.5" fill="{ui.MUTED}">{code}</text>')


svg = f"""
<div class="clocks"><svg viewBox="0 -40 1000 200" role="img" aria-label="The journey of a shipment: the plane lands,
 the freight is checked in, it is ready to collect, and the customer collects it. The terminal's time runs from landing
 to ready; the customer's time from ready to collected">
<defs><pattern id="hx" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
<path d="M0 0v5" stroke="rgba(10,20,32,.35)" stroke-width="1.2"/></pattern></defs>
<path d="M{xa:.1f} 0 v-12 h{xc - xa:.1f} v12" fill="none" stroke="{ui.GOLD}" stroke-width="1.2"/>
<text x="{xa:.1f}" y="-20" text-anchor="start" font-family="IBM Plex Sans Condensed, sans-serif" font-size="14"
 fill="{ui.GOLD}">The terminal's time: {a + b:.1f} hours on average. The promise covers this part.</text>
<path d="M{xc + 6:.1f} 0 v-12 h{xd - xc - 6:.1f} v12" fill="none" stroke="{ui.NEU}" stroke-width="1.2"/>
<text x="{xd:.1f}" y="-20" text-anchor="end" font-family="IBM Plex Sans Condensed, sans-serif" font-size="14"
 fill="{ui.INK2}">The customer's time: {c:.1f} hours on average (customs, paperwork, pickup)</text>
<rect x="{xa:.1f}" y="70" width="{xb - xa:.1f}" height="30" fill="{ui.GOLD}"/><rect x="{xa:.1f}" y="70" width="{xb - xa:.1f}" height="30" fill="url(#hx)"/>
<rect x="{xb:.1f}" y="70" width="{xc - xb:.1f}" height="30" fill="#c98a2e"/><rect x="{xb:.1f}" y="70" width="{xc - xb:.1f}" height="30" fill="url(#hx)"/>
<rect x="{xc:.1f}" y="70" width="{xd - xc:.1f}" height="30" fill="{ui.CTX}"/><rect x="{xc:.1f}" y="70" width="{xd - xc:.1f}" height="30" fill="url(#hx)"/>
{tick(xa, "Plane lands", "ARR", "start")}{tick(xb, "Checked in", "RCF", "end", above=True)}{tick(xc, "Ready to collect", "NFD", "start")}{tick(xd, "Collected", "DLV", "end")}
</svg></div>"""
mobile = (f'<div class="clocks-m"><div class="bar"><i style="width:{100 * a / tot:.2f}%;background-color:{ui.GOLD}"></i>'
          f'<i style="width:{100 * b / tot:.2f}%;background-color:#c98a2e"></i>'
          f'<i style="width:{100 * c / tot:.2f}%;background-color:{ui.CTX}"></i></div><dl>'
          f'<dt><span class="sw" style="background:{ui.GOLD}"></span>Lands to checked in</dt><dd>towing in and unpacking</dd><dd class="v">{a:.1f} h</dd>'
          f'<dt><span class="sw" style="background:#c98a2e"></span>Checked in to ready</dt><dd>paperwork check</dd><dd class="v">{b:.1f} h</dd>'
          f'<dt><span class="sw" style="background:{ui.CTX}"></span>Ready to collected</dt><dd>customs, paperwork, pickup: the customer\'s time</dd><dd class="v">{c:.1f} h</dd>'
          f'</dl></div>')
with ui.plate("The journey of a shipment", "Average hours between each step, for shipments ready at least a week "
                                           "before the data ends. The small letters are the industry's names for each step."):
    st.markdown(svg + mobile, unsafe_allow_html=True)
    ui.takeaway(f"The terminal accounts for only <b>{ui.pct(k['handler_share'])}</b> of the time between landing and "
                f"collection. The promise, and every on-time figure in this lab, covers that part alone. The rest is "
                f"customs and the customer, and blaming the terminal for it is a classic mistake.")

# ---------------------------------------------------------------- five answers
ui.section("Five questions, five answers", "Each one is a page of the lab. Open any of them for the evidence.")
sc = ui.table("dq_scorecard")
ros = ui.table("rosters")
gap = h["dq_raw"] - h["dq_truth"]
week = {p: ros[ros["policy"] == p].groupby("shift")["headcount"].sum() for p in ("legacy", "optimized")}
move = week["optimized"] - week["legacy"]
up = [ui.SHIFTS[i].lower() for i in move.index if move[i] > 0]
down = [ui.SHIFTS[i].lower() for i in move.index if move[i] < 0]
pl = lambda xs: " and ".join(xs) + (" shifts" if len(xs) > 1 else " shift")  # noqa: E731
moves = (f" It moves people to when the freight lands: more on the {pl(up)}, fewer on the {pl(down)}."
         if up and down else "")
fx = cfg["flex"]
replan = "brings it back to" if h["dis_replanned"] > h["dis_static"] else "gets"
answers = {
    "kpis": (ui.in100(h["nfd_on_time"]), "gold",
             f"shipments are ready to collect within the promise. The slowest tenth take more than "
             f"{h['handler_p90_h']:.1f} hours from landing. Most of the waiting after that belongs to customs and the "
             f"customer, not the terminal."),
    "dq": (f"{abs(100 * gap):.1f} points", "loss",
           f"is how far the records, taken at face value, {'understate' if gap < 0 else 'overstate'} on-time "
           f"performance: {ui.pct(h['dq_raw'])} instead of the true {ui.pct(h['dq_truth'])}. {len(sc)} automatic checks "
           f"catch nearly every error; after fixing what is safe and setting the rest aside, the figure is "
           f"{ui.pct(h['dq_repaired'])}."),
    "risk": (ui.pct(h["model_catch"], 0), "gain",
             f"of the shipments that end up late are among the riskiest {ui.pct(h['expedite_share'], 0)} an early-warning "
             f"model flags when their plane lands. A random pick of the same size would catch "
             f"{ui.pct(h['expedite_share'], 0)}."),
    "roster": (ui.pct(h["opt_on_time"]), "gain",
               f"of shipments ready on time with a recommended roster, against {ui.pct(h['legacy_on_time'])} with the "
               f"current one, using {h['legacy_hours_week'] - h['opt_hours_week']:,.0f} fewer staff hours a week.{moves}"),
    "disruption": (ui.pct(h["dis_static"]), "loss",
                   f"on time when {ui.pct(h['dis_share'], 0)} of flights are squeezed into two daily rush hours, down "
                   f"from {ui.pct(h['base_static'])}. Re-planning the roster {replan} {ui.pct(h['dis_replanned'])}; "
                   f"keeping it and calling in {fx['pool_size']} on-call staff when the queue grows reaches "
                   f"{ui.pct(h['dis_flex'])}."),
}
rows = []
for p in ui.PAGES:
    if p["key"] not in answers:
        continue
    v, tone, s = answers[p["key"]]
    rows.append(f'<a class="finding" href="{p["url"]}" target="_self"><span class="pn">{p["num"]}</span>'
                f'<span><span class="pe">{ui.esc(p["eyebrow"])}</span><span class="q">{ui.esc(p["q"])}</span></span>'
                f'<span class="ans"><span class="v {tone}">{ui.esc(v)}</span><span class="s">{ui.esc(s)}</span>'
                f'<span class="go">Open: {ui.esc(p["title"])}</span></span></a>')
st.markdown(f'<div class="findings">{"".join(rows)}</div>', unsafe_allow_html=True)
test0 = pd.Timestamp(cfg["split"]["valid_end"]) + pd.Timedelta(days=1)
ui.note(f"Measured on the {ui.num(k['awbs'])} shipments whose records passed the data checks. The early-warning, "
        f"staffing and disruption answers are measured on the last months of data, {test0:%B} to {cut:%B %Y}.")

# ---------------------------------------------------------------- tools
ui.section("Two tools anyone can use", "No charts to read.")
tools = [("§", ui.PAGE["legal"], "Look up any shipment and get a plain answer: what was promised, whether it was kept, "
                                 "and whose clock any delay was on. Test a promise before it goes into a contract."),
         ("?", ui.PAGE["ask"], "Ask a question in your own words, or paste a shipment number. The answers come from "
                               "the lab's stored results.")]
st.markdown('<div class="parts">' + "".join(
    f'<a class="part-card" href="{p["url"]}" target="_self"><span class="pn">{n}</span>'
    f'<span class="pe">{ui.esc(p["eyebrow"])}</span>'
    f'<b>{ui.esc(p["title"] if p["nav"].lower() in p["title"].lower() else p["nav"] + ": " + p["title"])}</b>'
    f'<span class="ps">{ui.esc(t)}</span></a>' for n, p, t in tools) + "</div>", unsafe_allow_html=True)

# ---------------------------------------------------------------- freight by month
ui.section("How much freight lands each month")
m = ui.table("monthly")
fig = go.Figure(go.Bar(x=m["arr_month"], y=m["tonnes"], marker=ui.hatched(ui.NEU),
                       customdata=m[["awbs"]], hovertemplate="%{x|%B %Y}<br>%{y:,.0f} tonnes<br>%{customdata[0]:,} shipments<extra></extra>"))
fig.update_yaxes(title_text="Tonnes", tickformat=",")
fig.update_xaxes(tickformat="%b<br>%Y", dtick="M2")
with ui.plate("Tonnes landed each month", f"Shipments that passed the data checks, {start:%B %Y} to {cut:%B %Y}"):
    ui.show(fig, 300)
    lo, hi = m.loc[m["tonnes"].idxmin()], m.loc[m["tonnes"].idxmax()]
    ui.takeaway(f"Volume ranges from {ui.num(lo['tonnes'])} tonnes ({lo['arr_month']:%B %Y}) to "
                f"{ui.num(hi['tonnes'])} tonnes ({hi['arr_month']:%B %Y}). The share ready on time stays between "
                f"{ui.pct(m['on_time'].min())} and {ui.pct(m['on_time'].max())} every month.")

# ---------------------------------------------------------------- words
ui.section("Words you will see", "The rest are in the glossary on the Methods page.")
keep = ["Shipment", "Ready to collect", "The promise", "On time", "Container", "Unpacking", "Queue", "Roster",
        "Percentage point", "Synthetic"]
terms = {t[0]: t for t in ui.glossary_terms()}
ui.glossary([terms[t] for t in keep])
ui.footer()
