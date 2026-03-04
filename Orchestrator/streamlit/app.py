"""
SPM Dashboard — Navigation controller

Usa st.navigation() per registrare esplicitamente le pagine,
disabilitando l'auto-discovery dalla directory pages/.
Questo evita conflitti di URL pathname con le pagine-stub legacy.
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st
import api_client as api

st.set_page_config(
    page_title="SPM — Security Patch Manager",
    page_icon="🔒",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Sidebar comune a tutte le pagine ────────────────────────────
with st.sidebar:
    st.title("🔒 SPM")
    st.caption(f"API: `{api.base_url()}`")
    st.divider()
    if "operator" not in st.session_state:
        st.session_state.operator = ""
    st.session_state.operator = st.text_input(
        "Operatore",
        value=st.session_state.operator,
        placeholder="nome.cognome",
        help="Usato per approvazioni e deployments",
    )
    st.divider()

# ── Registrazione esplicita delle pagine ────────────────────────
pg = st.navigation([
    st.Page("pages/0_Home.py",           title="Overview",      icon="🏠", default=True),
    st.Page("pages/1_Gruppi_UYUNI.py",   title="Gruppi UYUNI",  icon="🖥"),
    st.Page("pages/2_Test_Batch.py",     title="Test Batch",    icon="🧪"),
    st.Page("pages/3_Approvazioni.py",   title="Approvazioni",  icon="✅"),
])
pg.run()
