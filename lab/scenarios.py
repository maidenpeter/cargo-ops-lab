"""Disruption scenario names and keys. Kept apart from the simulation so the app can read results without the solver."""
from __future__ import annotations

import itertools

from lab import config as C

POLICIES = {
    "legacy": "Legacy roster",
    "static": "Optimized on the normal timetable",
    "replanned": "Re-planned on the disrupted schedule",
    "flex": "Normal-timetable roster plus call-in pool",
}


def scenarios() -> list[tuple[float, float]]:
    d = C.load()["disruption"]
    return list(itertools.product(d["rescheduled_shares"], d["volume_changes"]))


def key(share: float, vol: float) -> str:
    return f"s{round(share * 100):02d}_v{round(-vol * 100):02d}"
