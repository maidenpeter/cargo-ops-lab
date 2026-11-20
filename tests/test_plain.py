"""The plain-language layer: the story, the shipment lookup and the chat all read the stored results correctly."""
import pandas as pd

from lab import ask as A
from lab import config as C
from lab import headline
from lab import shipments as S
from lab import ui


def test_story_follows_its_fixed_rule(results_ready):
    awb_id = S.story_pick()
    sc = S.scores()
    rec = S.record(awb_id)
    assert rec["status"] == "kept" and rec["scored"] and rec["on_time"] is False
    assert rec["flagged"] and sc.loc[awb_id, "late"] == 1
    earlier = sc[(sc["arr_ts"] < sc.loc[awb_id, "arr_ts"]) & (sc["late"] == 1) & (sc["score"] >= S.flag_cut())]
    assert earlier.empty  # nothing earlier meets the rule
    s = headline.read()["story"]  # the README tells the same story from the stored results
    assert s["id"] == awb_id and abs(s["missed_by_min"] + rec["margin_min"]) < 1e-9


def test_shipment_verdicts_match_the_promise(results_ready):
    sla = C.load()["sla_hours"]
    for label, awb_id in S.examples().items():
        rec = S.record(awb_id)
        if rec["status"] != "kept":
            assert rec["status"] == "set_aside" and "set this record aside" in S.verdict(rec)[0]
            continue
        due = rec["arr"] + pd.Timedelta(hours=sla[rec["product"]])
        assert rec["due"] == due
        assert rec["on_time"] == (rec["nfd"] <= due), label
        text = " ".join(S.verdict(rec))
        assert ("kept its promise" in text) == bool(rec["on_time"]), label
    assert S.record("AWB9999999")["status"] == "unknown"
    assert S.find_id("was awb 0192068 late?") == "AWB0192068"


def test_chat_answers_come_from_the_stored_results(results_ready):
    h = headline.read()
    text, page = A.answer("How often is freight on time?")
    assert page == "kpis" and ui.pct(h["nfd_on_time"]) in text
    text, page = A.answer("What happens when the schedule breaks?")
    assert page == "disruption" and ui.pct(h["dis_static"]) in text and ui.pct(h["dis_replanned"]) in text
    text, page = A.answer("What does NFD mean?")
    assert page == "methods" and "notified for delivery" in text
    text, page = A.answer("Was AWB0192068 late?")
    assert page == "legal" and "promise" in text
    text, page = A.answer("Tell me about the weather")
    assert page is None
    for q in A.SUGGESTIONS:
        text, _ = A.answer(q)
        assert text and chr(0x2014) not in text and chr(0x2013) not in text, q
