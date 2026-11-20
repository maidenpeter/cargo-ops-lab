"""The engine behind Ask the lab.

Without an API key, questions are matched to answers written from the stored results, so every number matches
the pages. With ANTHROPIC_API_KEY in the app's secrets, Claude answers instead, grounded in the same facts and
told to quote no number that is not in them.
"""
from __future__ import annotations

import json
import re

import pandas as pd
import streamlit as st

from lab import config as C
from lab import scenarios as X
from lab import shipments as S
from lab import ui

MODEL = "claude-opus-5-5"
MAX_QUESTIONS = 20        # per visitor session, to keep a public page's API spend bounded
SUGGESTIONS = ["What is this lab?", "How often is freight on time?", "Can the records be trusted?",
               "Can late shipments be spotted early?", "How many staff does each shift need?",
               "What happens when the schedule breaks?", "What can the legal team do with this?",
               "What does NFD mean?", "Is any of this real?"]


def _clean(text: str) -> str:
    """House style: no em or en dashes in anything shown."""
    return text.replace(chr(0x2014), ", ").replace(chr(0x2013), " to ")


@st.cache_data(show_spinner=False)
def _facts(stamp: float) -> dict:
    h = ui.headline()
    cfg = C.load()
    k = ui.table("kpi_summary").set_index("kpi")["value"]
    ver = ui.table("dq_versions").set_index("version")["on_time"]
    sc = ui.table("dq_scorecard")
    sla = cfg["sla_hours"]
    lo, hi = min(sla, key=sla.get), max(sla, key=sla.get)
    top = " and ".join(ui.PRODUCT_NOUNS[x] for x in sla if sla[x] == sla[hi])
    start, cut = pd.Timestamp(cfg["window"]["start"]), pd.Timestamp(cfg["window"]["cutoff"])
    months = (cut.year - start.year) * 12 + cut.month - start.month + 1
    test0 = pd.Timestamp(cfg["split"]["valid_end"]) + pd.Timedelta(days=1)
    dis = ui.table("disruption")
    b0 = dis[(dis["scenario"] == X.key(0.0, 0.0)) & (dis["policy"] == "static")]["late_per_week"].iloc[0]
    b4 = dis[(dis["scenario"] == X.key(h["dis_share"], 0.0)) & (dis["policy"] == "static")]["late_per_week"].iloc[0]
    tr_path = C.DATA / "test_results.csv"
    tr = pd.read_csv(tr_path) if tr_path.exists() else pd.DataFrame(columns=["status"])
    caught = sc["true_pos"].sum() / sc["injected"].sum()
    p = ui.pct
    return {
        "overview": (f"Cargo Ops Lab is a simulated airport cargo terminal at a Gulf hub, built by Marion Peter to show "
                     f"how an analyst would run its numbers. It plays out {months} months of freight, "
                     f"{ui.num(k['awbs_total'])} shipments weighing {ui.num(k['tonnes_total'])} tonnes, and answers five "
                     f"questions: how often freight is ready on time, whether the records can be trusted, whether late "
                     f"shipments can be spotted early, how many staff each shift needs, and what happens when the flight "
                     f"schedule breaks. Every number is illustrative."),
        "measures": (f"{p(h['nfd_on_time'])} of shipments are ready to collect within the promise, counted from the "
                     f"moment the plane lands. The promise depends on the type of cargo, from {sla[lo]} hours for "
                     f"{ui.PRODUCT_NOUNS[lo]} to {sla[hi]} for {top}. The typical "
                     f"shipment takes {h['handler_p50_h']:.1f} hours; the slowest tenth take more than "
                     f"{h['handler_p90_h']:.1f}. Once freight is ready, the waiting belongs to customs and the customer: "
                     f"the terminal accounts for only {p(h['handler_share_of_dwell'])} of the time freight spends at the "
                     f"airport."),
        "data": (f"Not quite as they arrive. A copy of the records was given {len(sc)} kinds of everyday error on "
                 f"purpose, such as times in the wrong time zone and messages sent twice. Taken at face value it says "
                 f"{p(ver['Raw feed'])} of shipments were on time; the truth is {p(ver['Truth'])}. Automatic checks catch "
                 f"{p(caught, 0)} of the errors, and after fixing what is safe and setting the rest aside the figure is "
                 f"{p(ver['Repaired'])}. {h['sentences']['timezone']}"),
        "risk": (f"{h['sentences']['catch']} The early-warning model scores each shipment when its plane lands, using "
                 f"only what is known then, and the biggest warning sign is the queue already waiting. It was tested on "
                 f"{test0:%B} to {cut:%B %Y}, months it never saw while it was built. A real terminal is messier, so "
                 f"expect a real model to catch fewer."),
        "staffing": (f"{h['sentences']['roster']} The recommended roster was found by trying staff levels for each "
                     f"shift in the simulation and weighing wages against late penalties, then testing the whole roster "
                     f"end to end."),
        "disruption": f"{h['sentences']['headline']} {h['sentences']['flex']} {h['sentences']['volume']}",
        "drift": h["sentences"]["drift"],
        "legal": ("The Legal desk page does three things. It looks up any shipment and says in plain words what was "
                  "promised, when the freight was ready, whether the promise was kept and whose clock any delay was on, "
                  "with a file to download. It tests a promise before it goes into a contract: how often it would have "
                  "been kept and what the penalties would cost. And it shows how much lateness a broken schedule "
                  f"causes on its own: with {p(h['dis_share'], 0)} of flights moved, about "
                  f"{p((b4 - b0) / b4, 0)} of late shipments are down to the disruption. It is not legal advice."),
        "synthetic": ("None of it is real. Every flight and shipment comes from one seeded simulation. No terminal, "
                      "airline, airport or system vendor is named: airlines are Carrier A to Carrier T and origins are "
                      "regions. Promises, work rates, costs and penalties are illustrative settings, listed with their "
                      "reasons on the Methods page."),
        "method": (f"A discrete-event simulation in Python (SimPy) plays out every flight and shipment. The measures and "
                   f"the data checks are SQL queries in DuckDB. The early-warning model is gradient boosting from "
                   f"scikit-learn, tested on months it never saw. The roster comes from an integer program (PuLP with "
                   f"the CBC solver) over a grid of simulations, and every roster is re-simulated before it is reported. "
                   f"{int((tr['status'] == 'passed').sum())} of {len(tr)} automated tests pass."),
        "fallback": ("I can answer questions about how often freight is on time, whether the records can be trusted, "
                     "the early-warning model, staffing, what happens when the schedule breaks, what the legal team can "
                     "do with the data, the words the lab uses, or a shipment number such as AWB0192080."),
    }


