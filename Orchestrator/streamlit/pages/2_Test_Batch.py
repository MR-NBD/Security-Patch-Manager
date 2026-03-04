"""
SPM Dashboard — Test Batch

Avvia un batch di test su patch in coda.
Richiede autenticazione AD con credenziali UYUNI valide.
Le credenziali vengono usate per la sessione UYUNI → audit trail per operatore.
Alla fine dei test viene aggiunta una nota su tutti i sistemi del gruppo.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
import pandas as pd
import api_client as api

st.set_page_config(page_title="Test Batch — SPM", page_icon="🧪", layout="wide")

with st.sidebar:
    st.title("🔒 SPM")
    st.caption(f"API: `{api.base_url()}`")
    st.divider()
    st.page_link("app.py",                        label="🏠 Overview")
    st.page_link("pages/1_Gruppi_UYUNI.py",        label="🖥 Gruppi UYUNI")
    st.page_link("pages/2_Test_Batch.py",          label="🧪 Test Batch")
    st.page_link("pages/3_Approvazioni.py",        label="✅ Approvazioni")
    st.divider()

st.title("🧪 Test Batch")


# ── Stato engine ──────────────────────────────────────────────────
ts, ts_err = api.tests_status()
if ts_err:
    st.error(f"Errore API: {ts_err}")
    st.stop()

running = ts.get("engine_running", False)
if running:
    st.warning("🔄 **Test engine in esecuzione** — attendi il completamento prima di avviare un nuovo batch.")

# ── Selezione patch dalla coda ────────────────────────────────────
st.subheader("Patch in coda (status: queued)")

qdata, qerr = api.queue_list(status="queued", limit=100)
if qerr:
    st.error(f"Errore coda: {qerr}")
    st.stop()

items = (qdata or {}).get("items", [])

if not items:
    st.info("Nessuna patch in coda con status 'queued'. Aggiungile dalla pagina **Gruppi UYUNI**.")
    st.page_link("pages/1_Gruppi_UYUNI.py", label="→ Vai a Gruppi UYUNI")
    st.stop()

# Raggruppa per OS per identificare il gruppo
os_set = set(it.get("target_os", "") for it in items)

# Tabella con selezione
_SEV_ICON = {"Critical": "🔴", "High": "🟠", "Medium": "🟡", "Low": "🔵"}

rows = []
for it in items:
    sev  = it.get("severity") or "?"
    rows.append({
        "Seleziona": False,
        "QID":       it.get("queue_id"),
        "Errata":    it.get("errata_id", "?"),
        "Synopsis":  (it.get("synopsis") or "")[:60],
        "OS":        it.get("target_os", "?"),
        "Severity":  f"{_SEV_ICON.get(sev,'⚪')} {sev}",
        "Score":     it.get("success_score"),
    })

df = pd.DataFrame(rows)
edited = st.data_editor(
    df,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Seleziona": st.column_config.CheckboxColumn("Seleziona", default=False),
        "Score":     st.column_config.ProgressColumn(
            "Score", min_value=0, max_value=100, format="%d"
        ),
    },
    disabled=["QID", "Errata", "Synopsis", "OS", "Severity", "Score"],
    key="queue_selection",
)

selected_rows = edited[edited["Seleziona"] == True]
selected_qids = selected_rows["QID"].tolist()
selected_os   = selected_rows["OS"].unique().tolist() if not selected_rows.empty else []

if selected_qids:
    st.success(f"**{len(selected_qids)}** patch selezionate per il test.")
    if len(selected_os) > 1:
        st.warning(
            f"⚠ Hai selezionato patch per OS diversi: {', '.join(selected_os)}. "
            "I batch dovrebbero essere per un solo OS alla volta."
        )
else:
    st.caption("Seleziona le patch da testare nella colonna 'Seleziona'.")

st.divider()

# ── Selezione gruppo e autenticazione ────────────────────────────
st.subheader("Autenticazione operatore")

st.info(
    "Le tue credenziali AD vengono usate direttamente con UYUNI XML-RPC. "
    "Tutte le azioni (scheduleApplyErrata, scheduleScriptRun, addNote) "
    "risulteranno a tuo nome nel log UYUNI.",
    icon="🔑",
)

# Carica gruppi per la selezione
gdata, gerr = api.groups_list()
groups = (gdata or {}).get("groups", [])
group_names = [g["name"] for g in groups]

col_grp, col_user = st.columns(2)
with col_grp:
    if group_names:
        group_name = st.selectbox("Gruppo UYUNI target", group_names)
    else:
        group_name = st.text_input("Gruppo UYUNI target", placeholder="test-ubuntu-2404")

with col_user:
    username = st.text_input(
        "Username (UPN)",
        placeholder="nome.cognome@asl06.medus.local",
    )

password = st.text_input("Password AD", type="password")

st.divider()

# ── Avvio batch ───────────────────────────────────────────────────
st.subheader("Avvio batch test")

can_run = (
    bool(selected_qids)
    and bool(group_name)
    and bool(username)
    and bool(password)
    and not running
)

if st.button(
    f"▶ Avvia batch ({len(selected_qids)} patch)",
    type="primary",
    disabled=not can_run,
    use_container_width=True,
    help=(
        "Seleziona patch, inserisci credenziali e premi per avviare il test batch."
        if not can_run else ""
    ),
):
    # Step 1: valida credenziali
    with st.spinner("Validazione credenziali..."):
        vdata, verr = api.validate_operator(username, password)

    if verr:
        st.error(f"Errore di connessione: {verr}")
        st.stop()

    if not (vdata or {}).get("valid"):
        st.error(
            "❌ Credenziali non valide o utente non autorizzato in UYUNI. "
            "Verifica username e password AD."
        )
        st.stop()

    st.success(f"✓ Credenziali valide per **{username}**")

    # Step 2: avvia batch (bloccante — può richiedere decine di minuti)
    with st.spinner(
        f"Batch test in corso — {len(selected_qids)} patch... "
        "(questa operazione può richiedere diversi minuti)"
    ):
        result, err = api.run_batch(selected_qids, group_name, username, password)

    if err:
        st.error(f"Errore batch: {err}")
        st.stop()

    # ── Report risultati ──────────────────────────────────────────
    if result:
        passed = result.get("passed", 0)
        failed = result.get("failed", 0)
        total  = result.get("total", 0)

        st.divider()
        st.subheader("📊 Report batch")

        r1, r2, r3 = st.columns(3)
        r1.metric("Totale testati",  total)
        r2.metric("Superati",        passed, delta=passed if passed > 0 else None)
        r3.metric("Falliti / Errori", failed, delta=-failed if failed > 0 else None, delta_color="inverse")

        st.caption(
            f"Gruppo: **{result.get('group')}** | "
            f"Operatore: **{result.get('operator')}**"
        )

        results_list = result.get("results", [])
        if results_list:
            _STATUS_ICON = {
                "pending_approval": "✅",
                "failed":           "❌",
                "error":            "🔥",
                "skipped":          "⏭",
            }
            report_rows = []
            for r in results_list:
                status = r.get("status", "?")
                report_rows.append({
                    "Stato":      f"{_STATUS_ICON.get(status,'⬜')} {status}",
                    "Errata":     r.get("errata_id", "?"),
                    "Durata":     f"{r.get('duration_s','?')}s",
                    "Fase":       r.get("failure_phase") or "—",
                    "Motivo":     (r.get("failure_reason") or "")[:80],
                })
            st.dataframe(pd.DataFrame(report_rows), use_container_width=True, hide_index=True)

        if passed > 0:
            st.info(
                f"**{passed} patch** superano i test e sono in attesa di approvazione. "
                "Vai su **Approvazioni** per approvare o rifiutare.",
                icon="⏳",
            )
            st.page_link("pages/3_Approvazioni.py", label="→ Vai ad Approvazioni")

        st.success(
            "Nota di riepilogo aggiunta su tutti i sistemi UYUNI del gruppo.",
            icon="📝",
        )


# ── Stato corrente test engine ────────────────────────────────────
st.divider()
st.subheader("Stato engine")

stats24 = ts.get("stats_24h", {}) or {}
c1, c2, c3, c4 = st.columns(4)
c1.metric("Passati (24h)",  stats24.get("passed_24h", 0))
c2.metric("Falliti (24h)",  stats24.get("failed_24h", 0))
c3.metric("Errori (24h)",   stats24.get("error_24h", 0))
c4.metric("Durata media",   f"{stats24.get('avg_duration_s') or 0}s")

last = ts.get("last_result")
if last and isinstance(last, dict):
    s   = last.get("status", "?")
    eid = last.get("errata_id", "?")
    dur = last.get("duration_s", "?")
    icons = {"pending_approval": "✅", "failed": "❌", "error": "🔥", "skipped": "⏭"}
    st.caption(
        f"**Ultimo risultato:** {icons.get(s,'ℹ')} **{eid}** → `{s}` ({dur}s)"
    )
