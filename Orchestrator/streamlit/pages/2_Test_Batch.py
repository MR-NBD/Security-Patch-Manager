"""
SPM Dashboard — Test Batch

Avvia un batch di test su patch in coda con autenticazione AD/UYUNI.
Il batch gira in background — la pagina fa polling ogni 5s e mostra
il progresso patch per patch in tempo reale.
"""

import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import time
from datetime import datetime, timezone
import streamlit as st
import pandas as pd
import api_client as api
import auth_guard

auth_guard.require_auth()

st.title("Test Batch")

# ─────────────────────────────────────────────────────────────────
# Helpers rendering fasi
# ─────────────────────────────────────────────────────────────────

_PHASE_ICON = {
    "completed":   "✅",
    "failed":      "❌",
    "skipped":     "⏭",
    "in_progress": "⏳",
}

_PHASE_LABEL = {
    "pre_check":    "⓪ Pre-check",
    "snapshot":     "① Snapshot",
    "patch":        "② Patch",
    "reboot":       "③ Reboot",
    "validate":     "④ Validate (Prometheus)",
    "services":     "⑤ Service check",
    "rollback":     "↩ Rollback",
    "post_rollback": "↩✓ Post-rollback verify",
}

_PIPELINE_STEPS = [
    "pre_check", "snapshot", "patch", "reboot",
    "validate", "services",
]