def facts() -> dict:
    p = C.DATA / "headline.json"
    return _facts(p.stat().st_mtime if p.exists() else 0.0)


# topic: (page it points to, words that suggest it). A trailing * marks a stem; other words match whole.
# Earlier topics win ties, so the specific ones come first.
TOPICS = [
    ("legal", "legal", ["legal", "claim*", "contract*", "penalt*", "liab*", "fault*", "dispute*", "force majeure",
                        "clause*", "lawyer*", "court", "sue", "evidence", "breach*", "attorney*", "counsel"]),
    ("drift", "disruption", ["drift*", "still work*", "still accurate", "hold up"]),
    ("disruption", "disruption", ["disrupt*", "schedule*", "bunch*", "rush hour*", "wave*", "airspace", "break*",
                                  "broken", "on-call", "on call", "call-in", "call in", "re-plan*", "replan*", "crisis"]),
    ("risk", "risk", ["predict*", "model*", "early warning", "early-warning", "risk*", "flag*", "fast-track*",
                      "fast track*", "machine learning", "spot*", "forecast*", "ai"]),
    ("data", "dq", ["trust*", "data", "error*", "quality", "record*", "clean*", "time zone*", "timezone*",
                    "duplicate*", "missing", "wrong", "accurate", "reliable"]),
    ("staffing", "roster", ["staff*", "roster*", "shift*", "people", "hire", "hiring", "crew*", "worker*",
                            "headcount", "wage*", "budget*", "hours a week", "labor", "labour"]),
    ("synthetic", "methods", ["real", "synthetic", "fake", "made up", "invented", "actual compan*", "which airport",
                              "which airline"]),
    ("method", "methods", ["how was", "how did", "built", "method*", "python", "sql", "duckdb", "simpy", "code",
                           "tools", "tested", "tests", "technique*", "assumption*"]),
    ("measures", "kpis", ["on time", "on-time", "how often", "late*", "promise*", "measure*", "kpi*", "performance",
                          "ready", "slow*", "fast", "dwell*", "wait*", "delay*"]),
    ("overview", "terminal", ["what is this", "overview", "this lab", "the lab", "this app", "summary", "summari*",
                              "who built", "marion", "purpose", "hello", "cargo ops", "start"]),
]
# each type of cargo and the words people use for it
CARGO = {"live_animals": ["live animal*", "animal*", "livestock", "pet*"], "pharma": ["pharma*", "medicine*", "drug*", "vaccine*"],
         "express": ["express"], "perishable": ["perishable*", "fresh", "food", "flower*"],
         "dangerous_goods": ["dangerous", "hazard*", "battery", "batteries"], "general": ["general"]}


