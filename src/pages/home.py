"""Landing page: pick a market to track."""

import streamlit as st

st.title("ETF Tracker")
st.caption("Pick a market to see its sector ETF performance.")

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.page_link("pages/india.py", label="🇮🇳  India", width="stretch")
    st.caption("Taxonomy chart, sector performance, social-trending ETFs")
with col2:
    st.page_link("pages/usa.py", label="🇺🇸  USA", width="stretch")
    st.caption("SPDR sector ETFs, sector performance, social-trending ETFs")
with col3:
    st.page_link("pages/usa_ai.py", label="🤖  USA - AI", width="stretch")
    st.caption("End-to-end AI value chain: models, robotics, chips, data centers, power")
with col4:
    st.page_link("pages/canada.py", label="🇨🇦  Canada", width="stretch")
    st.caption("TSX sector ETFs, sector performance, social-trending ETFs")
