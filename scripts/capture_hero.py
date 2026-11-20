"""Screenshots for the README: the story, the broken schedule, a shipment file, and a card for every page.

Start the app first (streamlit run app.py), then:

    python scripts/capture_hero.py --base http://localhost:8501

Writes assets/readme/story.webp, schedule.webp, legal.webp and cards/<page>.webp.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from capture import settle  # noqa: E402
from lab.ui import PAGES  # noqa: E402

WIDTH = 1280


def shot(page, path: Path, top: float | None = None, bottom: float | None = None, height: int = 760) -> None:
    """Save a band of the page as WebP: from `top` to `bottom` (page pixels), or the first `height` pixels."""
    h = page.evaluate("() => { const m = document.querySelector('[data-testid=\"stMain\"]');"
                      " return Math.max(m ? m.scrollHeight : 0, document.body.scrollHeight, 900); }")
    page.set_viewport_size({"width": WIDTH, "height": int(h) + 40})  # the app scrolls inside stMain, not the window
    time.sleep(1.2)
    y0 = 0 if top is None else max(0, top)
    y1 = height if bottom is None else bottom
    tmp = path.with_suffix(".png")
    path.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(tmp), clip={"x": 0, "y": y0, "width": WIDTH, "height": y1 - y0})
    Image.open(tmp).convert("RGB").save(path, "WEBP", quality=82, method=6)
    tmp.unlink()
    page.set_viewport_size({"width": WIDTH, "height": 900})


def box(page, selector: str) -> dict:
    """Page position of an element, measured with the page scrolled back to the top (a click can scroll it)."""
    page.evaluate("() => { const m = document.querySelector('[data-testid=\"stMain\"]'); if (m) m.scrollTo(0, 0);"
                  " window.scrollTo(0, 0); }")
    time.sleep(0.5)
    return page.locator(selector).first.bounding_box()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8501")
    ap.add_argument("--out", default=str(ROOT / "assets" / "readme"))
    args = ap.parse_args()
    out = Path(args.out)
    story_id = json.loads((ROOT / "data" / "headline.json").read_text(encoding="utf-8"))["story"]["id"]
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": WIDTH, "height": 900}, device_scale_factor=1)
        page.goto(args.base, wait_until="domcontentloaded")
        settle(page)

        # a card for every page: the top of the page as a visitor first sees it
        for i, pg in enumerate(PAGES):
            page.goto(f"{args.base}/{pg['url'] if i else ''}", wait_until="domcontentloaded")
            settle(page)
            shot(page, out / "cards" / f"{pg['key']}.webp")
            print("card", pg["key"])

        # the story at chapter five, with the timeline filled in
        page.goto(args.base, wait_until="domcontentloaded")
        settle(page)
        for _ in range(4):
            page.get_by_role("button", name="Next").click()
            settle(page)
        page.set_viewport_size({"width": WIDTH, "height": 3000})
        time.sleep(1)
        s = box(page, 'div[class*="st-key-plate-the-story"]')
        shot(page, out / "story.webp", s["y"] - 2, s["y"] + s["height"] + 16)
        print("story")

        # the broken schedule: 40% of flights moved into rush hours, the re-planned roster selected
        page.goto(f"{args.base}/disruption", wait_until="domcontentloaded")
        settle(page)
        thumb = page.locator('[data-testid="stSlider"] input[type="range"]').first
        thumb.focus()
        for _ in range(2):  # 0% -> 20% -> 40%
            page.keyboard.press("ArrowRight")
            settle(page)
        page.locator('[data-testid="stButtonGroup"] button', has_text="Re-planned").first.click()
        settle(page)
        page.set_viewport_size({"width": WIDTH, "height": 4000})
        time.sleep(1)
        top = box(page, 'div.sechead:has-text("Try it")')
        end = box(page, 'div[class*="st-key-plate-four-responses"]')
        shot(page, out / "schedule.webp", top["y"] - 16, end["y"] + end["height"] + 16)
        print("schedule")

        # the Legal desk, looking up the story's shipment
        page.goto(f"{args.base}/legal", wait_until="domcontentloaded")
        settle(page)
        field = page.get_by_label("Or type a shipment number")
        field.fill(story_id)
        field.press("Enter")
        settle(page)
        page.set_viewport_size({"width": WIDTH, "height": 4000})
        time.sleep(1)
        top = box(page, 'div.sechead:has-text("Look up a shipment")')
        end = box(page, 'div[class*="st-key-plate-the-timeline"]')
        shot(page, out / "legal.webp", top["y"] - 16, end["y"] + end["height"] + 70)
        print("legal")
        b.close()


if __name__ == "__main__":
    main()