def _cargo_answer(product: str) -> str:
    by = ui.table("kpi_by")
    on = float(by[(by["dim"] == "Product") & (by["level"] == product)]["value"].iloc[0])
    t = ui.table("handler_time_by_product").set_index("product").loc[product]
    noun = ui.PRODUCT_NOUNS[product]
    text = (f"{noun.capitalize()} have a {int(t['sla_h'])}-hour promise, and {ui.pct(on)} of them are ready to collect "
            f"within it. The typical shipment is ready {t['p50_h']:.1f} hours after landing; the slowest tenth take more "
            f"than {t['p90_h']:.1f}.")
    if t["p90_h"] > t["sla_h"] or on < 0.8:
        text += (f" Getting them off the plane and checked in takes {t['arr_to_rcf_min']:.0f} minutes on average and "
                 f"the paperwork {t['rcf_to_nfd_min']:.0f} more, so the promise itself is the first thing to question.")
    return text
DEFINE = re.compile(r"\b(what is|what's|what are|what does|mean|meaning|define|definition|stand for|stands for)\b")


def _hits(q: str, words: list[str]) -> int:
    n = 0
    for w in words:
        stem = w.endswith("*")
        n += bool(re.search(r"(?<![a-z])" + re.escape(w.rstrip("*")) + ("" if stem else r"(?![a-z])"), q))
    return n


def _term(q: str) -> tuple[str, str, str] | None:
    for term, aka, definition in ui.glossary_terms():
        names = [term.lower()] + [a.strip().lower() for a in (aka or "").split(",")]
        if any(n and re.search(r"(?<![a-z])" + re.escape(n) + r"(?![a-z])", q) for n in names):
            return term, aka, definition
    return None


def answer(question: str) -> tuple[str, str | None]:
    """A plain-English answer from the stored results, and the page it comes from."""
    q = (question or "").lower()
    awb_id = S.find_id(question)
    if awb_id:
        rec = S.record(awb_id)
        return " ".join(S.verdict(rec)), "legal"
    t = _term(q)
    if t and DEFINE.search(q):
        term, aka, definition = t
        return (f"{term}{f' ({aka})' if aka else ''}: {definition}"), "methods"
    f = facts()
    scored = [(_hits(q, words), i) for i, (_, _, words) in enumerate(TOPICS)]
    best, i = max(scored, key=lambda s: (s[0], -s[1]))
    cargo = next((p for p, words in CARGO.items() if _hits(q, words)), None)
    if cargo and (not best or TOPICS[i][0] == "measures"):  # a question about one type of cargo
        return _cargo_answer(cargo), "kpis"
    if best:
        key, page, _ = TOPICS[i]
        return f[key], page
    if t:
        term, aka, definition = t
        return (f"{term}{f' ({aka})' if aka else ''}: {definition}"), "methods"
    return f["fallback"], None


