"""House rules: every assumption is commented, no dashes, no company names, the synthetic label on every page."""
import re

from lab import config as C

TEXT = [p for p in C.ROOT.rglob("*") if p.is_file() and p.suffix in {".py", ".sql", ".md", ".yml", ".toml", ".csv", ".txt"}
        and not any(part in {".venv", ".git", "__pycache__", ".pytest_cache"} for part in p.parts)]
APP = [p for p in TEXT if p.suffix in {".py", ".sql", ".yml", ".toml", ".csv"} and "tests" not in p.parts]
# handlers, airlines, airports, authorities and cargo system vendors that must not appear in the app
NAMES = ["emirates", "dnata", "qatar", "etihad", "flydubai", "saudia", "lufthansa", "cathay", "fedex", "dhl", "ups",
         "swissport", "menzies", "worldwide flight services", "wfs", "dubai airports", "dubai international", "dxb",
         "hamad", "abu dhabi", "sharjah", "champ", "nallian", "ibs software", "hermes"]
DASHES = re.compile("[" + chr(0x2013) + chr(0x2014) + "]")


def test_every_config_value_has_a_comment():
    a = C.assumptions()
    leaves = a[a["value"] != ""]
    assert len(leaves) > 50
    missing = leaves[leaves["note"] == ""]["key"].tolist()
    assert not missing, missing


def test_no_em_or_en_dashes_anywhere():
    bad = [str(p.relative_to(C.ROOT)) for p in TEXT if DASHES.search(p.read_text(encoding="utf-8"))]
    assert not bad, bad


def test_no_company_names_in_the_app():
    hits = []
    for p in APP:
        low = p.read_text(encoding="utf-8").lower()
        hits += [f"{p.name}: {n}" for n in NAMES if re.search(r"\b" + re.escape(n) + r"\b", low)]
    assert not hits, hits


def test_every_page_carries_the_synthetic_label():
    pages = sorted((C.ROOT / "pages").glob("*.py"))
    assert len(pages) == 7
    for p in pages:
        assert "ui.page(" in p.read_text(encoding="utf-8"), p.name
    assert "Synthetic terminal. Illustrative only." in (C.ROOT / "lab" / "ui.py").read_text(encoding="utf-8")
