import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lab import config as C
from lab import shipments as S
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
    on_flight = S.book()
    n_flight = int(((on_flight["flight"].astype(str) == r["flight"]) & (on_flight["arr_ts"] == r["arr"])).sum())
    late_min = (r["arr"] - r["sched"]).total_seconds() / 60
    wd, si = S.shift_of(r["arr"])
    legacy_ros, rec_ros = C.legacy_roster(), ui.table("rosters")
    crew_now = int(legacy_ros[wd][si])
    crew_rec = int(rec_ros[(rec_ros["policy"] == "optimized") & (rec_ros["weekday"] == wd) & (rec_ros["shift"] == si)]["headcount"].iloc[0])
    shift_name = ui.SHIFTS[si].lower()
    noun = ui.PRODUCT_NOUNS[r["product"]]
    when = ("Shortly after midnight on " if r["arr"].hour < 3 else "On ") + S.when(r["arr"])
    lateness = (f", {late_min:.0f} minutes behind schedule" if late_min > 5 else
                f", {-late_min:.0f} minutes early" if late_min < -5 else ", on schedule")
    if crew_rec == crew_now:
        helped = (f"The recommended roster keeps {crew_now} people on that {shift_name} shift, so staffing alone would "
                  f"not have changed this night.")
    else:
        helped = (f"The recommended roster puts {crew_rec} people on that {shift_name} shift instead of {crew_now}.")
    if r.get("flagged"):
        helped += (" The early-warning model did flag it, though: a supervisor watching the list could have moved it "
                   "up. Whether that would have saved the minutes it missed by is a question for a trial on the floor, "
                   "not for the records.")
    helped += " The five questions below show what the lab can answer."
    chapters = [
        ("A freighter lands" if r["aircraft"] == "freighter" else "A plane lands",
         f"{when}, flight {r['flight']}, a {r['aircraft']} from {r['carrier']}, lands from {r['region']} at "
         f"{r['arr']:%H:%M}{lateness}. On board are {n_flight} shipments."),
        (f"One shipment of {noun}",
         f"One of them, {r['id']}, is {r['pieces']} pieces of {noun} weighing {r['weight']:,.1f} kg, {r['unit']}. "
         f"{noun.capitalize()} come with a {r['sla_h']:g}-hour promise: the customer should hear the shipment is ready "
         f"by {r['due']:%H:%M}."),
        ("The queue",
         f"The terminal is already busy. {r.get('backlog', 0):.0f} shipments that landed earlier are still waiting to be "
         f"unpacked, and {r.get('due_next_2h', 0):.0f} more are due in the next two hours. The {shift_name} shift has "
         f"{crew_now} people scheduled."
         + (f" {noun.capitalize()} go near the front of the queue, but a crew cannot leave a container half unpacked"
            + (", and this one is large." if r["weight"] >= 1000 else ".")
            if r["product"] in cfg["priority_products"] else "")),
        ("The early warning",
         f"Scoring it the moment the plane lands, the early-warning model gives it a {r.get('score', 0):.0%} chance of "
         f"being late. That sounds low, but it is riskier than {r.get('rank', 0):.0%} of the shipments in these months"
         + (", so it lands on the fast-track list." if r.get("flagged") else ".")),
        ("What happened",
         f"It was checked in at {r['rcf']:%H:%M}, {S.dur((r['rcf'] - r['arr']).total_seconds() / 60)} after landing, and "
         f"ready to collect at {r['nfd']:%H:%M}: "
         + (f"{S.dur(r['margin_min'])} past the promise." if not r["on_time"] else f"{S.dur(r['margin_min'])} inside the promise.")
         + (f" The customer collected it at {r['dlv']:%H:%M}, {S.dur(r['customer_min'])} later, on the customer's clock."
            if r["customer_min"] is not None else "")),
        ("What the lab asks next", helped),
    ]
    step = min(st.session_state.get("story", 0), len(chapters) - 1)

    # the shipment's own timeline, revealed one chapter at a time
    t0 = r["arr"] - pd.Timedelta(minutes=20)
    t1 = max(x for x in (r["due"], r["nfd"], r["dlv"]) if pd.notna(x)) + pd.Timedelta(minutes=30)
    span = (t1 - t0).total_seconds()
    X0, W = 30, 940
    xt = lambda t: X0 + W * (t - t0).total_seconds() / span  # noqa: E731
    font = 'font-family="IBM Plex Sans Condensed, Arial Narrow, sans-serif"'
    parts = [f'<line x1="{X0}" y1="120" x2="{X0 + W}" y2="120" stroke="{ui.RULE_STRONG}" stroke-width="1"/>']
    hour = t0.ceil("h")
    while hour < t1:
        parts.append(f'<line x1="{xt(hour):.1f}" y1="116" x2="{xt(hour):.1f}" y2="124" stroke="{ui.RULE_STRONG}"/>'
                     f'<text x="{xt(hour):.1f}" y="142" text-anchor="middle" {font} font-size="13" fill="{ui.MUTED}">{hour:%H:%M}</text>')
        hour += pd.Timedelta(hours=1)
    xa = xt(r["arr"])
    parts.append(f'<circle cx="{xa:.1f}" cy="120" r="6" fill="{ui.INK}"/>'
                 f'<text x="{xa:.1f}" y="168" text-anchor="start" {font} font-size="14" fill="{ui.INK}">Lands {r["arr"]:%H:%M}</text>')
    if step >= 1:
        xd = xt(r["due"])
        parts.append(f'<line x1="{xd:.1f}" y1="34" x2="{xd:.1f}" y2="132" stroke="{ui.GOLD}" stroke-width="1.6" stroke-dasharray="5 4"/>'
                     f'<text x="{xd:.1f}" y="26" text-anchor="middle" {font} font-size="14" fill="{ui.GOLD}">Promise runs out {r["due"]:%H:%M}</text>')
    if step >= 2:
        parts.append(f'<text x="{xa:.1f}" y="58" text-anchor="start" {font} font-size="14" fill="{ui.INK2}">'
                     f'{r.get("backlog", 0):.0f} already waiting, {r.get("due_next_2h", 0):.0f} more due in 2 hours</text>')
    if step >= 3 and "score" in r:
        parts.append(f'<text x="{xa:.1f}" y="80" text-anchor="start" {font} font-size="14" fill="{ui.LOSS_INK if r.get("flagged") else ui.INK2}">'
                     f'Early warning: {r["score"]:.0%} risk' + (", on the fast-track list" if r.get("flagged") else "") + '</text>')
    if step >= 4:
        xr, xn = xt(r["rcf"]), xt(r["nfd"])
        cut_x = min(xn, xt(r["due"]))
        parts.append(f'<rect x="{xa:.1f}" y="104" width="{cut_x - xa:.1f}" height="14" fill="{ui.GOLD}" opacity=".85"/>')
        if xn > cut_x:
            parts.append(f'<rect x="{cut_x:.1f}" y="104" width="{xn - cut_x:.1f}" height="14" fill="{ui.LOSS}"/>')
        if pd.notna(r["dlv"]):
            xl = xt(r["dlv"])
            parts.append(f'<rect x="{xn:.1f}" y="122" width="{xl - xn:.1f}" height="8" fill="{ui.CTX}"/>'
                         f'<circle cx="{xl:.1f}" cy="126" r="5" fill="{ui.NEU}"/>'
                         f'<text x="{xl:.1f}" y="168" text-anchor="end" {font} font-size="14" fill="{ui.INK2}">Collected {r["dlv"]:%H:%M}</text>')
        parts.append(f'<circle cx="{xr:.1f}" cy="111" r="4" fill="{ui.INK}"/>'
                     f'<circle cx="{xn:.1f}" cy="111" r="6" fill="{ui.LOSS_INK if not r["on_time"] else ui.GAIN_INK}"/>'
                     f'<text x="{xn:.1f}" y="190" text-anchor="middle" {font} font-size="14" fill="{ui.INK}">'
                     f'Checked in {r["rcf"]:%H:%M}, ready {r["nfd"]:%H:%M}</text>')
    svg_story = (f'<div class="story-line"><svg viewBox="0 0 1000 200" role="img" aria-label="Timeline of shipment '
                 f'{r["id"]}">{"".join(parts)}</svg></div>')
    dots = "".join(f'<i class="{"on" if i <= step else ""}"></i>' for i in range(len(chapters)))
    title, body = chapters[step]
    with ui.plate("The story: one shipment, one night", f"A real record from the simulation, {r['id']}. It was picked by "
                                                        "a fixed rule: the first late shipment in the test months that "
                                                        "the early-warning model had flagged."):
        st.markdown(f'<div class="story"><div class="dots">{dots}<span>Chapter {step + 1} of {len(chapters)}</span></div>'
                    f'<h3>{ui.esc(title)}</h3><p>{ui.esc(body)}</p></div>{svg_story}', unsafe_allow_html=True)
        b1, b2, _ = st.columns([0.18, 0.22, 0.6])
        if b1.button("Back", icon=":material/arrow_back:", disabled=step == 0, width="stretch"):
            st.session_state.story = step - 1
            st.rerun()
        last = step == len(chapters) - 1
        if b2.button("Start again" if last else "Next", icon=":material/replay:" if last else ":material/arrow_forward:",
                     type="primary", width="stretch"):
            st.session_state.story = 0 if last else step + 1
            st.rerun()
        if last:
            st.page_link("pages/8_Legal.py", label=f"Open this shipment's file on the Legal desk ({r['id']})",
                         icon=":material/gavel:")

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
