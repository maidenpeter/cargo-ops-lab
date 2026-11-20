"""The overview's story as a picture book: a journey map across the top, a drawn scene for each chapter, and the
words beside it. Every value drawn comes from the shipment's stored record and the stored results."""
from __future__ import annotations

import math

import pandas as pd

from lab import shipments as S
from lab import ui

F_UI = "IBM Plex Sans Condensed, Arial Narrow, sans-serif"
F_NUM = "EB Garamond, Georgia, serif"
F_LBL = "Old Standard TT, Georgia, serif"
INK, INK2, MUTED, GOLD, LOSS, LOSS_INK, CTX = ui.INK, ui.INK2, ui.MUTED, ui.GOLD, ui.LOSS, ui.LOSS_INK, ui.CTX
GROUND, SURFACE, SUNK, RULE = ui.GROUND, ui.SURFACE, ui.SUNK, ui.RULE_STRONG
W, H = 640, 380  # every scene is drawn on the same canvas


# ---------------------------------------------------------------- drawing kit
def text(x, y, s, size=14, fill=INK, anchor="start", font=F_UI, spacing=None, weight=None) -> str:
    sp = f' letter-spacing="{spacing}"' if spacing else ""
    wt = f' font-weight="{weight}"' if weight else ""
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-family="{font}" font-size="{size}" fill="{fill}" '
            f'text-anchor="{anchor}"{sp}{wt}>{ui.esc(s)}</text>')


def label(x, y, s, fill=MUTED, anchor="start") -> str:
    """Small engraved capitals, like the labels on the site."""
    return text(x, y, s.upper(), 10.5, fill, anchor, F_LBL, spacing="1.6")


def defs(p: str) -> str:
    arrow = lambda i, c: (f'<marker id="{p}{i}" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="7" markerHeight="7" '  # noqa: E731
                          f'orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z" fill="{c}"/></marker>')
    return (f'<defs>{arrow("g", GOLD)}{arrow("m", MUTED)}{arrow("r", LOSS_INK)}{arrow("i", INK2)}'
            f'<pattern id="{p}h" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
            f'<path d="M0 0v5" stroke="rgba(10,20,32,.35)" stroke-width="1.2"/></pattern></defs>')


def svg(p: str, body: str, aria: str, w: int = W, h: int = H) -> str:
    return (f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="{ui.esc(aria)}" xmlns="http://www.w3.org/2000/svg">'
            f'{defs(p)}{body}</svg>')


def arrow(x1, y1, x2, y2, p, color="g", dash=False, width=1.6, curve=0.0) -> str:
    stroke = {"g": GOLD, "m": MUTED, "r": LOSS_INK, "i": INK2}[color]
    d = f"M{x1:.1f} {y1:.1f} L{x2:.1f} {y2:.1f}"
    if curve:
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2 - curve
        d = f"M{x1:.1f} {y1:.1f} Q{mx:.1f} {my:.1f} {x2:.1f} {y2:.1f}"
    da = ' stroke-dasharray="5 4"' if dash else ""
    return f'<path d="{d}" fill="none" stroke="{stroke}" stroke-width="{width}"{da} marker-end="url(#{p}{color})"/>'


def chip(x, y, s, color=GOLD, fill="rgba(240,166,58,.13)", size=13) -> str:
    w = 9 + 6.6 * len(s) * size / 13
    return (f'<rect x="{x:.1f}" y="{y - 15:.1f}" width="{w:.1f}" height="22" rx="11" fill="{fill}" stroke="{color}" '
            f'stroke-width="1"/>' + text(x + w / 2, y + 0.5, s, size, color, "middle"))


def plane(x, y, s=1.0, rot=0.0, fill=INK) -> str:
    """A cargo plane in profile, nose to the right."""
    return (f'<g transform="translate({x:.1f},{y:.1f}) rotate({rot:.1f}) scale({s:.2f})" fill="{fill}">'
            '<path d="M-62 -2 Q-62 -10 -50 -10 L40 -10 Q60 -10 68 0 Q60 8 40 8 L-50 8 Q-62 8 -62 -2 z"/>'
            '<path d="M-56 -10 L-66 -32 L-52 -32 L-38 -10 z"/>'
            '<path d="M-8 0 L22 0 L0 28 L-14 28 z" opacity=".8"/>'
            '<path d="M-60 0 L-40 0 L-48 9 L-62 9 z" opacity=".8"/>'
            f'<path d="M50 -7 L60 -7 L63 -2 L50 -2 z" fill="{GROUND}"/></g>')


