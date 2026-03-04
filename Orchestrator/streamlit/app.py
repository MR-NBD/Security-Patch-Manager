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
    st.caption("**Credenziali UYUNI**")
    if "uyuni_username" not in st.session_state:
        st.session_state.uyuni_username = ""
    if "uyuni_password" not in st.session_state:
        st.session_state.uyuni_password = ""
    st.session_state.uyuni_username = st.text_input(
        "Username (UPN)",
        value=st.session_state.uyuni_username,
        placeholder="nome.cognome@asl06.medus.local",
    )
    st.session_state.uyuni_password = st.text_input(
        "Password AD",
        value=st.session_state.uyuni_password,
        type="password",
    )
    if st.session_state.uyuni_username and st.session_state.uyuni_password:
        if "uyuni_org" not in st.session_state:
            st.session_state.uyuni_org = ""
        # Carica org solo se le credenziali sono cambiate
        cred_key = f"{st.session_state.uyuni_username}:{hash(st.session_state.uyuni_password)}"
        if st.session_state.get("_cred_key") != cred_key:
            gdata, _ = api.groups_list(
                username=st.session_state.uyuni_username,
                password=st.session_state.uyuni_password,
            )
            org = (gdata or {}).get("org", {})
            st.session_state.uyuni_org = org.get("org_name", "")
            st.session_state["_cred_key"] = cred_key
        if st.session_state.uyuni_org:
            st.success(f"🏢 {st.session_state.uyuni_org}", icon=None)
    st.divider()

# ── Registrazione esplicita delle pagine ────────────────────────
pg = st.navigation([
    st.Page("pages/0_Home.py",           title="Overview",      icon="🏠", default=True),
    st.Page("pages/1_Gruppi_UYUNI.py",   title="Gruppi UYUNI",  icon="🖥"),
    st.Page("pages/2_Test_Batch.py",     title="Test Batch",    icon="🧪"),
    st.Page("pages/3_Approvazioni.py",   title="Approvazioni",  icon="✅"),
])
pg.run()
