"""
SPM Dashboard — Entry point con autenticazione AD via UYUNI.

Se non autenticato → mostra login form.
Se autenticato → mostra navigazione completa.
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


# ─────────────────────────────────────────────
# LOGIN FORM (se non autenticato)
# ─────────────────────────────────────────────

if not st.session_state.get("authenticated"):
    st.title("🔒 Security Patch Manager")
    st.caption(f"Orchestrator: `{api.base_url()}`")
    st.divider()

    col, _ = st.columns([1, 1])
    with col:
        st.subheader("Accesso")
        username = st.text_input("Username (UPN)", placeholder="nome.cognome@asl06.medus.local")
        password = st.text_input("Password AD", type="password")

        if st.button("▶ Accedi", type="primary", use_container_width=True):
            if not username or not password:
                st.error("Inserisci username e password.")
            else:
                with st.spinner("Autenticazione in corso..."):
                    vdata, verr = api.validate_operator(username, password)

                if verr or not (vdata or {}).get("valid"):
                    st.error("❌ Credenziali non valide o utente non autorizzato in UYUNI.")
                else:
                    # Recupera org dell'utente
                    with st.spinner("Caricamento organizzazione..."):
                        gdata, _ = api.groups_list(username=username, password=password)
                    org = (gdata or {}).get("org", {})

                    st.session_state.authenticated     = True
                    st.session_state.uyuni_username    = username
                    st.session_state.uyuni_password    = password
                    st.session_state.uyuni_org_name    = org.get("org_name", "")
                    st.session_state.uyuni_org_id      = org.get("org_id")
                    st.rerun()
    st.stop()


# ─────────────────────────────────────────────
# SIDEBAR (solo se autenticato)
# ─────────────────────────────────────────────

with st.sidebar:
    st.title("🔒 SPM")
    st.caption(f"API: `{api.base_url()}`")
    st.divider()

    st.caption(f"👤 **{st.session_state.uyuni_username}**")
    if st.session_state.get("uyuni_org_name"):
        st.caption(f"🏢 {st.session_state.uyuni_org_name}")

    if st.button("Logout", use_container_width=True):
        for key in ["authenticated", "uyuni_username", "uyuni_password",
                    "uyuni_org_name", "uyuni_org_id", "active_batch_id"]:
            st.session_state.pop(key, None)
        st.rerun()

    st.divider()


# ─────────────────────────────────────────────
# NAVIGAZIONE (solo se autenticato)
# ─────────────────────────────────────────────

pg = st.navigation([
    st.Page("pages/0_Home.py",          title="Overview",     icon="🏠", default=True),
    st.Page("pages/1_Gruppi_UYUNI.py",  title="Gruppi UYUNI", icon="🖥"),
    st.Page("pages/2_Test_Batch.py",    title="Test Batch",   icon="🧪"),
    st.Page("pages/3_Approvazioni.py",  title="Approvazioni", icon="✅"),
])
pg.run()
