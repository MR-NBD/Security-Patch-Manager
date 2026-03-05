"""
SPM Dashboard — Auth Guard

Funzione di utilità importata da ogni pagina per bloccare
l'accesso a utenti non autenticati.
"""

import streamlit as st


def require_auth() -> None:
    """Blocca la pagina se l'utente non ha completato il login Azure AD."""
    if not st.session_state.get("authenticated"):
        st.stop()