def crate(x, y, w, h, d, stroke=GOLD) -> str:
    """A container drawn in three-quarter view."""
    planks = "".join(f'<line x1="{x}" y1="{y + h * k / 5:.1f}" x2="{x + w}" y2="{y + h * k / 5:.1f}" stroke="{stroke}" '
                     f'stroke-width=".7" opacity=".35"/>' for k in range(1, 5))
    return (f'<polygon points="{x},{y} {x + d},{y - d} {x + w + d},{y - d} {x + w},{y}" fill="{SUNK}" stroke="{stroke}" stroke-width="1.3"/>'
            f'<polygon points="{x + w},{y} {x + w + d},{y - d} {x + w + d},{y + h - d} {x + w},{y + h}" fill="{GROUND}" stroke="{stroke}" stroke-width="1.3"/>'
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{SURFACE}" stroke="{stroke}" stroke-width="1.3"/>{planks}')


def person(x, y, s=1.0, fill=INK2) -> str:
    return (f'<g fill="{fill}"><circle cx="{x:.1f}" cy="{y - 8 * s:.1f}" r="{3.4 * s:.1f}"/>'
            f'<rect x="{x - 5 * s:.1f}" y="{y - 3.5 * s:.1f}" width="{10 * s:.1f}" height="{11 * s:.1f}" rx="{3.5 * s:.1f}"/></g>')


def truck(x, y, s=1.0, fill=INK2) -> str:
    return (f'<g transform="translate({x:.1f},{y:.1f}) scale({s:.2f})" fill="{fill}">'
            '<rect x="-30" y="-20" width="36" height="22" rx="2"/><path d="M8 -14 L20 -14 L28 -4 L28 2 L8 2 z"/>'
            f'<circle cx="-20" cy="5" r="5" stroke="{GROUND}" stroke-width="2"/><circle cx="18" cy="5" r="5" stroke="{GROUND}" stroke-width="2"/></g>')


def polar(cx, cy, r, deg):
    a = math.radians(deg)
    return cx + r * math.sin(a), cy - r * math.cos(a)


def dial(ts: pd.Timestamp) -> float:
    """Angle of a time on a twelve-hour clock face, in degrees clockwise from twelve."""
    return ((ts.hour % 12) + ts.minute / 60) * 30


def squares(x0, y0, n, cols, size, gap, fill, opacity=1.0, stroke=None) -> str:
    st = f' stroke="{stroke}" stroke-width=".8"' if stroke else ""
    return "".join(f'<rect x="{x0 + (i % cols) * (size + gap):.1f}" y="{y0 + (i // cols) * (size + gap):.1f}" '
                   f'width="{size}" height="{size}" rx="1.5" fill="{fill}" opacity="{opacity}"{st}/>' for i in range(n))


def lines(x, y, rows: list[str], size=13.5, fill=INK2, gap=18, anchor="start", font=F_UI) -> str:
    return "".join(text(x, y + i * gap, r, size, fill, anchor, font) for i, r in enumerate(rows))


def hm(ts: pd.Timestamp) -> str:
    return f"{ts:%H:%M}"


# ---------------------------------------------------------------- the six scenes
def scene_land(r: dict, c: dict) -> str:
    p = "s1"
    late = c["flight_late_min"]
    b = [f'<rect x="20" y="322" width="600" height="24" fill="{SUNK}" stroke="{RULE}"/>']
    b += [f'<line x1="{x}" y1="334" x2="{x + 22}" y2="334" stroke="{INK2}" stroke-width="2" opacity=".55"/>' for x in range(40, 600, 44)]
    b.append(arrow(34, 120, 395, 318, p, "g", dash=True, curve=-60))
    b.append(plane(205, 196, 1.25, 24, INK))
    b.append(label(30, 40, "Scheduled"))
    b.append(text(30, 70, hm(r["sched"]), 30, MUTED, font=F_NUM))
    b.append(f'<line x1="28" y1="61" x2="102" y2="61" stroke="{MUTED}" stroke-width="1.2"/>')
    b.append(arrow(112, 60, 150, 60, p, "m"))
    b.append(label(162, 40, "Landed", GOLD))
    b.append(text(162, 70, hm(r["arr"]), 34, GOLD, font=F_NUM))
    if abs(late) > 5:
        b.append(chip(252, 62, f"{late:.0f} min {'late' if late > 0 else 'early'}", LOSS_INK if late > 0 else ui.GAIN_INK,
                      "rgba(217,105,79,.15)" if late > 0 else "rgba(37,163,164,.15)"))
    b.append(text(398, 314, "touchdown", 12, GOLD, "middle"))
    n = c["n_flight"]
    cols = 7 if n <= 49 else 10
    size = 14 if n <= 49 else 10
    shown = min(n, 100)
    gx, gy = 452, 132
    b.append(label(gx, 104, "On board"))
    b.append(text(gx, 124, f"{n} shipments", 15, INK))
    b.append(squares(gx, gy, shown, cols, size, 4, INK2, .5))
    k = shown // 2
    kx, ky = gx + (k % cols) * (size + 4), gy + (k // cols) * (size + 4)
    b.append(f'<rect x="{kx:.1f}" y="{ky:.1f}" width="{size}" height="{size}" rx="1.5" fill="{GOLD}"/>')
    rows = math.ceil(shown / cols)
    yb = gy + rows * (size + 4) + 18
    b.append(f'<line x1="{kx + size / 2:.1f}" y1="{ky + size:.1f}" x2="{kx + size / 2:.1f}" y2="{yb - 12:.1f}" stroke="{GOLD}"/>')
    b.append(text(kx + size / 2, yb, r["id"], 12.5, GOLD, "middle"))
    b.append(text(30, 300, f"{r['aircraft'].capitalize()} {r['flight']}, {r['carrier']}, from {r['region']}", 13.5, INK2))
    return svg(p, "".join(b), f"Flight {r['flight']} lands at {hm(r['arr'])}")


def scene_shipment(r: dict, c: dict) -> str:
    p = "s2"
    b = [crate(52, 132, 196, 138, 34)]
    if r["product"] == "pharma":
        b.append(f'<rect x="139" y="160" width="22" height="60" fill="{GOLD}"/><rect x="120" y="179" width="60" height="22" fill="{GOLD}"/>')
    else:
        b.append(f'<rect x="96" y="176" width="108" height="30" fill="none" stroke="{GOLD}" stroke-width="1.4"/>')
    b.append(text(150, 250, c["noun"].upper(), 13, INK, "middle", F_LBL, spacing="2"))
    b.append(f'<line x1="248" y1="132" x2="290" y2="84" stroke="{INK2}" stroke-width="1"/>')
    b.append(f'<rect x="262" y="58" width="132" height="30" rx="3" fill="{SUNK}" stroke="{GOLD}"/>'
             f'<circle cx="274" cy="73" r="3.5" fill="none" stroke="{GOLD}"/>' + text(334, 78, r["id"], 13.5, GOLD, "middle"))
    b.append(text(52, 306, f"{r['pieces']} pieces, {r['weight']:,.1f} kg", 15, INK))
    b.append(text(52, 328, r["unit"], 13, MUTED))
    cx, cy, rr = 505, 200, 96
    b.append(f'<circle cx="{cx}" cy="{cy}" r="{rr}" fill="{SUNK}" stroke="{INK2}" stroke-width="1.2"/>')
    for k in range(12):
        x1, y1 = polar(cx, cy, rr - 2, k * 30)
        x2, y2 = polar(cx, cy, rr - (12 if k % 3 == 0 else 7), k * 30)
        b.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{INK2}" stroke-width="{1.6 if k % 3 == 0 else .8}"/>')
    for k, n in ((0, "12"), (3, "3"), (6, "6"), (9, "9")):
        x, y = polar(cx, cy, rr - 24, k * 30)
        b.append(text(x, y + 5, n, 13, MUTED, "middle", F_NUM))
    a0, a1 = dial(r["arr"]), dial(r["due"])
    span = (a1 - a0) % 360
    x0, y0 = polar(cx, cy, rr + 12, a0)
    x1, y1 = polar(cx, cy, rr + 12, a0 + span)
    b.append(f'<path d="M{x0:.1f} {y0:.1f} A{rr + 12} {rr + 12} 0 {1 if span > 180 else 0} 1 {x1:.1f} {y1:.1f}" fill="none" '
             f'stroke="{GOLD}" stroke-width="7" stroke-linecap="round" opacity=".9"/>')
    b.append(f'<circle cx="{x0:.1f}" cy="{y0:.1f}" r="6" fill="{INK}"/><circle cx="{x1:.1f}" cy="{y1:.1f}" r="6" fill="{GOLD}"/>')
    lx, ly = polar(cx, cy, rr + 30, a0)
    b.append(text(lx - 4, ly - 6, f"lands {hm(r['arr'])}", 12.5, INK, "end"))
    ex, ey = polar(cx, cy, rr + 30, a0 + span)
    b.append(text(ex + 6, ey + 4, f"due {hm(r['due'])}", 12.5, GOLD, "start" if (a0 + span) % 360 < 180 else "end"))
    b.append(text(cx, cy + 6, f"{r['sla_h']:g} h", 34, GOLD, "middle", F_NUM))
    b.append(text(cx, cy + 28, "promise", 13, INK2, "middle"))
    b.append(arrow(300, 205, 396, 205, p, "i"))
    b.append(text(348, 196, "the clock", 12, MUTED, "middle"))
    b.append(text(348, 228, "starts at landing", 12, MUTED, "middle"))
    return svg(p, "".join(b), f"{r['id']}, {c['noun']}, with a {r['sla_h']:g}-hour promise")


def scene_queue(r: dict, c: dict) -> str:
    p = "s3"
    waiting, coming = int(round(r.get("backlog", 0))), int(round(r.get("due_next_2h", 0)))
    b = [label(20, 96, "Due within 2 hours"), text(20, 114, f"{coming} more", 15, INK2)]
    b.append(squares(20, 128, min(coming, 120), 10, 8, 4, INK2, .32))
    b.append(arrow(144, 190, 196, 190, p, "m"))
    b.append(label(206, 96, "Already waiting"))
    b.append(text(206, 114, f"{waiting} shipments", 15, INK))
    b.append(squares(206, 128, min(waiting, 80), 10, 13, 5, INK2, .75))
    sx, sy = 452, 74
    b.append(f'<rect x="{sx}" y="{sy}" width="170" height="214" rx="3" fill="{SURFACE}" stroke="{INK2}"/>')
    b.append(label(sx + 85, sy + 24, "Unpacking", INK2, "middle"))
    crew = c["crew_now"]
    for i in range(min(crew, 30)):
        b.append(person(sx + 26 + (i % 5) * 30, sy + 62 + (i // 5) * 34, 1.0, INK))
    b.append(text(sx + 85, sy + 202, f"{c['shift'].capitalize()} shift: {crew} people", 13.5, INK, "middle"))
    b.append(arrow(390, 190, 446, 190, p, "g", width=2))
    qx, qy = 404, 150
    b.append(f'<rect x="{qx}" y="{qy}" width="18" height="18" rx="2" fill="{GOLD}"/>')
    b.append(text(qx + 9, qy - 10, r["id"][-4:], 11, GOLD, "middle"))
    if c["priority"]:
        b.append(arrow(330, 256, qx + 9, qy + 24, p, "g", dash=True, curve=-30))
        b.append(lines(206, 286, [f"{c['noun'].capitalize()} go near the front,", "but a crew cannot leave a container",
                                  "half unpacked."], 12.5, GOLD))
    b.append(text(20, 352, "Each square is one shipment.", 12, MUTED))
    return svg(p, "".join(b), f"{waiting} shipments waiting, {coming} more due, {crew} people on shift")


def scene_warning(r: dict, c: dict) -> str:
    p = "s4"
    rank = r.get("rank", 0)
    me = min(99, max(0, int(round(rank * 100)) - 1))
    top = 100 - int(round(100 * c["expedite_share"]))
    gx, gy, cell = 30, 64, 27
    b = [label(gx, 40, "100 shipments, ranked by risk")]
    for i in range(100):
        x, y = gx + (i % 10) * cell + cell / 2, gy + (i // 10) * cell + cell / 2
        on_list = i >= top
        b.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{8 if i == me else 6.5}" fill="{GOLD if on_list else INK2}" '
                 f'opacity="{1 if i == me else (.55 if on_list else .28)}"/>')
    mx, my = gx + (me % 10) * cell + cell / 2, gy + (me // 10) * cell + cell / 2
    b.append(f'<circle cx="{mx:.1f}" cy="{my:.1f}" r="13" fill="none" stroke="{INK}" stroke-width="1.6"/>')
    b.append(text(gx, gy - 6, "lowest risk", 12, MUTED))
    b.append(text(gx + 10 * cell, gy + 10 * cell + 20, "highest risk", 12, MUTED, "end"))
    ly = gy + (top // 10) * cell
    b.append(f'<rect x="{gx - 4}" y="{ly - 3:.1f}" width="{10 * cell + 8}" height="{cell + 6}" rx="5" fill="none" '
             f'stroke="{GOLD}" stroke-width="1.2" stroke-dasharray="4 3"/>')
    b.append(text(gx, gy + 10 * cell + 20, f"the riskiest {100 - top}", 12, GOLD))
    cx, cy = 352, 92
    b.append(arrow(mx + 8, my - 14, cx - 4, cy + 110, p, "g", curve=50))
    b.append(f'<rect x="{cx}" y="{cy}" width="262" height="150" rx="3" fill="{SURFACE}" stroke="{GOLD}"/>')
    b.append(label(cx + 16, cy + 26, "Fast-track list", GOLD))
    b.append(text(cx + 16, cy + 58, r["id"], 16, INK))
    b.append(text(cx + 16, cy + 80, f"{c['noun'].capitalize()}, landed {hm(r['arr'])}", 13, INK2))
    b.append(text(cx + 246, cy + 66, f"{r.get('score', 0):.0%}", 30, GOLD, "end", F_NUM))
    b.append(text(cx + 246, cy + 86, "chance of being late", 11.5, MUTED, "end"))
    b.append(lines(cx + 16, cy + 116, [f"Riskier than {round(rank * 100)} in 100 shipments,",
                                       f"so it joins the riskiest {100 - top}."], 13, INK2))
    b.append(lines(352, 300, ["The list goes to supervisors the moment", "the plane lands."], 13, MUTED))
    return svg(p, "".join(b), f"Risk {r.get('score', 0):.0%}, riskier than {round(rank * 100)} in 100 shipments")


def scene_outcome(r: dict, c: dict) -> str:
    p = "s5"
    t0 = r["arr"] - pd.Timedelta(minutes=25)
    end = r["dlv"] if pd.notna(r["dlv"]) else r["nfd"]
    t1 = max(end, r["due"]) + pd.Timedelta(minutes=25)
    x0, x1 = 30, 612
    xt = lambda ts: x0 + (x1 - x0) * (ts - t0).total_seconds() / (t1 - t0).total_seconds()  # noqa: E731
    ya = 214
    xa, xr, xn, xd = xt(r["arr"]), xt(r["rcf"]), xt(r["nfd"]), xt(r["due"])
    b = [f'<line x1="{x0}" y1="{ya}" x2="{x1}" y2="{ya}" stroke="{RULE}"/>']
    hr = t0.ceil("h")
    while hr < t1:
        x = xt(hr)
        b.append(f'<line x1="{x:.1f}" y1="{ya - 4}" x2="{x:.1f}" y2="{ya + 4}" stroke="{RULE}"/>'
                 + text(x, ya + 20, hm(hr), 11.5, MUTED, "middle"))
        hr += pd.Timedelta(hours=1)
    b.append(f'<rect x="{xa:.1f}" y="{ya - 30}" width="{xr - xa:.1f}" height="24" fill="{GOLD}"/>'
             f'<rect x="{xa:.1f}" y="{ya - 30}" width="{xr - xa:.1f}" height="24" fill="url(#{p}h)"/>')
    b.append(f'<rect x="{xr:.1f}" y="{ya - 30}" width="{xn - xr:.1f}" height="24" fill="#c98a2e"/>')
    late = xn > xd
    if late:
        b.append(f'<rect x="{xd:.1f}" y="{ya - 30}" width="{xn - xd:.1f}" height="24" fill="{LOSS}"/>')
    b.append(f'<path d="M{xa:.1f} {ya - 40} v-8 h{xr - xa:.1f} v8" fill="none" stroke="{INK2}"/>')
    b.append(text((xa + xr) / 2, ya - 56, f"{S.dur((r['rcf'] - r['arr']).total_seconds() / 60)}: towed in, queued, unpacked",
                  13, INK2, "middle"))
    b.append(f'<line x1="{xd:.1f}" y1="78" x2="{xd:.1f}" y2="{ya + 6}" stroke="{GOLD}" stroke-width="1.6" stroke-dasharray="5 4"/>')
    b.append(text(xd, 70, f"Promise runs out {hm(r['due'])}", 13.5, GOLD, "middle"))
    b.append(arrow(xd + 70, 120, xr + (xn - xr) / 2 + 2, ya - 32, p, "i", curve=20))
    b.append(text(xd + 74, 116, f"{S.dur((r['nfd'] - r['rcf']).total_seconds() / 60)} of paperwork", 12.5, INK2))
    if pd.notna(r["dlv"]):
        xl = xt(r["dlv"])
        b.append(f'<rect x="{xn:.1f}" y="{ya - 20}" width="{xl - xn:.1f}" height="12" fill="{CTX}"/>'
                 f'<rect x="{xn:.1f}" y="{ya - 20}" width="{xl - xn:.1f}" height="12" fill="url(#{p}h)"/>')
        b.append(truck(xl + 2, ya - 36, 0.75, INK2))
        b.append(text(xl - 30, ya - 30, f"{S.dur(r['customer_min'])}: the customer's time", 12.5, MUTED, "end"))
    marks = [(xa, f"Lands {hm(r['arr'])}", INK, "start", ya + 44), (xn, f"Ready {hm(r['nfd'])}", LOSS_INK if late else ui.GAIN_INK,
             "middle", ya + 44)]
    if pd.notna(r["dlv"]):
        marks.append((xt(r["dlv"]), f"Collected {hm(r['dlv'])}", INK2, "end", ya + 44))
    for x, s, col, anc, y in marks:
        b.append(f'<circle cx="{x:.1f}" cy="{ya}" r="5" fill="{col}"/>' + text(x, y, s, 14, col, anc))
    if late:
        b.append(chip(xn - 40, ya + 82, f"{S.dur(r['margin_min'])} late", LOSS_INK, "rgba(217,105,79,.15)", 14))
        b.append(arrow(xn - 2, ya + 64, xn, ya + 8, p, "r"))
    b.append(text(30, 360, f"Checked in {hm(r['rcf'])}. Hub local time.", 12, MUTED))
    return svg(p, "".join(b), f"Timeline: lands {hm(r['arr'])}, ready {hm(r['nfd'])}, promise {hm(r['due'])}")


def scene_next(r: dict, c: dict) -> str:
    p = "s6"
    late = r["margin_min"] is not None and r["margin_min"] < 0
    b = [f'<rect x="18" y="148" width="168" height="84" rx="4" fill="{SURFACE}" stroke="{LOSS_INK if late else ui.GAIN_INK}" stroke-width="1.4"/>']
    b.append(text(102, 182, f"Ready {S.dur(r['margin_min'])}", 15, INK, "middle"))
    b.append(text(102, 202, "late" if late else "early", 15, LOSS_INK if late else ui.GAIN_INK, "middle"))
    b.append(text(102, 222, r["id"], 11.5, MUTED, "middle"))
    staff = ([f"The recommended roster also has {c['crew_rec']} people", "on that shift: no change this time."]
             if c["crew_rec"] == c["crew_now"] else
             [f"The recommended roster puts {c['crew_rec']} there", f"instead of {c['crew_now']}."])
    flag = (["It was on the list. Only a trial on the floor", "can say if that saves the minutes."] if r.get("flagged")
            else ["It was not on the list, which is", "what the model misses."])
    broke = [f"With {c['dis_share']:.0%} of flights in rush hours, late", f"shipments rise from {c['late_base']:,.0f} to "
             f"{c['late_dis']:,.0f} a week."]
    nodes = [("More staff that night?", staff, 34, "roster"), ("Fast-track it?", flag, 150, "risk"),
             ("And if flights bunch?", broke, 266, "disruption")]
    for title, rows, y, key in nodes:
        page = ui.PAGE[key]
        b.append(arrow(190, 190, 252, y + 40, p, "g", curve=0))
        b.append(f'<a href="{page["url"]}" target="_self"><title>Open {ui.esc(page["nav"])}</title>'
                 f'<rect x="258" y="{y}" width="364" height="86" rx="4" fill="{SUNK}" stroke="{RULE}"/>'
                 f'<rect x="258" y="{y}" width="4" height="86" fill="{GOLD}"/>'
                 + text(276, y + 26, title, 15.5, INK, font=F_NUM) + lines(276, y + 48, rows, 13, INK2, 17)
                 + label(608, y + 26, f"Open {page['nav']}", GOLD, "end") + "</a>")
    return svg(p, "".join(b), "Three questions that follow from one late shipment")


SCENES = [scene_land, scene_shipment, scene_queue, scene_warning, scene_outcome, scene_next]


# ---------------------------------------------------------------- the journey map
def journey(stations: list[tuple[str, str, str]], cur: int) -> str:
    """Six stations joined by arrows; each is a link to its chapter."""
    p = "jm"
    n = len(stations)
    w, h = 1000, 138
    xs = [70 + i * (860 / (n - 1)) for i in range(n)]
    y = 42
    b = []
    for i in range(n - 1):
        done = i < cur
        b.append(f'<line x1="{xs[i] + 30:.1f}" y1="{y}" x2="{xs[i + 1] - 34:.1f}" y2="{y}" stroke="{GOLD if done else MUTED}" '
                 f'stroke-width="{2 if done else 1.2}"{"" if done else " stroke-dasharray=" + chr(34) + "4 4" + chr(34)} '
                 f'marker-end="url(#{p}{"g" if done else "m"})"/>')
    for i, ((icon, title, sub), x) in enumerate(zip(stations, xs)):
        state = "done" if i < cur else ("now" if i == cur else "next")
        ring = {"done": GOLD, "now": GOLD, "next": MUTED}[state]
        fill = {"done": "rgba(240,166,58,.14)", "now": GOLD, "next": "none"}[state]
        ic = {"done": INK, "now": GROUND, "next": MUTED}[state]
        g = [f'<circle cx="{x:.1f}" cy="{y}" r="26" fill="{fill}" stroke="{ring}" stroke-width="{2 if state == "now" else 1.3}"/>']
        if state == "now":
            g.append(f'<circle cx="{x:.1f}" cy="{y}" r="31" fill="none" stroke="{GOLD}" stroke-width=".8" opacity=".7"/>')
        g.append(icon_mark(icon, x, y, ic))
        g.append(text(x, y + 52, title, 13.5, INK if state != "next" else MUTED, "middle"))
        g.append(text(x, y + 70, sub, 12, GOLD if state == "now" else MUTED, "middle"))
        b.append(f'<a href="?story={i + 1}" target="_self"><title>Chapter {i + 1}: {ui.esc(title)}</title>{"".join(g)}'
                 f'<circle cx="{x:.1f}" cy="{y + 30}" r="44" fill="transparent"/></a>')
    return f'<div class="journey">{svg(p, "".join(b), "The story in six steps", w, h)}</div>'


def icon_mark(kind: str, x: float, y: float, col: str) -> str:
    if kind == "plane":
        return plane(x + 2, y + 2, 0.3, -8, col)
    if kind == "crate":
        return (f'<rect x="{x - 10}" y="{y - 8}" width="20" height="16" fill="none" stroke="{col}" stroke-width="1.6"/>'
                f'<line x1="{x - 10}" y1="{y}" x2="{x + 10}" y2="{y}" stroke="{col}" stroke-width="1.2"/>')
    if kind == "queue":
        return "".join(f'<rect x="{x - 13 + k * 9}" y="{y - 4}" width="7" height="7" fill="{col}" opacity="{.5 + k * .25}"/>' for k in range(3))
    if kind == "flag":
        return (f'<line x1="{x - 7}" y1="{y - 11}" x2="{x - 7}" y2="{y + 11}" stroke="{col}" stroke-width="1.8"/>'
                f'<path d="M{x - 6} {y - 11} L{x + 10} {y - 6} L{x - 6} {y - 1} z" fill="{col}"/>')
    if kind == "clock":
        return (f'<circle cx="{x}" cy="{y}" r="11" fill="none" stroke="{col}" stroke-width="1.6"/>'
                f'<path d="M{x} {y - 7} L{x} {y} L{x + 6} {y + 3}" fill="none" stroke="{col}" stroke-width="1.6"/>')
    return text(x, y + 8, "?", 24, col, "middle", F_NUM)
