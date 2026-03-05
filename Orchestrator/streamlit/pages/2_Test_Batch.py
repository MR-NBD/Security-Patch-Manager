"""
SPM Dashboard — Test Batch

Avvia un batch di test su patch in coda con autenticazione AD/UYUNI.
Il batch gira in background — la pagina fa polling ogni 5s e mostra
il progresso patch per patch in tempo reale.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import time
import streamlit as st
import pandas as pd
import api_client as api
import auth_guard

auth_guard.require_auth()

st.title("🧪 Test Batch")

_STATUS_ICON = {
    "pending_approval": "✅",
    "failed":           "❌",
    "error":            "🔥",
    "skipped":          "⏭",
}


# ─────────────────────────────────────────────────────────────────
# Monitor batch in corso (polling asincrono)
# ─────────────────────────────────────────────────────────────────

def render_monitor(batch_id: str):
    """Mostra progresso batch in tempo reale con auto-refresh ogni 5s."""
    st.subheader(f"🔄 Batch in corso — ID: `{batch_id}`")

    status_data, err = api.batch_status(batch_id)
    if err:
        st.error(f"Errore polling: {err}")
        if st.button("Annulla monitoraggio"):
            del st.session_state["active_batch_id"]
            st.rerun()
        return

    b             = status_data or {}
    batch_status  = b.get("status", "running")
    total         = b.get("total", 0)
    completed     = b.get("completed", 0)
    passed        = b.get("passed", 0)
    failed        = b.get("failed", 0)
    results       = b.get("results", [])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Totale",      total)
    c2.metric("Completati",  f"{completed}/{total}")
    c3.metric("Superati",    passed)
    c4.metric("Falliti",     failed)

    st.caption(
        f"Gruppo: **{b.get('group')}** | Operatore: **{b.get('operator')}** | "
        f"Avviato: {(b.get('started_at') or '')[:16].replace('T',' ')}"
    )

    if total > 0:
        st.progress(completed / total, text=f"{completed}/{total} patch completate")

    if results:
        rows = []
        for r in results:
            s = r.get("status", "?")
            rows.append({
                "Stato":   f"{_STATUS_ICON.get(s,'⬜')} {s}",
                "Errata":  r.get("errata_id", "?"),
                "Durata":  f"{r.get('duration_s','?')}s",
                "Fase":    r.get("failure_phase") or "—",
                "Motivo":  (r.get("failure_reason") or "")[:80],
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    if batch_status == "completed":
        st.success(f"✅ Batch completato — {passed}/{total} patch superate.")
        if passed > 0:
            st.info(f"**{passed} patch** in attesa di approvazione.", icon="⏳")
            st.page_link("pages/3_Approvazioni.py", label="→ Vai ad Approvazioni")
        st.info("Nota di riepilogo aggiunta su tutti i sistemi del gruppo UYUNI.", icon="📝")
        if st.button("✚ Nuovo batch"):
            del st.session_state["active_batch_id"]
            st.rerun()

    elif batch_status == "error":
        st.error(f"❌ Batch fallito: {b.get('error','errore sconosciuto')}")
        if st.button("Chiudi"):
            del st.session_state["active_batch_id"]
            st.rerun()

    else:
        st.info("🔄 Test in corso — aggiornamento automatico ogni 5 secondi...")
        time.sleep(5)
        st.rerun()


# ── Se c'è un batch attivo, mostra solo il monitor ───────────────
if "active_batch_id" in st.session_state:
    render_monitor(st.session_state["active_batch_id"])
    st.stop()


# ─────────────────────────────────────────────────────────────────
# FORM: selezione patch + autenticazione + lancio
# ─────────────────────────────────────────────────────────────────

ts, ts_err = api.tests_status()
if ts_err:
    st.error(f"Errore API: {ts_err}")
    st.stop()

if ts.get("engine_running"):
    st.warning("🔄 Test engine già in esecuzione. Attendi il completamento.")

# ── Patch in coda ─────────────────────────────────────────────────
st.subheader("Patch in coda (status: queued)")

qdata, qerr = api.queue_list(status="queued", limit=100)
if qerr:
    st.error(f"Errore coda: {qerr}")
    st.stop()

items = (qdata or {}).get("items", [])
if not items:
    st.info("Nessuna patch in coda. Aggiungile dalla pagina **Gruppi UYUNI**.")
    st.page_link("pages/1_Gruppi_UYUNI.py", label="→ Vai a Gruppi UYUNI")
    st.stop()

_SEV_ICON = {"Critical": "🔴", "High": "🟠", "Medium": "🟡", "Low": "🔵"}

# Riepilogo reboot prima della tabella
_n_reboot    = sum(1 for it in items if it.get("requires_reboot") is True)
_n_no_reboot = sum(1 for it in items if it.get("requires_reboot") is False)
_n_unknown   = len(items) - _n_reboot - _n_no_reboot

if _n_reboot > 0:
    st.warning(
        f"**{_n_reboot}** patch richiedono riavvio del sistema test — "
        f"**{_n_no_reboot}** applicabili a caldo"
        + (f" — {_n_unknown} non ancora analizzate" if _n_unknown else ""),
        icon="⚠",
    )
else:
    st.info(
        f"Tutte le patch ({_n_no_reboot}) sono applicabili senza riavvio."
        + (f" ({_n_unknown} non ancora analizzate)" if _n_unknown else ""),
        icon="✅",
    )

st.caption("Ordine di test: priorità → **no-reboot prima** → score → data accodamento")

rows = []
for it in items:
    sev = it.get("severity") or "?"
    rb  = it.get("requires_reboot")
    rb_label = "⚠ Si" if rb is True else ("✅ No" if rb is False else "— ?")
    rows.append({
        "Seleziona": False,
        "QID":       it.get("queue_id"),
        "Errata":    it.get("errata_id", "?"),
        "OS":        it.get("target_os", "?"),
        "Severity":  f"{_SEV_ICON.get(sev,'⚪')} {sev}",
        "Reboot":    rb_label,
        "Score":     it.get("success_score"),
        "Synopsis":  (it.get("synopsis") or "")[:55],
    })

edited = st.data_editor(
    pd.DataFrame(rows),
    use_container_width=True,
    hide_index=True,
    column_config={
        "Seleziona": st.column_config.CheckboxColumn("Seleziona", default=False),
        "Reboot":    st.column_config.TextColumn("Reboot", width="small"),
        "Score":     st.column_config.ProgressColumn(
            "Score", min_value=0, max_value=100, format="%d"
        ),
    },
    disabled=["QID", "Errata", "OS", "Severity", "Reboot", "Score", "Synopsis"],
    key="queue_selection",
)

selected_rows = edited[edited["Seleziona"] == True]
selected_qids = selected_rows["QID"].tolist()

if selected_qids:
    st.success(f"**{len(selected_qids)}** patch selezionate.")
else:
    st.caption("Seleziona le patch da testare.")

st.divider()

# ── Avvio batch ───────────────────────────────────────────────────
st.subheader("Avvio")

org_id = st.session_state.get("selected_org_id")
gdata, _ = api.groups_list(org_id)
group_names = [g["name"] for g in (gdata or {}).get("groups", [])]

group_name = (
    st.selectbox("Gruppo UYUNI target", group_names)
    if group_names
    else st.text_input("Gruppo UYUNI target", placeholder="test-ubuntu-2404")
)

# Operatore = utente autenticato via Azure AD
operator = st.session_state.get("user_upn", "")
st.info(
    f"Operazione avviata da **{st.session_state.get('user_name', operator)}** "
    f"({operator}) — registrato nel log SPM.",
    icon="🔑",
)

can_run = (
    bool(selected_qids) and bool(group_name)
    and not ts.get("engine_running")
)

if st.button(
    f"▶ Avvia batch ({len(selected_qids)} patch)",
    type="primary",
    disabled=not can_run,
    use_container_width=True,
):
    with st.spinner("Avvio batch..."):
        bdata, berr = api.start_batch(selected_qids, group_name, operator)

    if berr:
        st.error(f"Errore avvio batch: {berr}")
        st.stop()

    bid = (bdata or {}).get("batch_id")
    if bid:
        st.session_state["active_batch_id"] = bid
        st.rerun()
    else:
        st.error((bdata or {}).get("error", "Errore sconosciuto nell'avvio"))
