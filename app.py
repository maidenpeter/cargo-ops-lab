"""Cargo Ops Lab: import cargo terminal analytics on synthetic data. Run with `streamlit run app.py`."""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lab import ui  # noqa: E402

st.set_page_config(page_title=ui.APP, page_icon=str(ui.C.ROOT / "assets" / "seal.svg"), layout="wide",
                   initial_sidebar_state="collapsed")
ui.css()
st.logo(str(ui.C.ROOT / "assets" / "seal.svg"), size="large", link=ui.PORTFOLIO)

pages = [st.Page(p["file"], title=p["nav"], url_path=p["url"], icon=p["icon"], default=(i == 0))
         for i, p in enumerate(ui.PAGES)]
st.navigation(pages, position="top").run()
