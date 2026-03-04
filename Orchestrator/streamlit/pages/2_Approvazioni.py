"""Pagina sostituita da 3_Approvazioni.py — redirect automatico."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import streamlit as st
st.switch_page("pages/3_Approvazioni.py")
