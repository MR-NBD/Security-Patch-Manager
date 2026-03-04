"""
Deployments — rimosso dal workflow.
La promozione in produzione avviene direttamente tramite UYUNI.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import streamlit as st
import api_client as api

st.set_page_config(page_title="Deployments — SPM", page_icon="🚀", layout="wide")

with st.sidebar:
    st.title("🔒 SPM")
    st.caption(f"API: `{api.base_url()}`")
    st.divider()
    st.page_link("app.py",                        label="🏠 Overview")
    st.page_link("pages/1_Gruppi_UYUNI.py",        label="🖥 Gruppi UYUNI")
    st.page_link("pages/2_Test_Batch.py",          label="🧪 Test Batch")
    st.page_link("pages/3_Approvazioni.py",        label="✅ Approvazioni")

st.title("🚀 Deployments")
st.info(
    "Il deploy in produzione avviene direttamente tramite l'interfaccia web UYUNI, "
    "non tramite SPM. Vai su UYUNI per applicare le patch approvate ai sistemi di produzione.",
    icon="ℹ",
)
st.page_link("pages/3_Approvazioni.py", label="→ Vai alle Approvazioni")
