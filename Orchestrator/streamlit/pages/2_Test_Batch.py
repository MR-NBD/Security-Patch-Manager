"""
SPM Dashboard — Test Batch

Avvia un batch di test su patch in coda con autenticazione AD/UYUNI.
Il batch gira in background — la pagina fa polling ogni 5s e mostra
il progresso patch per patch in tempo reale.
"""

import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import re
import time
from collections import Counter
import streamlit as st
import pandas as pd
import api_client as api
import auth_guard
import test_render as tr

auth_guard.require_auth()

st.title("Test Batch")

# ── Famiglie USN ──────────────────────────────────────────────────
# Palette colori pastello per evidenziare righe della stessa famiglia
_FAMILY_COLORS = [
    "#FFF9C4",  # giallo
    "#C8E6FA",  # azzurro
    "#C8F5E4",  # verde
    "#FAD7E6",  # rosa
    "#E8D5FA",  # viola
    "#FFE0B2",  # arancio
    "#B3E5FC",  # ciano
    "#F0F4C3",  # lime
    "#FFDDC1",  # pesca
    "#D7F5D3",  # menta
]


def _advisory_family(name: str):
    """Estrae la famiglia USN. 'USN-7412-2' → 'USN-7412'. None se non USN."""
    m = re.match(r'^(USN-\d+)-\d+$', name)
    return m.group(1) if m else None


def _render_live_test(batch_id: str, current_test_id: int, current_errata_id: str) -> None:
    """
    Sezione 'Patch in esecuzione': mostra in tempo reale fasi, metriche, pipeline.
    """
    st.subheader(f"Patch in esecuzione — `{current_errata_id or '...'}`")

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
    col_elapsed.metric("Tempo trascorso", tr.elapsed(t.get("started_at") or ""))

    st.caption("**Pipeline di esecuzione:**")
    tr.render_pipeline(phases)

    st.divider()

    tab_fasi, tab_prom = st.tabs(["Fasi", "Prometheus"])
    with tab_fasi:
        tr.render_phases_table(phases)
    with tab_prom:
        tr.render_prometheus_section(t)


def _render_completed_results(results: list) -> None:
    """Storico dei test completati nel batch corrente, espandibili."""
    if not results:
        return

    st.subheader(f"Test completati nel batch ({len(results)})")

    _RES_ICON = {
        "pending_approval": "✅",
        "failed":           "❌",
        "error":            "❌",
        "skipped":          "—",
    }

    for r in reversed(results):  # più recente prima
        errata  = r.get("errata_id") or r.get("queue_id", "?")
        status  = r.get("status", "?")
        icon    = _RES_ICON.get(status, "⬜")
        dur     = tr.fmt_duration(r.get("duration_s"))
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
                    c2.metric("Durata",  tr.fmt_duration(t.get("duration_seconds")))
                    c3.metric("Esito",   f"{icon} {status}")

                    tab_f, tab_p = st.tabs(["Fasi", "Prometheus"])
                    with tab_f:
                        tr.render_phases_table(phases)
                    with tab_p:
                        tr.render_prometheus_section(t)

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
        st.success(f"Batch completato — {passed}/{total} patch superate.")
        if passed > 0:
            st.info(f"**{passed} patch** in attesa di approvazione.")
            st.page_link("pages/3_Approvazioni.py", label="→ Vai ad Approvazioni")
        st.info("Nota di riepilogo aggiunta su tutti i sistemi del gruppo UYUNI.")
        if st.button("+ Nuovo batch"):
            del st.session_state["active_batch_id"]
            st.rerun()

    elif batch_status == "cancelled":
        remaining = total - completed
        st.warning(
            f"Batch cancellato. {completed} test eseguiti, {remaining} saltati."
        )
        if passed > 0:
            st.info(f"**{passed} patch** già superate sono in attesa di approvazione.")
            st.page_link("pages/3_Approvazioni.py", label="→ Vai ad Approvazioni")
        if st.button("+ Nuovo batch"):
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

st.caption("Ordine di test: **no-reboot prima** → score → data accodamento")

