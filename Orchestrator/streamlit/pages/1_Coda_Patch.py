"""
SPM Dashboard — Coda Patch
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
import pandas as pd
import api_client as api

st.set_page_config(page_title="Coda Patch — SPM", page_icon="📋", layout="wide")

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

st.title("📋 Coda Patch")

# ── Filtri ───────────────────────────────────────────────────────
with st.expander("Filtri", expanded=True):
    fc1, fc2, fc3, fc4 = st.columns(4)
    with fc1:
        f_status = st.selectbox("Status", [
            "", "queued", "testing", "passed", "pending_approval",
            "approved", "failed", "rejected", "snoozed", "completed",
        ])
    with fc2:
        f_os = st.selectbox("OS", ["", "ubuntu", "rhel"])
    with fc3:
        f_sev = st.selectbox("Severity", ["", "Critical", "High", "Medium", "Low"])
    with fc4:
        f_limit = st.number_input("Righe", min_value=10, max_value=200, value=100, step=10)

# ── Carica dati ──────────────────────────────────────────────────
data, err = api.queue_list(
    status=f_status or None,
    target_os=f_os or None,
    severity=f_sev or None,
    limit=f_limit,
)

if err:
    st.error(f"Errore API: {err}")
    st.stop()

# queue_list ritorna {"total": N, "limit": N, "offset": N, "items": [...]}
items = data.get("items", [])
total = data.get("total", 0)

st.caption(f"**{total}** elementi totali, mostrati **{len(items)}**")

_SEV_ICON = {"Critical": "🔴", "High": "🟠", "Medium": "🟡", "Low": "🔵"}
_STAT_ICON = {
    "queued": "⬜", "testing": "🔄", "passed": "✅",
    "pending_approval": "⏳", "approved": "✅",
    "failed": "❌", "rejected": "🚫", "snoozed": "💤",
    "completed": "🏁", "rolled_back": "↩",
}

if not items:
    st.info("Nessuna patch in coda con questi filtri.")
else:
    rows = []
    for it in items:
        sev  = it.get("severity") or "?"
        stat = it.get("status") or "?"
        rows.append({
            "ID":         it.get("queue_id"),       # chiave corretta: queue_id
            "Errata":     it.get("errata_id", "?"),
            "Synopsis":   (it.get("synopsis") or "")[:60],
            "OS":         it.get("target_os", "?"),
            "Severity":   f"{_SEV_ICON.get(sev,'⚪')} {sev}",
            "Score":      it.get("success_score"),
            "Status":     f"{_STAT_ICON.get(stat,'⬜')} {stat}",
            "Priorità":   it.get("priority_override", 0),
            "Creato da":  it.get("created_by") or "",
            "In coda da": str(it.get("queued_at") or "")[:16].replace("T", " "),
        })
    df = pd.DataFrame(rows)
    st.dataframe(
        df, use_container_width=True, hide_index=True,
        column_config={"Score": st.column_config.ProgressColumn(
            "Score", min_value=0, max_value=100, format="%d"
        )},
    )

    # ── Dettaglio + rimozione ────────────────────────────────────
    st.divider()
    st.subheader("Dettaglio elemento")
    sel_id = st.number_input("ID elemento (colonna ID nella tabella)", min_value=1,
                              step=1, value=None, placeholder="es. 42")
    if sel_id:
        detail, derr = api.queue_item(int(sel_id))
        if derr:
            st.error(derr)
        elif detail:
            d1, d2 = st.columns(2)
            with d1:
                st.write(f"**Errata:** {detail.get('errata_id')}")
                st.write(f"**Status:** {detail.get('status')}")
                st.write(f"**Severity:** {detail.get('severity')}")
                st.write(f"**OS:** {detail.get('target_os')}")
                st.write(f"**Score:** {detail.get('success_score')}")
                st.write(f"**Reboot richiesto:** {'Sì' if detail.get('requires_reboot') else 'No'}")
                st.write(f"**Patch kernel:** {'Sì' if detail.get('affects_kernel') else 'No'}")
            with d2:
                st.write(f"**Synopsis:** {detail.get('synopsis') or '—'}")
                cves = detail.get("cves") or []
                if cves:
                    cve_str = ", ".join(cves[:6]) + (f" +{len(cves)-6}" if len(cves) > 6 else "")
                    st.write(f"**CVE:** {cve_str}")
                pkgs = detail.get("packages") or []
                if pkgs:
                    st.write(f"**Pacchetti:** {len(pkgs)}")
                if detail.get("notes"):
                    st.write(f"**Note:** {detail['notes']}")

            if detail.get("status") == "queued":
                if st.button(f"🗑 Rimuovi ID {sel_id} dalla coda", type="secondary"):
                    res, e2 = api.queue_remove(int(sel_id))
                    if e2:
                        st.error(e2)
                    else:
                        st.success("Rimosso dalla coda.")
                        st.rerun()


# ── Aggiungi patch ───────────────────────────────────────────────
st.divider()
st.subheader("Aggiungi patch in coda")

with st.form("add_queue"):
    ac1, ac2, ac3 = st.columns(3)
    with ac1:
        new_errata = st.text_input("Errata ID *", placeholder="es. USN-7412-2")
    with ac2:
        new_os = st.selectbox("OS *", ["ubuntu", "rhel"])
    with ac3:
        new_prio = st.number_input("Priorità", min_value=0, max_value=10, value=0)

    nc1, nc2 = st.columns(2)
    with nc1:
        new_by = st.text_input("Creato da",
                               value=st.session_state.get("operator", ""),
                               placeholder="nome.cognome")
    with nc2:
        new_notes = st.text_input("Note", placeholder="opzionale")

    if st.form_submit_button("➕ Aggiungi", type="primary", use_container_width=True):
        if not new_errata.strip():
            st.error("Errata ID obbligatorio")
        else:
            res, e2 = api.queue_add(
                errata_id=new_errata.strip(),
                target_os=new_os,
                priority_override=new_prio,
                created_by=new_by.strip() or None,
                notes=new_notes.strip() or None,
            )
            if e2:
                st.error(f"Errore: {e2}")
            else:
                queued = res.get("queued", [])
                errors = res.get("errors", [])
                for q in queued:
                    st.success(
                        f"Aggiunto: **{q.get('errata_id')}** "
                        f"(ID: {q.get('id')}, score: {q.get('success_score')})"
                    )
                for e3 in errors:
                    st.error(f"{e3.get('errata_id')}: {e3.get('error')}")
                if queued:
                    st.rerun()
