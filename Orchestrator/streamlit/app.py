"""
SPM Dashboard — Entry point con Azure AD SSO (OAuth2/OIDC via MSAL).

Flusso:
  1. Utente non autenticato → bottone "Accedi con Microsoft"
  2. Click → redirect a login.microsoftonline.com (gestito da Microsoft)
  3. Microsoft autentica → redirect a http://10.172.2.22:8501?code=...
  4. App scambia il code con token → legge UPN e nome dall'id_token
  5. Naviga alla dashboard
"""

import sys, os

sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st
import api_client as api
import azure_auth as auth

st.set_page_config(
    page_title="Security Patch Manager",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────
# GESTIONE CALLBACK AZURE AD (code nel query string)
# ─────────────────────────────────────────────

params = st.query_params
if "code" in params and not st.session_state.get("authenticated"):
    code = params["code"]
    st.query_params.clear()  # rimuove ?code= dall'URL

    with st.spinner("Autenticazione in corso..."):
        result = auth.exchange_code(code)

    if "access_token" in result or "id_token_claims" in result:
        user = auth.get_user_info(result)
        st.session_state.authenticated = True
        st.session_state.user_upn = user["upn"]
        st.session_state.user_name = user["display_name"] or user["upn"]
        # Carica org UYUNI (con account admin di servizio)
        gdata, _ = api.groups_list()
        org = (gdata or {}).get("org", {})
        st.session_state.uyuni_org_name = org.get("org_name", "")
        st.rerun()
    else:
        error_desc = result.get(
            "error_description", result.get("error", "Errore sconosciuto")
        )
        st.error(f"Autenticazione fallita: {error_desc}")
        st.stop()


# ─────────────────────────────────────────────
# LOGIN PAGE (se non autenticato)
# ─────────────────────────────────────────────

if not st.session_state.get("authenticated"):
    st.title("Security Patch Manager")
    st.caption(f"Orchestrator: `{api.base_url()}`")
    st.divider()

    col, _ = st.columns([1, 1])
    with col:
        st.subheader("Accesso")

        if not auth.is_configured():
            st.error(
                "Azure AD non configurato. Aggiungi al `.env` del VM:\n\n"
                "```\nAZURE_TENANT_ID=fae8df93-7cf5-40da-b480-f272e15b6242\n"
                "AZURE_CLIENT_ID=<client-id-app-registration-spm>\n"
                "AZURE_CLIENT_SECRET=<client-secret>\n"
                "AZURE_REDIRECT_URI=http://10.172.2.22:8501\n```"
            )
        else:
            auth_url = auth.get_auth_url()
            st.link_button(
                "Accedi con Microsoft",
                auth_url,
                use_container_width=True,
                type="primary",
            )
            st.caption(
                "Il login è gestito da Microsoft — nessuna password viene inserita qui."
            )

    st.stop()


# ─────────────────────────────────────────────
# SIDEBAR (solo se autenticato)
# ─────────────────────────────────────────────

with st.sidebar:
    st.title("SPM")
    st.caption(f"API: `{api.base_url()}`")
    st.divider()

    st.caption(f"👤 **{st.session_state.user_name}**")
    st.caption(f"📧 {st.session_state.user_upn}")
    if st.session_state.get("uyuni_org_name"):
        st.caption(f"🏢 {st.session_state.uyuni_org_name}")

    if st.button("Logout", use_container_width=True):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

    st.divider()


# ─────────────────────────────────────────────
# NAVIGAZIONE (solo se autenticato)
# ─────────────────────────────────────────────

pg = st.navigation(
    [
        st.Page("pages/0_Home.py", title="Overview", icon="🏠", default=True),
        st.Page("pages/1_Gruppi_UYUNI.py", title="Gruppi UYUNI", icon="🖥"),
        st.Page("pages/2_Test_Batch.py", title="Test Batch", icon="🧪"),
        st.Page("pages/3_Approvazioni.py", title="Approvazioni", icon="✅"),
    ]
)
pg.run()
