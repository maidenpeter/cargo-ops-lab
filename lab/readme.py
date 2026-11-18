"""Renders README.md from docs/README.template.md, filling every number from data/headline.json.

Placeholders look like {{key|format}}: formats are pct (one decimal), pct0, pts, num, num1, hrs, f3, f4 and raw.
Keys can reach into nested values with dots, for example {{sentences.headline|raw}}.
"""
from __future__ import annotations

import re

from lab import config as C

TEMPLATE = C.ROOT / "docs" / "README.template.md"
OUT = C.ROOT / "README.md"

FORMATS = {
    "pct": lambda v: f"{100 * v:.1f}%",
    "pct0": lambda v: f"{100 * v:.0f}%",
    "pts": lambda v: f"{abs(v):.1f} points",
    "num": lambda v: f"{v:,.0f}",
    "num1": lambda v: f"{v:,.1f}",
    "hrs": lambda v: f"{v:.1f} hours",
    "f3": lambda v: f"{v:.3f}",
    "f4": lambda v: f"{v:.4f}",
    "raw": lambda v: str(v),
}


def _get(h: dict, key: str):
    v = h
    for part in key.split("."):
        v = v[part]
    return v


def render(h: dict) -> str:
    text = TEMPLATE.read_text(encoding="utf-8")

    def sub(m: re.Match) -> str:
        key, fmt = m.group(1), (m.group(2) or "raw")
        return FORMATS[fmt](_get(h, key))

    return re.sub(r"\{\{\s*([\w.]+)\s*(?:\|\s*(\w+))?\s*\}\}", sub, text)


def write(h: dict) -> None:
    OUT.write_text(render(h), encoding="utf-8")
