"""
SPM Dashboard — Overview (Home)

Mostra:
  • Stato sistema (health componenti)
  • Notifiche non lette
  • Statistiche coda e sync UYUNI
  • Stats test ultime 24h
  • Azioni rapide: trigger sync, trigger test
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st
import api_client as api

st.set_page_config(
    page_title="SPM — Security Patch Manager",
    page_icon="🔒",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Stili ────────────────────────────────────────────────────────
st.markdown("""
<style>
.metric-card {
    background: #1e1e2e;
    border-radius: 8px;
    padding: 16px;
    text-align: center;
}
.status-ok    { color: #4ade80; font-weight: bold; }
.status-warn  { color: #facc15; font-weight: bold; }
.status-err   { color: #f87171; font-weight: bold; }
.badge-critical { background:#7f1d1d; color:#fca5a5; border-radius:4px; padding:2px 8px; font-size:12px; }
.badge-high     { background:#7c2d12; color:#fdba74; border-radius:4px; padding:2px 8px; font-size:12px; }
.badge-medium   { background:#713f12; color:#fde68a; border-radius:4px; padding:2px 8px; font-size:12px; }
.badge-low      { background:#1e3a5f; color:#93c5fd; border-radius:4px; padding:2px 8px; font-size:12px; }
</style>
""", unsafe_allow_html=True)


# ── Sidebar ──────────────────────────────────────────────────────
with st.sidebar:
    st.title("🔒 SPM")
    st.caption(f"Orchestrator: `{api.base_url()}`")
    st.divider()
    st.page_link("app.py",                       label="🏠 Overview",      icon=None)
    st.page_link("pages/1_Coda_Patch.py",        label="📋 Coda Patch")
    st.page_link("pages/2_Approvazioni.py",      label="✅ Approvazioni")
    st.page_link("pages/3_Test_Engine.py",       label="🧪 Test Engine")
    st.page_link("pages/4_Deployments.py",       label="🚀 Deployments")
    st.divider()
    if "operator" not in st.session_state:
        st.session_state.operator = ""
    st.session_state.operator = st.text_input(
        "Operatore", value=st.session_state.operator,
        placeholder="nome.cognome",
        help="Usato per approvazioni e deployments",
    )


# ── Titolo ───────────────────────────────────────────────────────
st.title("Security Patch Manager — Overview")

# ── Health system ────────────────────────────────────────────────
health, err = api.health_detail()

if err:
    st.error(f"Orchestrator non raggiungibile: {err}")
    st.stop()

overall = health.get("status", "unknown")
components = health.get("components", {})

col_db, col_uyuni, col_prom, col_up = st.columns(4)

def _comp_icon(c: dict) -> str:
    s = c.get("status", "unknown")
    return "🟢" if s == "connected" else ("🟡" if s == "unavailable" else "🔴")

with col_db:
    db = components.get("database", {})
    s = db.get("status", "?")
    st.metric("Database", s.upper(), delta=None)
    if s == "error":
        st.caption(f"⚠ {db.get('message','')}")

with col_uyuni:
    uy = components.get("uyuni", {})
    s = uy.get("status", "?")
    st.metric("UYUNI", s.upper())
    if s == "connected":
        st.caption(f"API v{uy.get('api_version','?')}")
    else:
        st.caption(f"⚠ {uy.get('message','')[:60]}")

with col_prom:
    pr = components.get("prometheus", {})
    s = pr.get("status", "?")
    st.metric("Prometheus", s.upper())
    if s == "unavailable":
        st.caption("Non critico — skipped")

with col_up:
    st.metric("Uptime", f"{health.get('uptime_seconds', 0) // 60} min")
    st.caption(f"v{health.get('version','?')}")


st.divider()

# ── Notifiche non lette ──────────────────────────────────────────
notif_data, _ = api.notifications(limit=10)
if notif_data:
    total_unread = notif_data.get("total_unread", 0)
    notif_items  = notif_data.get("items", [])
    if total_unread > 0:
        with st.container():
            for n in notif_items[:5]:
                ntype = n.get("notification_type", "?")
                icon  = "⏳" if ntype == "pending_approval" else "❌"
                subj  = n.get("subject", "")
                st.warning(f"{icon} {subj}", icon=None)
            if total_unread > 5:
                st.caption(f"+ altre {total_unread - 5} notifiche non lette")
            if st.button("✓ Segna tutte come lette", key="mark_read_banner"):
                api.notifications_mark_read()
                st.rerun()

# ── Stats coda ───────────────────────────────────────────────────
col_left, col_right = st.columns(2)

with col_left:
    st.subheader("Coda patch")
    stats, err = api.queue_stats()
    if err:
        st.error(err)
    elif stats:
        by_status = stats.get("by_status", {})
        by_os     = stats.get("by_os", {})
        total     = stats.get("total", 0)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Totale", total)
        c2.metric("In coda", by_status.get("queued", 0))
        c3.metric("In test", by_status.get("testing", 0))
        c4.metric("Approv.", by_status.get("pending_approval", 0))

        if by_os:
            st.caption(
                f"Ubuntu: {by_os.get('ubuntu', 0)}  |  "
                f"RHEL: {by_os.get('rhel', 0)}"
            )

        # Stato workflow
        workflow_states = {
            "passed": by_status.get("passed", 0),
            "approved": by_status.get("approved", 0),
            "failed": by_status.get("failed", 0),
            "rejected": by_status.get("rejected", 0),
            "completed": by_status.get("completed", 0),
        }
        non_zero = {k: v for k, v in workflow_states.items() if v > 0}
        if non_zero:
            st.caption("  ".join(f"{k}: **{v}**" for k, v in non_zero.items()))

with col_right:
    st.subheader("Test Engine — ultime 24h")
    ts, err = api.tests_status()
    if err:
        st.error(err)
    elif ts:
        running = ts.get("engine_running", False)
        stats24 = ts.get("stats_24h", {})

        if running:
            st.info("🔄 Test in corso...")
        else:
            st.success("✅ Engine inattivo")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Passati", stats24.get("passed_24h", 0), delta=None)
        c2.metric("Falliti", stats24.get("failed_24h", 0))
        c3.metric("Errori",  stats24.get("error_24h",  0))
        c4.metric("Durata media", f"{stats24.get('avg_duration_s') or 0}s")

        last = ts.get("last_result")
        if last:
            r = last.get("status", "?")
            eid = last.get("errata_id", "?")
            icon = "✅" if r == "pending_approval" else ("❌" if r == "failed" else "ℹ")
            st.caption(f"Ultimo: {icon} **{eid}** → {r}")


st.divider()

# ── Sync UYUNI ───────────────────────────────────────────────────
st.subheader("Sync UYUNI")

sync_col, errata_col = st.columns(2)

with sync_col:
    ss, err = api.sync_status()
    if err:
        st.error(err)
    elif ss:
        running = ss.get("running", False)
        last    = ss.get("last_sync", {}) or {}

        if running:
            st.info("🔄 Sync in corso...")
        else:
            last_at = last.get("completed_at") or last.get("started_at") or "mai"
            if isinstance(last_at, str) and len(last_at) > 16:
                last_at = last_at[:16].replace("T", " ")
            st.caption(f"Ultimo sync: **{last_at}**")
            if last.get("status") == "success":
                st.caption(
                    f"Errata sincronizzate: **{last.get('errata_count', 0)}**  |  "
                    f"Durata: {last.get('duration_s', '?')}s"
                )
            elif last.get("status") == "error":
                st.caption(f"⚠ Errore: {last.get('error','?')[:80]}")

    if st.button("🔄 Sync manuale", use_container_width=True):
        with st.spinner("Sync in corso..."):
            res, err = api.sync_trigger()
        if err:
            st.error(f"Sync fallito: {err}")
        else:
            st.success(
                f"Sync completato — {res.get('errata_count', '?')} errata "
                f"in {res.get('duration_s', '?')}s"
            )
            st.rerun()

with errata_col:
    cs, err = api.errata_cache_stats()
    if err:
        st.error(err)
    elif cs:
        bysev = cs.get("by_severity", {})
        byos  = cs.get("by_os", {})
        c1, c2, c3 = st.columns(3)
        c1.metric("Totale errata", cs.get("total", 0))
        c2.metric("Critical + High",
                  (bysev.get("critical", 0) or 0) + (bysev.get("high", 0) or 0))
        c3.metric("Ubuntu", byos.get("ubuntu", 0))

        last_sync = cs.get("last_synced")
        if last_sync:
            st.caption(f"Ultimo sync: {str(last_sync)[:16].replace('T',' ')}")


st.divider()

# ── Azione rapida: trigger test ──────────────────────────────────
st.subheader("Azioni rapide")

c1, c2 = st.columns(2)
with c1:
    if st.button("▶ Esegui prossimo test", use_container_width=True,
                 help="Prende il primo elemento 'queued' dalla coda e lo testa"):
        with st.spinner("Test in corso — potrebbe richiedere alcuni minuti..."):
            res, err = api.tests_run()
        if err:
            st.error(f"Errore: {err}")
        else:
            status = res.get("status", "?")
            if status == "skipped":
                st.info(f"Nessun test eseguito: {res.get('reason','?')}")
            elif status in ("pending_approval", "passed"):
                st.success(
                    f"Test superato — **{res.get('errata_id')}**  "
                    f"({res.get('duration_s', '?')}s)"
                )
            elif status in ("failed", "error"):
                st.error(
                    f"Test fallito — **{res.get('errata_id')}**  "
                    f"fase: {res.get('failure_phase','?')}  "
                    f"motivo: {res.get('failure_reason','?')}"
                )
            else:
                st.info(f"Risultato: {status}")
            st.rerun()

with c2:
    st.info(
        "Per aggiungere patch in coda o gestire le approvazioni, "
        "usa le pagine dedicate nel menu laterale.",
        icon="💡",
    )