# ── Rilevamento famiglie USN correlate ───────────────────────────
_fam_counter  = Counter()
_errata_family: dict = {}
for it in items:
    eid = it.get("errata_id", "")
    fam = _advisory_family(eid)
    if fam:
        _errata_family[eid] = fam
        _fam_counter[fam] += 1

# Solo famiglie con più di 1 patch in coda
_multi_families = sorted(f for f, cnt in _fam_counter.items() if cnt > 1)
_fam_color = {
    fam: _FAMILY_COLORS[i % len(_FAMILY_COLORS)]
    for i, fam in enumerate(_multi_families)
}

# ── Legenda + bottoni selezione rapida per famiglia ──────────────
if _multi_families:
    st.caption(
        "Righe dello stesso colore appartengono alla stessa famiglia USN. "
        "Usa i bottoni per selezionarle tutte insieme."
    )
    fam_btn_cols = st.columns(min(len(_multi_families), 4))
    for i, fam in enumerate(_multi_families):
        cnt = _fam_counter[fam]
        with fam_btn_cols[i % len(fam_btn_cols)]:
            if st.button(
                f"{fam} ({cnt})",
                key=f"famsel_{fam}",
                help=f"Aggiunge tutte le patch della famiglia {fam} alla selezione",
            ):
                fam_errata = [
                    it["errata_id"] for it in items
                    if _errata_family.get(it.get("errata_id", "")) == fam
                ]
                current = st.session_state.get("queue_multiselect", [])
                st.session_state["queue_multiselect"] = list(
                    dict.fromkeys(current + fam_errata)
                )
                st.rerun()

# ── Tabella con righe colorate per famiglia ──────────────────────
rows = []
_row_bg: list = []
for it in items:
    eid = it.get("errata_id", "")
    fam = _errata_family.get(eid)
    sev = it.get("severity") or "?"
    rb  = it.get("requires_reboot")
    rb_label = "⚠ Si" if rb is True else ("✅ No" if rb is False else "— ?")
    rows.append({
        "QID":      it.get("queue_id"),
        "Errata":   eid,
        "Famiglia": fam if fam and fam in _fam_color else "",
        "Severity": f"{_SEV_ICON.get(sev, '⚪')} {sev}",
        "Reboot":   rb_label,
        "Score":    it.get("success_score"),
        "Synopsis": (it.get("synopsis") or "")[:55],
    })
    _row_bg.append(_fam_color.get(fam) if fam and fam in _fam_color else None)

_df = pd.DataFrame(rows)


def _apply_row_colors(row):
    bg = _row_bg[row.name]
    return [f"background-color: {bg}" if bg else ""] * len(row)


st.dataframe(
    _df.style.apply(_apply_row_colors, axis=1),
    use_container_width=True,
    hide_index=True,
    column_config={
        "Famiglia": st.column_config.TextColumn("Famiglia", width="medium"),
        "Reboot":   st.column_config.TextColumn("Reboot", width="small"),
        "Score":    st.column_config.ProgressColumn(
            "Score", min_value=0, max_value=100, format="%d"
        ),
    },
)

# ── Selezione patch tramite multiselect ─────────────────────────
errata_options = [it.get("errata_id", "?") for it in items]
selected_errata = st.multiselect(
    "Seleziona patch da testare",
    options=errata_options,
    default=[e for e in st.session_state.get("queue_multiselect", [])
             if e in errata_options],
    key="queue_multiselect",
    placeholder="Cerca advisory per nome o seleziona dalla lista...",
)

_errata_to_qid = {it.get("errata_id"): it.get("queue_id") for it in items}
selected_qids  = [_errata_to_qid[e] for e in selected_errata if e in _errata_to_qid]

if selected_qids:
    # Mostra quante sono correlate tra quelle selezionate
    sel_families = Counter(
        _errata_family[e] for e in selected_errata if e in _errata_family
    )
    multi_sel = {f for f, c in sel_families.items() if c > 1}
    msg = f"**{len(selected_qids)}** patch selezionate"
    if multi_sel:
        msg += f" — di cui {sum(sel_families[f] for f in multi_sel)} correlate " \
               f"in {len(multi_sel)} famiglie"
    st.success(msg)
else:
    st.caption("Seleziona le patch da testare oppure usa i bottoni famiglia.")

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