def _elapsed(iso_start: str) -> str:
    """Calcola tempo trascorso da un timestamp ISO."""
    try:
        start = datetime.fromisoformat(iso_start.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - start
        s = int(delta.total_seconds())
        if s < 60:
            return f"{s}s"
        return f"{s // 60}m {s % 60}s"
    except Exception:
        return "?"


def _fmt_duration(seconds) -> str:
    if seconds is None:
        return "—"
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    return f"{s // 60}m {s % 60}s"


def _phase_detail(phase: dict) -> str:
    """Estrae stringa di dettaglio leggibile dall'output JSON della fase."""
    name   = phase.get("phase_name", "")
    output = phase.get("output") or {}
    err    = phase.get("error_message") or ""

    if name == "pre_check":
        disk  = output.get("disk_available_mb")
        svcs  = output.get("failed_services") or []
        rpend = output.get("reboot_pending")
        parts = []
        if disk is not None:
            parts.append(f"Disco: {disk} MB liberi")
        parts.append("Servizi OK" if not svcs else f"Servizi KO: {', '.join(svcs)}")
        if rpend:
            parts.append("⚠ Reboot pendente")
        return " | ".join(parts) if parts else err

    if name == "snapshot":
        snap = output.get("snapshot_id")
        return f"Snapshot ID: **{snap}**" if snap else err

    if name == "patch":
        count = output.get("count")
        return f"{count} pacchetti applicati" if count is not None else err

    if name == "reboot":
        return "Reboot eseguito, sistema tornato online" if not err else err

    if name == "validate":
        if output.get("skipped"):
            return "⏭ Prometheus non disponibile — validazione saltata"
        cd  = output.get("cpu_delta")
        md  = output.get("memory_delta")
        cok = output.get("cpu_ok")
        mok = output.get("memory_ok")
        parts = []
        if cd is not None:
            icon = "✅" if cok else "❌"
            parts.append(f"CPU Δ={cd:+.1f}% {icon}")
        if md is not None:
            icon = "✅" if mok else "❌"
            parts.append(f"MEM Δ={md:+.1f}% {icon}")
        return " | ".join(parts) if parts else err

    if name == "services":
        checked = output.get("checked") or []
        failed  = output.get("failed")  or []
        if not failed:
            return f"Tutti OK ({len(checked)} servizi controllati)"
        return f"❌ DOWN: {', '.join(failed)}"

    if name == "rollback":
        rtype = output.get("rollback_type", "?")
        snap  = output.get("snapshot_id")
        base  = f"Rollback tipo: **{rtype}**"
        return f"{base} | Snapshot ID: {snap}" if snap else base

    if name == "post_rollback":
        ok = output.get("rollback_verified")
        if ok:
            return "Servizi verificati OK dopo rollback"
        failed = output.get("failed_services") or []
        return f"❌ Servizi ancora DOWN: {', '.join(failed)}" if failed else err

    return err or "—"


def _render_pipeline(phases: list) -> None:
    """Mostra la pipeline di esecuzione come riga di badge colorati."""
    phase_map = {p["phase_name"]: p for p in phases}
    cols = st.columns(len(_PIPELINE_STEPS) + 2)  # +2 per rollback e esito finale

    step_cols = _PIPELINE_STEPS[:]

    for i, step in enumerate(step_cols):
        p = phase_map.get(step)
        if not p:
            label = _PHASE_LABEL.get(step, step).split(" ", 1)[-1]
            cols[i].markdown(f"⬜ *{label}*")
        else:
            status = p.get("status", "")
            icon   = _PHASE_ICON.get(status, "⬜")
            label  = _PHASE_LABEL.get(step, step).split(" ", 1)[-1]
            cols[i].markdown(f"{icon} **{label}**")

    # Rollback (opzionale)
    rb = phase_map.get("rollback")
    if rb:
        icon = _PHASE_ICON.get(rb["status"], "⬜")
        cols[-2].markdown(f"{icon} **Rollback**")
    else:
        cols[-2].markdown("⬜ *Rollback*")

    # Esito finale
    all_done = all(
        phase_map.get(s, {}).get("status") in ("completed", "skipped")
        for s in _PIPELINE_STEPS
        if s in phase_map or s not in ("reboot", "rollback")
    )
    if rb:
        cols[-1].markdown("❌ **Fallita**")
    elif all_done and phase_map:
        cols[-1].markdown("✅ **pending_approval**")
    else:
        cols[-1].markdown("⬜ *Esito*")


def _render_prometheus_section(test: dict) -> None:
    """Mostra sezione metriche Prometheus con baseline, post-patch e delta."""
    baseline = test.get("baseline_metrics") or {}
    post     = test.get("post_patch_metrics") or {}
    delta    = test.get("metrics_delta") or {}
    evalu    = test.get("metrics_evaluation") or {}

    if not baseline.get("available") and not post.get("available"):
        st.caption("Prometheus non disponibile per questo test.")
        return

    cpu_base = baseline.get("cpu_percent")
    mem_base = baseline.get("memory_percent")
    cpu_post = post.get("cpu_percent")
    mem_post = post.get("memory_percent")
    cpu_d    = delta.get("cpu_delta")
    mem_d    = delta.get("memory_delta")
    cpu_ok   = evalu.get("cpu_ok")
    mem_ok   = evalu.get("memory_ok")

    def _fmt(v):
        return f"{v:.1f}%" if v is not None else "—"

    def _fmt_delta(v, ok):
        if v is None:
            return "—"
        icon = "✅" if ok else ("❌" if ok is False else "")
        return f"{v:+.1f}% {icon}"

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("CPU baseline",  _fmt(cpu_base))
    c2.metric("CPU post-patch", _fmt(cpu_post),
              delta=_fmt_delta(cpu_d, cpu_ok),
              delta_color="inverse" if cpu_ok is False else "normal")
    c3.metric("MEM baseline",  _fmt(mem_base))
    c4.metric("MEM post-patch", _fmt(mem_post),
              delta=_fmt_delta(mem_d, mem_ok),
              delta_color="inverse" if mem_ok is False else "normal")

    if evalu.get("skipped"):
        st.caption("⏭ Validazione Prometheus saltata (dati non disponibili al momento del test).")


def _render_phases_table(phases: list) -> None:
    """Tabella dettagliata di tutte le fasi."""
    if not phases:
        st.caption("Nessuna fase registrata.")
        return

    rows = []
    for p in phases:
        name   = p.get("phase_name", "?")
        status = p.get("status", "?")
        icon   = _PHASE_ICON.get(status, "⬜")
        dur    = _fmt_duration(p.get("duration_seconds"))
        detail = _phase_detail(p)
        started = (p.get("started_at") or "")[:19].replace("T", " ")
        rows.append({
            "Fase":    _PHASE_LABEL.get(name, name),
            "Stato":   f"{icon} {status}",
            "Inizio":  started,
            "Durata":  dur,
            "Dettaglio": detail,
        })

    st.dataframe(
        pd.DataFrame(rows),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Dettaglio": st.column_config.TextColumn("Dettaglio", width="large"),
        },
    )


