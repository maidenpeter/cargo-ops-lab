"""Screenshot every page and report errors. Start the app first (streamlit run app.py), then:

    python scripts/capture.py                       # http://localhost:8501, laptop and phone widths
    python scripts/capture.py --base http://localhost:8601 --out assets/screenshots --widths 1280
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab.ui import PAGES  # noqa: E402

LABEL = "Synthetic terminal. Illustrative only."


def save_webp(page, path: Path) -> None:
    """Full-page screenshot as WebP (the page grain does not compress well as PNG)."""
    tmp = path.with_suffix(".png")
    page.screenshot(path=str(tmp), full_page=True)
    Image.open(tmp).convert("RGB").save(path, "WEBP", quality=80, method=6)
    tmp.unlink()


def settle(page, timeout: float = 90) -> None:
    """Wait until Streamlit has finished running the script and the charts have drawn."""
    page.wait_for_selector(f"text={LABEL}", timeout=timeout * 1000)
    end = time.time() + timeout
    quiet = 0
    while time.time() < end and quiet < 3:
        status = page.query_selector('[data-testid="stStatusWidget"]')
        text = status.inner_text() if status else ""
        busy = ("Stop" in text or "Running" in text or page.query_selector('[data-testid="stSkeleton"]') is not None)
        quiet = 0 if busy else quiet + 1
        time.sleep(0.5)
    time.sleep(2.0)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8501")
    ap.add_argument("--out", default=str(ROOT / "assets" / "screenshots"))
    ap.add_argument("--widths", default="1280,390")
    ap.add_argument("--pages", default="")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    keys = [k for k in args.pages.split(",") if k]
    problems = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        warm = browser.new_page()  # the first session after a server start registers the pages
        warm.goto(args.base, wait_until="domcontentloaded")
        settle(warm)
        warm.close()
        for width in (int(w) for w in args.widths.split(",")):
            ctx = browser.new_context(viewport={"width": width, "height": 900}, device_scale_factor=1)
            page = ctx.new_page()
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            for i, pg in enumerate(PAGES):
                if keys and pg["key"] not in keys:
                    continue
                errors.clear()
                page.set_viewport_size({"width": width, "height": 900})
                page.goto(f"{args.base}/{pg['url'] if i else ''}", wait_until="domcontentloaded")  # the first page lives at /
                settle(page)
                exc = [e.inner_text()[:300] for e in page.query_selector_all('[data-testid="stException"]')]
                overflow = page.evaluate("() => document.documentElement.scrollWidth > window.innerWidth + 1")
                h = page.evaluate("() => { const m = document.querySelector('[data-testid=\"stMain\"]');"
                                  " return Math.max(m ? m.scrollHeight : 0, document.body.scrollHeight); }")
                page.set_viewport_size({"width": width, "height": min(int(h) + 40, 20000)})
                time.sleep(1.5)
                path = out / f"{pg['key']}_{width}.webp"
                save_webp(page, path)
                status = "ok"
                if exc or errors or overflow:
                    status = "PROBLEM"
                    problems.append((pg["key"], width, exc, errors, overflow))
                print(f"{status:7s} {pg['key']:11s} {width}px  height {h}px  -> {path.name}", flush=True)
            ctx.close()
        browser.close()
    for key, width, exc, errors, overflow in problems:
        print(f"\n== {key} at {width}px")
        for e in exc:
            print("  exception:", e.replace("\n", " | "))
        for e in errors:
            print("  page error:", e[:300])
        if overflow:
            print("  horizontal overflow")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
