"""Screenshot the hero page in the headline state: 40% of flights moved into waves, the re-planned policy selected.

    python scripts/capture_hero.py --base http://localhost:8501
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from capture import save_webp, settle  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8501")
    ap.add_argument("--out", default=str(ROOT / "assets" / "screenshots" / "disruption_waves_1280.webp"))
    args = ap.parse_args()
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1280, "height": 900})
        page.goto(args.base, wait_until="domcontentloaded")
        settle(page)
        page.goto(f"{args.base}/disruption", wait_until="domcontentloaded")
        settle(page)
        thumb = page.locator('[data-testid="stSlider"] input[type="range"]').first
        thumb.focus()
        for _ in range(2):  # 0% -> 20% -> 40%
            page.keyboard.press("ArrowRight")
            settle(page)
        page.locator('[data-testid="stButtonGroup"] button', has_text="Re-planned").first.click()
        settle(page)
        h = page.evaluate("() => document.querySelector('[data-testid=\"stMain\"]').scrollHeight")
        page.set_viewport_size({"width": 1280, "height": int(h) + 40})
        time.sleep(1.5)
        save_webp(page, Path(args.out))
        print("saved", args.out)
        b.close()


if __name__ == "__main__":
    main()