def _render_live_test(batch_id: str, current_test_id: int, current_errata_id: str) -> None:
    """
    Sezione 'Patch in esecuzione': mostra in tempo reale fasi, metriche, pipeline.
    """
    st.subheader(f"⚙ Patch in esecuzione — `{current_errata_id or '...'}`")

    test_data, terr = api.test_detail(current_test_id)
    if terr or not test_data:
        st.info("Caricamento dati test in corso...")
        return

    t = test_data
    phases = t.get("phases") or []

    col_sys, col_os, col_snap, col_elapsed = st.columns(4)
    col_sys.metric("Sistema", t.get("test_system_name") or t.get("test_system_ip") or "?")
    col_os.metric("OS", (t.get("target_os") or "?").upper())
    snap_type = t.get("snapshot_type") or "—"
    snap_id   = t.get("snapshot_id")
    col_snap.metric("Snapshot", f"#{snap_id}" if snap_id else snap_type)
    col_elapsed.metric("Tempo trascorso", _elapsed(t.get("started_at") or ""))

    st.caption("**Pipeline di esecuzione:**")
    _render_pipeline(phases)

    st.divider()

    tab_fasi, tab_prom = st.tabs(["📋 Fasi", "📊 Prometheus"])
    with tab_fasi:
        _render_phases_table(phases)
    with tab_prom:
        _render_prometheus_section(t)


def _render_completed_results(results: list) -> None:
    """Storico dei test completati nel batch corrente, espandibili."""
    if not results:
        return

    st.subheader(f"📜 Test completati nel batch ({len(results)})")

    _RES_ICON = {
        "pending_approval": "✅",
        "failed":           "❌",
        "error":            "🔴",
        "skipped":          "⏭",
    }

    for r in reversed(results):  # più recente prima
        errata  = r.get("errata_id") or r.get("queue_id", "?")
        status  = r.get("status", "?")
        icon    = _RES_ICON.get(status, "⬜")
        dur     = _fmt_duration(r.get("duration_s"))
        phase   = r.get("failure_phase") or "—"
        test_id = r.get("test_id")

        label = f"{icon} **{errata}** — {status} — {dur}"
        if status in ("failed", "error"):
            label += f" — Fase: {phase}"

        with st.expander(label, expanded=False):
            if test_id:
                test_data, terr = api.test_detail(test_id)
                if terr or not test_data:
                    st.caption("Dati non disponibili.")
                else:
                    t      = test_data
                    phases = t.get("phases") or []

                    c1, c2, c3 = st.columns(3)
                    c1.metric("Sistema", t.get("test_system_name") or "?")
                    c2.metric("Durata",  _fmt_duration(t.get("duration_seconds")))
                    c3.metric("Esito",   f"{icon} {status}")

                    tab_f, tab_p = st.tabs(["📋 Fasi", "📊 Prometheus"])
                    with tab_f:
                        _render_phases_table(phases)
                    with tab_p:
                        _render_prometheus_section(t)

                    if r.get("failure_reason"):
                        st.error(f"**Motivo fallimento:** {r['failure_reason']}")
            else:
                reason = r.get("reason") or r.get("failure_reason") or "—"
                st.caption(f"Motivo: {reason}")


# ─────────────────────────────────────────────────────────────────
# Monitor batch in corso (polling asincrono)
# ─────────────────────────────────────────────────────────────────

