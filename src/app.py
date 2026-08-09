"""Multi-market ETF tracker entry point.

Usage:
    streamlit run src/app.py
"""

import streamlit as st

st.set_page_config(page_title="ETF Tracker", layout="wide")

pages = [
    st.Page("pages/home.py", title="Home", icon="🏠", default=True),
    st.Page("pages/india.py", title="India", icon="🇮🇳"),
    st.Page("pages/usa.py", title="USA", icon="🇺🇸"),
    st.Page("pages/usa_ai.py", title="USA - AI", icon="🤖"),
    st.Page("pages/canada.py", title="Canada", icon="🇨🇦"),
]

nav = st.navigation(pages)
nav.run()