# ---------------------------------------------------------------- Claude, when a key is configured
def api_key() -> str | None:
    try:
        return st.secrets.get("ANTHROPIC_API_KEY") or None
    except Exception:  # no secrets file at all
        return None


def model() -> str:
    try:
        return st.secrets.get("CHAT_MODEL") or MODEL
    except Exception:
        return MODEL


def system_prompt() -> str:
    grounding = {"facts": {k: v for k, v in facts().items() if k != "fallback"},
                 "glossary": [{"term": t, "also_called": a, "meaning": d} for t, a, d in ui.glossary_terms()],
                 "pages": {p["nav"]: p["title"] for p in ui.PAGES}}
    return (
        "You answer visitors' questions about Cargo Ops Lab, a portfolio app by Marion Peter: a simulated (synthetic) "
        "import cargo terminal at a Gulf hub. Many visitors have no cargo or data background, for example someone from "
        "a legal team.\n\n"
        "Rules:\n"
        "- Answer only from the facts below. If they do not cover the question, say so and name the page that comes "
        "closest.\n"
        "- Quote numbers exactly as they appear in the facts. Never estimate, round differently or invent a number.\n"
        "- Write plain English in two to five short sentences unless the visitor asks for more. Explain any technical "
        "word you use.\n"
        "- Everything in the lab is synthetic and illustrative. Never present it as data about a real terminal, airline "
        "or airport, and do not name real companies.\n"
        "- You are not a lawyer. When asked for legal advice, explain what the data shows and say it is not legal advice.\n"
        "- Do not use em dashes or en dashes.\n\n"
        "Facts (JSON):\n" + json.dumps(grounding, indent=1)
    )


def claude_stream(history: list[dict]):
    """Stream Claude's answer to the last question in `history` (alternating user and assistant turns)."""
    import anthropic  # only needed when a key is configured

    msgs = [{"role": m["role"], "content": m["content"]} for m in history[-12:]]
    while msgs and msgs[0]["role"] != "user":
        msgs = msgs[1:]
    awb_id = S.find_id(msgs[-1]["content"])
    if awb_id:  # give Claude the record itself, so it describes the shipment rather than guessing
        msgs[-1] = {"role": "user", "content": msgs[-1]["content"] + "\n\n[The lab's record for " + awb_id + ": "
                    + " ".join(S.verdict(S.record(awb_id))) + "]"}
    client = anthropic.Anthropic(api_key=api_key())
    try:
        with client.beta.messages.stream(
            model=model(),
            max_tokens=2048,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={"effort": "low"},
            cache_control={"type": "ephemeral"},
            system=system_prompt(),
            messages=msgs,
        ) as stream:
            for text in stream.text_stream:
                yield _clean(text)
            final = stream.get_final_message()
            if final.stop_reason == "refusal":
                yield "I can't help with that one. Try a question about the lab, its measures or a shipment."
            elif final.stop_reason == "max_tokens":
                yield " (The answer was cut short; ask for the rest.)"
    except anthropic.RateLimitError:
        yield "The assistant is busy right now. Try again in a minute, or pick one of the suggested questions."
    except anthropic.AuthenticationError:
        yield "The assistant's key is not working, so it cannot answer. The suggested questions still work."
    except anthropic.APIStatusError as e:
        yield f"The assistant could not answer (error {e.status_code}). Try again shortly."
    except anthropic.APIConnectionError:
        yield "The assistant could not be reached. Try again shortly."
