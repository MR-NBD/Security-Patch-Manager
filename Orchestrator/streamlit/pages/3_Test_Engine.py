"""
SPM Dashboard — Test Engine
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
import pandas as pd
import api_client as api

st.set_page_config(page_title="Test Engine — SPM", page_icon="🧪", layout="wide")

with st.sidebar:
    st.title("🔒 SPM")
    st.caption(f"API: `{api.base_url()}`")
    st.divider()
    st.page_link("app.py",                       label="🏠 Overview")
    st.page_link("pages/1_Coda_Patch.py",        label="📋 Coda Patch")
    st.page_link("pages/2_Approvazioni.py",      label="✅ Approvazioni")
    st.page_link("pages/3_Test_Engine.py",       label="🧪 Test Engine")
    st.page_link("pages/4_Deployments.py",       label="🚀 Deployments")
    st.divider()
    if "operator" not in st.session_state:
        st.session_state.operator = ""
    st.session_state.operator = st.text_input(
        "Operatore", value=st.session_state.operator, placeholder="nome.cognome",
    )

st.title("🧪 Test Engine")

# ── Stato engine ─────────────────────────────────────────────────
ts, err = api.tests_status()
if err:
    st.error(f"Errore API: {err}")
    st.stop()

running = ts.get("engine_running", False)
stats24 = ts.get("stats_24h", {}) or {}
last    = ts.get("last_result")

if running:
    st.info("🔄 **Test in corso** — engine attivo")
else:
    st.success("✅ Engine inattivo — pronto per il prossimo test")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Passati (24h)",     stats24.get("passed_24h", 0))
c2.metric("Falliti (24h)",     stats24.get("failed_24h", 0))
c3.metric("Errori (24h)",      stats24.get("error_24h",  0))
c4.metric("Durata media",      f"{stats24.get('avg_duration_s') or 0}s")

st.divider()

# ── Trigger manuale ───────────────────────────────────────────────
col_btn, col_last = st.columns([1, 3])
with col_btn:
    if st.button("▶ Esegui prossimo test", type="primary",
                 disabled=running, use_container_width=True):
        with st.spinner("Test in corso..."):
            res, e2 = api.tests_run()
        if e2:
            st.error(f"Errore: {e2}")
        else:
            s = res.get("status")
            if s == "skipped":
                st.info(f"Skipped: {res.get('reason')}")
            elif s in ("pending_approval", "passed"):
                st.success(f"Superato — **{res.get('errata_id')}** ({res.get('duration_s','?')}s)")
            elif s in ("failed", "error"):
                st.error(
                    f"Fallito — **{res.get('errata_id')}** "
                    f"| fase: {res.get('failure_phase','?')} "
                    f"| {(res.get('failure_reason') or '')[:80]}"
                )
            st.rerun()

with col_last:
    if last and isinstance(last, dict):
        s    = last.get("status", "?")
        eid  = last.get("errata_id", "?")
        dur  = last.get("duration_s", "?")
        phase = last.get("failure_phase") or ""
        icons = {"pending_approval": "✅", "failed": "❌", "error": "🔥", "skipped": "⏭"}
        st.markdown(
            f"**Ultimo risultato:** {icons.get(s,'ℹ')} **{eid}** → `{s}` ({dur}s)"
            + (f" — fase: `{phase}`" if phase else "")
        )


# ── Test recenti (da coda) ───────────────────────────────────────
st.divider()
st.subheader("Test recenti")

# Leggiamo la coda escludendo i soli 'queued' per vedere quelli già testati
queue_data, qerr = api.queue_list(limit=100)
if qerr:
    st.warning(f"Impossibile caricare: {qerr}")
else:
    all_items = queue_data.get("items", [])
    # Elementi che hanno un test_id (sono stati testati o sono in test)
    tested = [
        it for it in all_items
        if it.get("test_id") and it.get("status") != "queued"
    ]

    if not tested:
        st.info("Nessun test eseguito ancora.")
    else:
        _r_icon = {
            "passed": "✅", "pending_approval": "⏳",
            "failed": "❌", "error": "🔥", "testing": "🔄",
        }
        rows = []
        for it in tested:
            s = it.get("status", "?")
            rows.append({
                "Test ID":    it.get("test_id"),
                "Queue ID":   it.get("queue_id"),
                "Errata":     it.get("errata_id", "?"),
                "OS":         it.get("target_os", "?"),
                "Stato":      f"{_r_icon.get(s,'⬜')} {s}",
                "Score":      it.get("success_score"),
                "Completato": str(it.get("completed_at") or "")[:16].replace("T", " "),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


# ── Dettaglio test per ID ────────────────────────────────────────
st.divider()
st.subheader("Dettaglio test")

test_id_input = st.number_input(
    "Test ID (vedi colonna 'Test ID' sopra)",
    min_value=1, step=1, value=None, placeholder="es. 1"
)

if test_id_input:
    tdata, terr = api.test_detail(int(test_id_input))
    if terr:
        st.error(terr)
    elif tdata:
        d1, d2 = st.columns(2)
        with d1:
            st.markdown(f"**Errata:** {tdata.get('errata_id')}")
            st.markdown(f"**Sistema:** {tdata.get('test_system_name')} ({tdata.get('test_system_ip')})")
            st.markdown(f"**Risultato:** `{tdata.get('result','?')}`")
            st.markdown(f"**Durata:** {tdata.get('duration_seconds','?')}s")
            if tdata.get("failure_reason"):
                st.error(f"**Motivo fallimento:** {tdata.get('failure_reason')}")
                st.markdown(f"**Fase fallita:** `{tdata.get('failure_phase','?')}`")
        with d2:
            st.markdown(f"**Reboot eseguito:** {'Sì' if tdata.get('reboot_performed') else 'No'}")
            st.markdown(f"**Snapshot ID:** {tdata.get('snapshot_id') or '—'}")
            st.markdown(f"**Rollback:** {'Sì' if tdata.get('rollback_performed') else 'No'}")
            started   = str(tdata.get("started_at")   or "")[:16].replace("T", " ")
            completed = str(tdata.get("completed_at") or "")[:16].replace("T", " ")
            st.markdown(f"**Avviato:** {started}  |  **Completato:** {completed}")

        phases = tdata.get("phases", [])
        if phases:
            st.markdown("**Timeline fasi:**")
            ph_icon = {"completed": "✅", "failed": "❌", "skipped": "⏭", "in_progress": "🔄"}
            for ph in phases:
                ico  = ph_icon.get(ph.get("status", ""), "⬜")
                name = ph.get("phase_name", "?")
                dur  = ph.get("duration_seconds")
                err_msg = ph.get("error_message")
                out  = ph.get("output") or {}

                col_n, col_d, col_i = st.columns([2, 1, 5])
                with col_n:
                    st.markdown(f"{ico} **{name}**")
                with col_d:
                    st.caption(f"{dur}s" if dur else "—")
                with col_i:
                    if err_msg:
                        st.caption(f"⚠ {err_msg[:120]}")
                    # Output chiavi rilevanti
                    for k in ("snapshot_id", "count", "reboot_successful", "failed_services"):
                        if k in out:
                            st.caption(f"{k}: {out[k]}")
