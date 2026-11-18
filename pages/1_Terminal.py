import plotly.graph_objects as go
import streamlit as st

from lab import config as C
from lab import ui

h = ui.headline()
k = ui.table("kpi_summary").set_index("kpi")["value"]
tt = C.timetable()
n_belly, n_fr = int((tt["type"] == "belly").sum()), int((tt["type"] == "freighter").sum())

ui.page("terminal", lede=ui.TAGLINE)
ui.prose(
    f"A synthetic import terminal at a Gulf hub, built to show how an analyst would run its numbers. A weekly "
    f"timetable of {len(tt)} flight lines ({n_belly} passenger aircraft carrying cargo in the hold and {n_fr} freighters, "
    f"from {tt['carrier'].nunique()} carriers labeled A to T) lands {ui.num(k['awbs_total'])} air waybills (AWBs) and "
    f"{ui.num(k['tonnes_total'])} tonnes between April 2025 and the data cut-off on 30 September 2026.",
    "A discrete-event simulation runs the floor: ULDs are towed in, broken down by the shift on duty, checked, and "
    "released to the customer. Every milestone in the lab comes out of that run. Nothing here is real data, and no "
    "terminal, airline or airport is named.",
)

teaser = (f'<a class="teaser" href="disruption" target="_self"><span class="k">The twist</span>'
          f'<span class="t">{ui.esc(h["sentences"]["headline"])}</span><span class="go">Open When the Schedule Breaks</span></a>')
ui.proof([
    {"k": "NFD on time", "v": ui.pct(k["nfd_on_time"]), "d": "Freight ready within the promise, counted from arrival"},
    {"k": "Handler time p90", "v": ui.hrs(k["handler_p90_h"]), "d": f"Arrival to ready; the median is {ui.hrs(k['handler_p50_h'])}"},
    {"k": "Late per 1,000 AWBs", "v": ui.num(k["late_per_1000"]), "d": "The same measure, read as a count", "tone": "loss"},
    {"html": teaser},
])
ui.note(f"Measured on the {ui.num(k['awbs'])} AWBs that pass the data quality checks. History runs on the legacy roster.")

ui.section("Two clocks, two owners",
           "The terminal owns the time from aircraft arrival to freight ready. After that, customs and the forwarder "
           "own it. Blaming the terminal for dwell the customer owns is the classic mistake.")
a, b, c = k["arr_to_rcf_mean_h"], k["rcf_to_nfd_mean_h"], k["nfd_to_dlv_mean_h"]
tot = a + b + c
x0, w = 40, 920
xa, xb, xc = x0, x0 + w * a / tot, x0 + w * (a + b) / tot
xd = x0 + w


def tick(x, code, name, anchor="middle", above=False):
    """A milestone mark: the code and its name below the bar, or above it where two marks sit close together."""
    y_code, y_name = (58, 44) if above else (124, 142)
    y1, y2 = (62, 100) if above else (70, 108)
    return (f'<line x1="{x:.1f}" y1="{y1}" x2="{x:.1f}" y2="{y2}" stroke="{ui.INK}" stroke-width="1.2"/>'
            f'<text x="{x:.1f}" y="{y_code}" text-anchor="{anchor}" font-family="Old Standard TT, Georgia, serif" font-size="15" '
            f'letter-spacing="1.5" fill="{ui.INK}">{code}</text>'
            f'<text x="{x:.1f}" y="{y_name}" text-anchor="{anchor}" font-family="IBM Plex Sans Condensed, Arial Narrow, sans-serif" '
            f'font-size="13" fill="{ui.MUTED}">{name}</text>')