def render_monitor(batch_id: str):
    """Mostra progresso batch in tempo reale con auto-refresh ogni 5s."""
    status_data, err = api.batch_status(batch_id)
    if err:
        st.error(f"Errore polling: {err}")
        if st.button("Annulla monitoraggio"):
            del st.session_state["active_batch_id"]
            st.rerun()
        return

    b = status_data or {}
    batch_status    = b.get("status", "running")
    total           = b.get("total", 0)
    completed       = b.get("completed", 0)
    passed          = b.get("passed", 0)
    failed          = b.get("failed", 0)
    results         = b.get("results", [])
    current_test_id = b.get("current_test_id")
    current_errata  = b.get("current_errata_id")

    # ── Intestazione batch ─────────────────────────────────────────
    st.subheader(f"Batch `{batch_id}` — {batch_status.upper()}")
    st.caption(
        f"Gruppo: **{b.get('group')}** | Operatore: **{b.get('operator')}** | "
        f"Avviato: {(b.get('started_at') or '')[:16].replace('T', ' ')}"
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Totale",     total)
    c2.metric("Completati", f"{completed}/{total}")
    c3.metric("Superati",   passed)
    c4.metric("Falliti",    failed)

    if total > 0:
        st.progress(completed / total, text=f"{completed}/{total} patch completate")

    st.divider()

    # ── Patch in esecuzione (solo durante il batch) ────────────────
    if batch_status == "running" and current_test_id:
        _render_live_test(batch_id, current_test_id, current_errata)
        st.divider()

    # ── Test completati nel batch ──────────────────────────────────
    _render_completed_results(results)

    # ── Stato finale ───────────────────────────────────────────────
    if batch_status == "completed":
        st.success(f"✅ Batch completato — {passed}/{total} patch superate.")
        if passed > 0:
            st.info(f"**{passed} patch** in attesa di approvazione.", icon="⏳")
            st.page_link("pages/3_Approvazioni.py", label="→ Vai ad Approvazioni")
        st.info("Nota di riepilogo aggiunta su tutti i sistemi del gruppo UYUNI.", icon="📝")
        if st.button("✚ Nuovo batch"):
            del st.session_state["active_batch_id"]
            st.rerun()

    elif batch_status == "cancelled":
        remaining = total - completed
        st.warning(
            f"Batch cancellato. {completed} test eseguiti, {remaining} saltati."
        )
        if passed > 0:
            st.info(f"**{passed} patch** già superate sono in attesa di approvazione.", icon="⏳")
            st.page_link("pages/3_Approvazioni.py", label="→ Vai ad Approvazioni")
        if st.button("✚ Nuovo batch"):
            del st.session_state["active_batch_id"]
            st.rerun()

    elif batch_status == "error":
        st.error(f"❌ Batch fallito: {b.get('error', 'errore sconosciuto')}")
        if st.button("Chiudi"):
            del st.session_state["active_batch_id"]
            st.rerun()

    else:
        # Batch in corso: auto-refresh + pulsante annulla
        col_info, col_cancel = st.columns([4, 1])
        with col_info:
            st.info("Test in corso — aggiornamento automatico ogni 5 secondi...")
        with col_cancel:
            if st.button("⏹ Annulla batch", type="secondary"):
                _, cerr = api.batch_cancel(batch_id)
                if cerr:
                    st.error(f"Errore cancellazione: {cerr}")
                else:
                    st.warning("Cancellazione richiesta, il test corrente verrà completato.")
        time.sleep(5)
        st.rerun()


# ── Se c'è un batch attivo, mostra solo il monitor ───────────────
if "active_batch_id" in st.session_state:
    render_monitor(st.session_state["active_batch_id"])
    st.stop()


# ─────────────────────────────────────────────────────────────────
# FORM: selezione patch + lancio
# ─────────────────────────────────────────────────────────────────

ts, ts_err = api.tests_status()
if ts_err:
    st.error(f"Errore API: {ts_err}")
    st.stop()

if ts.get("engine_running"):
    st.warning("Test engine già in esecuzione. Attendi il completamento.")

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

_n_reboot   = sum(1 for it in items if it.get("requires_reboot") is True)
_n_no_reboot = sum(1 for it in items if it.get("requires_reboot") is False)
_n_unknown  = len(items) - _n_reboot - _n_no_reboot

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

st.caption("Ordine di test: **no-reboot prima** → score → data accodamento")

rows = []
for it in items:
    sev = it.get("severity") or "?"
    rb  = it.get("requires_reboot")
    rb_label = "⚠ Si" if rb is True else ("✅ No" if rb is False else "— ?")
    rows.append({
        "Seleziona": False,
        "QID":      it.get("queue_id"),
        "Errata":   it.get("errata_id", "?"),
        "OS":       it.get("target_os", "?"),
        "Severity": f"{_SEV_ICON.get(sev, '⚪')} {sev}",
        "Reboot":   rb_label,
        "Score":    it.get("success_score"),
        "Synopsis": (it.get("synopsis") or "")[:55],
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

operator = st.session_state.get("user_upn", "")
st.info(
    f"Operazione avviata da **{st.session_state.get('user_name', operator)}** "
    f"({operator}) — registrato nel log SPM.",
    icon="🔑",
)

can_run = bool(selected_qids) and bool(group_name) and not ts.get("engine_running")

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
