"""The downloads: the KPI dictionary in Excel beside its CSV, and the shipment file as a page that stands on its own."""
import io
import re
from html.parser import HTMLParser

import pandas as pd

from lab import config as C
from lab import kpis
from lab import shipments as S
from lab import ui


class Page(HTMLParser):
    """The tags and the visible text of a page."""

    def __init__(self, page: str):
        super().__init__()
        self.tags, self.chunks = [], []
        self.feed(page)
        self.text = " ".join(" ".join(self.chunks).split())

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)

    def handle_data(self, data):
        self.chunks.append(data)


def test_kpi_dictionary_excel_holds_what_the_csv_holds(results_ready):
    csv = pd.read_csv(C.DATA / "kpi_dictionary.csv")
    book = io.BytesIO(kpis.dictionary_xlsx(csv))
    pd.testing.assert_frame_equal(pd.read_excel(book, sheet_name="KPI dictionary"), csv, check_dtype=False)


def test_shipment_file_is_a_page_that_needs_nothing_else(results_ready):
    for label, awb_id in S.examples().items():
        rec = S.record(awb_id)
        page = S.file_html(rec)
        p = Page(page)
        assert page.startswith("<!doctype html>") and f"Shipment file: {rec['id']}" in p.text, label
        assert ui.SYNTHETIC in p.text and "not legal advice" in p.text, label
        for line in S.verdict(rec):
            assert line in p.text, label
        for k, v in S.file_facts(rec):
            assert f"{k} {v}" in p.text, label
        assert bool(S.file_facts(rec)) == (rec["status"] == "kept"), label
        # nothing to fetch or run: no scripts, stylesheets, images, frames or addresses
        assert not set(p.tags) & {"script", "link", "img", "iframe", "object", "embed"}, label
        assert not re.search(r"https?:|url\(|@import", page), label


def test_shipment_file_escapes_what_the_reader_typed(results_ready):
    rec = S.record("<script>alert(1)</script>")
    assert rec["status"] == "unknown"
    page = S.file_html(rec)
    assert "<SCRIPT>" not in page and "&lt;SCRIPT&gt;" in page
    assert "script" not in Page(page).tags
