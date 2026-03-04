"""
SPM Dashboard — Test Engine

Mostra:
  • Stato engine (running/idle)
  • Stats ultime 24h
  • Lista test recenti con risultato
  • Dettaglio test con timeline delle fasi
  • Trigger manuale test
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
import pandas as pd
import api_client as api

st.set_page_config(
    page_title="Test Engine — SPM",
    page_icon="🧪",
    layout="wide",
)

# ── Sidebar ──────────────────────────────────────────────────────
with st.sidebar:
    st.title("🔒 SPM")
    st.caption(f"Orchestrator: `{api.base_url()}`")
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
stats24 = ts.get("stats_24h", {})
last    = ts.get("last_result")

# Status banner
if running:
    st.info("🔄 **Test in corso** — engine attivo")
    if last and last.get("errata_id"):
        st.caption(f"Patch in elaborazione: **{last.get('errata_id')}**")
else:
    st.success("✅ Engine inattivo — pronto per il prossimo test")

# Metriche 24h
c1, c2, c3, c4 = st.columns(4)
c1.metric("Passati (24h)",     stats24.get("passed_24h",   0))
c2.metric("Falliti (24h)",     stats24.get("failed_24h",   0))
c3.metric("Errori (24h)",      stats24.get("error_24h",    0))
c4.metric("Durata media",      f"{stats24.get('avg_duration_s') or 0}s")

st.divider()

# ── Azioni ───────────────────────────────────────────────────────
col_run, col_info = st.columns([1, 3])
with col_run:
    if st.button("▶ Esegui prossimo test", type="primary",
                 disabled=running, use_container_width=True):
        with st.spinner("Test in corso..."):
            res, e2 = api.tests_run()
        if e2:
            st.error(f"Errore: {e2}")
        else:
            status = res.get("status")
            if status == "skipped":
                st.info(f"Skipped: {res.get('reason')}")
            elif status in ("pending_approval", "passed"):
                st.success(
                    f"Test superato — **{res.get('errata_id')}** "
                    f"({res.get('duration_s','?')}s)"
                )
            elif status in ("failed", "error"):
                st.error(
                    f"Fallito — **{res.get('errata_id')}** "
                    f"| fase: {res.get('failure_phase','?')} "
                    f"| {res.get('failure_reason','')[:80]}"
                )
            st.rerun()
with col_info:
    if last:
        r      = last.get("status", "?")
        eid    = last.get("errata_id", "?")
        dur    = last.get("duration_s", "?")
        phase  = last.get("failure_phase") or ""
        rb     = last.get("rollback", False)
        icons  = {"pending_approval": "✅", "failed": "❌", "error": "🔥", "skipped": "⏭"}
        icon   = icons.get(r, "ℹ")
        st.markdown(
            f"**Ultimo risultato:** {icon} **{eid}** → `{r}` "
            f"({dur}s)"
            + (f" | fase: {phase}" if phase else "")
            + (" | rollback: ✅" if rb else "")
        )


# ── Lista test recenti ───────────────────────────────────────────
st.subheader("Test recenti")

# Usiamo GET /api/v1/queue per vedere gli ultimi elementi con test_id
# e poi per ogni test_id mostriamo il dettaglio
# (non c'è un endpoint lista test, ma lo ricaviamo dalla coda)
queue_data, qerr = api.queue_list(limit=50)
if qerr:
    st.warning(f"Impossibile caricare lista test: {qerr}")
else:
    items = queue_data.get("items", []) if isinstance(queue_data, dict) else (queue_data or [])
    tested = [it for it in items if it.get("test_id") and it.get("status") not in ("queued",)]

    if not tested:
        st.info("Nessun test eseguito ancora.")
    else:
        rows = []
        result_icon = {
            "passed":           "✅",
            "pending_approval": "⏳",
            "failed":           "❌",
            "error":            "🔥",
            "testing":          "🔄",
        }
        for it in tested:
            s = it.get("status", "?")
            rows.append({
                "Test ID":   it.get("test_id"),
                "Queue ID":  it.get("id"),
                "Errata":    it.get("errata_id", "?"),
                "OS":        it.get("target_os", "?"),
                "Stato":     f"{result_icon.get(s,'⬜')} {s}",
                "Score":     it.get("success_score"),
                "Completato": (str(it.get("completed_at") or "")[:16]).replace("T", " "),
            })
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)


# ── Dettaglio test ───────────────────────────────────────────────
st.divider()
st.subheader("Dettaglio test")

test_id_input = st.number_input("Test ID", min_value=1, step=1, value=None,
                                 placeholder="Inserisci Test ID...")

if test_id_input:
    tdata, terr = api.test_detail(int(test_id_input))
    if terr:
        st.error(terr)
    elif tdata:
        phases = tdata.get("phases", [])

        d1, d2 = st.columns(2)
        with d1:
            st.markdown(f"**Errata:** {tdata.get('errata_id')}")
            st.markdown(f"**Sistema:** {tdata.get('test_system_name')} ({tdata.get('test_system_ip')})")
            st.markdown(f"**Risultato:** {tdata.get('result','?')}")
            st.markdown(f"**Durata:** {tdata.get('duration_seconds','?')}s")
            if tdata.get("failure_reason"):
                st.markdown(f"**Motivo fallimento:** {tdata.get('failure_reason')}")
                st.markdown(f"**Fase:** {tdata.get('failure_phase','?')}")
        with d2:
            st.markdown(f"**Reboot:** {'Sì' if tdata.get('required_reboot') else 'No'}")
            st.markdown(f"**Snapshot ID:** {tdata.get('snapshot_id') or '—'}")
            st.markdown(f"**Rollback:** {'Sì' if tdata.get('rollback_performed') else 'No'}")
            started = str(tdata.get("started_at") or "")[:16].replace("T", " ")
            completed = str(tdata.get("completed_at") or "")[:16].replace("T", " ")
            st.markdown(f"**Avviato:** {started}")
            st.markdown(f"**Completato:** {completed}")

        if tdata.get("synopsis"):
            st.caption(f"Synopsis: {tdata.get('synopsis')}")

        # ── Timeline fasi ────────────────────────────────────────
        if phases:
            st.markdown("**Timeline fasi:**")
            phase_icons = {
                "completed":   "✅",
                "failed":      "❌",
                "skipped":     "⏭",
                "in_progress": "🔄",
            }
            for ph in phases:
                pname = ph.get("phase_name", "?")
                pstat = ph.get("status", "?")
                pdur  = ph.get("duration_seconds")
                icon  = phase_icons.get(pstat, "⬜")

                col_ph, col_dur, col_err = st.columns([2, 1, 4])
                with col_ph:
                    st.markdown(f"{icon} **{pname}**")
                with col_dur:
                    st.caption(f"{pdur}s" if pdur else "—")
                with col_err:
                    if ph.get("error_message"):
                        st.caption(f"⚠ {ph['error_message'][:100]}")
                    out = ph.get("output")
                    if out and isinstance(out, dict):
                        # Mostra info chiave dall'output
                        for k in ("snapshot_id", "packages_applied", "count",
                                  "reboot_successful", "failed_services"):
                            if k in out:
                                st.caption(f"{k}: {out[k]}")