svg = f"""
<div class="clocks"><svg viewBox="0 -40 1000 200" role="img" aria-label="Milestones ARR, RCF, NFD and DLV on a time line,
 with the handler's clock from ARR to NFD and the customer's clock from NFD to DLV">
<defs><pattern id="hx" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
<path d="M0 0v5" stroke="rgba(10,20,32,.35)" stroke-width="1.2"/></pattern></defs>
<path d="M{xa:.1f} 0 v-12 h{xc - xa:.1f} v12" fill="none" stroke="{ui.GOLD}" stroke-width="1.2"/>
<text x="{xa:.1f}" y="-20" text-anchor="start" font-family="IBM Plex Sans Condensed, sans-serif" font-size="14"
 fill="{ui.GOLD}">Handler's clock: {a + b:.1f} h on average</text>
<path d="M{xc + 6:.1f} 0 v-12 h{xd - xc - 6:.1f} v12" fill="none" stroke="{ui.NEU}" stroke-width="1.2"/>
<text x="{(xc + xd) / 2:.1f}" y="-20" text-anchor="middle" font-family="IBM Plex Sans Condensed, sans-serif" font-size="14"
 fill="{ui.INK2}">Customer's clock: {c:.1f} h on average (customs, documents, pickup)</text>
<rect x="{xa:.1f}" y="70" width="{xb - xa:.1f}" height="30" fill="{ui.GOLD}"/><rect x="{xa:.1f}" y="70" width="{xb - xa:.1f}" height="30" fill="url(#hx)"/>
<rect x="{xb:.1f}" y="70" width="{xc - xb:.1f}" height="30" fill="#c98a2e"/><rect x="{xb:.1f}" y="70" width="{xc - xb:.1f}" height="30" fill="url(#hx)"/>
<rect x="{xc:.1f}" y="70" width="{xd - xc:.1f}" height="30" fill="{ui.CTX}"/><rect x="{xc:.1f}" y="70" width="{xd - xc:.1f}" height="30" fill="url(#hx)"/>
{tick(xa, "ARR", "aircraft arrives", "start")}{tick(xb, "RCF", "received from flight", "end", above=True)}{tick(xc, "NFD", "freight ready", "start")}{tick(xd, "DLV", "delivered", "end")}
</svg></div>"""
mobile = (f'<div class="clocks-m"><div class="bar"><i style="width:{100 * a / tot:.2f}%;background-color:{ui.GOLD}"></i>'
          f'<i style="width:{100 * b / tot:.2f}%;background-color:#c98a2e"></i>'
          f'<i style="width:{100 * c / tot:.2f}%;background-color:{ui.CTX}"></i></div><dl>'
          f'<dt><span class="sw" style="background:{ui.GOLD}"></span>ARR to RCF</dt><dd>arrival to received from flight</dd><dd class="v">{a:.1f} h</dd>'
          f'<dt><span class="sw" style="background:#c98a2e"></span>RCF to NFD</dt><dd>document check to freight ready</dd><dd class="v">{b:.1f} h</dd>'
          f'<dt><span class="sw" style="background:{ui.CTX}"></span>NFD to DLV</dt><dd>customs, documents, pickup</dd><dd class="v">{c:.1f} h</dd>'
          f'</dl></div>')
with ui.plate("Where the average shipment's time goes",
              "Mean hours between milestones, AWBs notified at least a week before the cut-off. RCF is received from flight."):
    st.markdown(svg + mobile, unsafe_allow_html=True)
    ui.takeaway(f"The handler holds <b>{ui.pct(k['handler_share'])}</b> of the time between arrival and delivery. "
                f"The promise, and every on-time measure in this lab, applies only to that part.")

ui.section("What lands, month by month")
m = ui.table("monthly")
fig = go.Figure(go.Bar(x=m["arr_month"], y=m["tonnes"], marker=ui.hatched(ui.NEU),
                       customdata=m[["awbs"]], hovertemplate="%{x|%B %Y}<br>%{y:,.0f} tonnes<br>%{customdata[0]:,} AWBs<extra></extra>"))
fig.update_yaxes(title_text="Tonnes", tickformat=",")
fig.update_xaxes(tickformat="%b<br>%Y", dtick="M2")
with ui.plate("Tonnes landed each month", "Cleaned AWBs by month of arrival, April 2025 to September 2026"):
    ui.show(fig, 300)
    lo, hi = m.loc[m["tonnes"].idxmin()], m.loc[m["tonnes"].idxmax()]
    ui.takeaway(f"Volume ranges from {ui.num(lo['tonnes'])} tonnes ({lo['arr_month']:%B %Y}) to "
                f"{ui.num(hi['tonnes'])} tonnes ({hi['arr_month']:%B %Y}). On-time performance by month stays between "
                f"{ui.pct(m['on_time'].min())} and {ui.pct(m['on_time'].max())}.")

ui.section("How the lab is built", "Five parts, in the order an analyst would work, then the appendix.")
cards = []
for p in ui.PAGES[1:]:
    n = p["num"] or "A"
    cards.append(f'<a class="part-card" href="{p["url"]}" target="_self"><span class="pn">{n}</span>'
                 f'<span class="pe">{ui.esc(p["eyebrow"])}</span><b>{ui.esc(p["title"])}</b>'
                 f'<span class="ps">{ui.esc(p["teaser"])}</span></a>')
st.markdown(f'<div class="parts">{"".join(cards)}</div>', unsafe_allow_html=True)
ui.footer()
