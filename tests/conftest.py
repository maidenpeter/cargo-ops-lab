import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lab import config as C  # noqa: E402
from lab import schedule as S  # noqa: E402


@pytest.fixture(scope="session")
def short_arrivals():
    """Three weeks of arrivals from the test months, generated fresh (small enough for quick engine checks)."""
    start = pd.Timestamp("2026-07-01")
    flights = S.build_flights(start - pd.Timedelta(days=9), start + pd.Timedelta(days=21), S.rng_for(91))
    awbs = S.build_awbs(flights, S.rng_for(92))
    return flights, awbs, start, start + pd.Timedelta(days=21)


@pytest.fixture(scope="session")
def results_ready():
    if not (C.DATA / "headline.json").exists():
        pytest.skip("run scripts/build_results.py first")
    return True


@pytest.fixture(scope="session")
def logs_ready(results_ready):
    if not (C.LOGS / "events_wide_truth.parquet").exists():
        pytest.skip("event logs are not committed; run scripts/build_results.py to regenerate them")
    return True
