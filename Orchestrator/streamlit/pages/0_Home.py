"""
SPM Dashboard — Overview (Home)
"""

import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timezone
import streamlit as st
import api_client as api
import auth_guard

auth_guard.require_auth()


@st.cache_data(ttl=300, show_spinner=False)
def _load_groups_summary(org_id):
    """Cache di 5 min: evita UYUNI XML-RPC ad ogni rerun della Home."""
    return api.groups_summary(org_id)


st.title("Pivi Orchestrator Patch Manager")

# ── Verifica connessione ─────────────────────────────────────────
health, err = api.health_detail()
if err:
    st.error(f"Orchestrator non raggiungibile ({api.base_url()}): {err}")
    st.stop()

# ── Stato componenti ─────────────────────────────────────────────
components = health.get("components", {})
c1, c2, c3, c4 = st.columns(4)


def _status_label(comp: dict) -> str:
    s = comp.get("status", "unknown")
    icons = {"connected": "🟢", "unavailable": "🟡", "error": "🔴"}
    return f"{icons.get(s, '⚪')} {s.upper()}"


with c1:
    db = components.get("database", {})
    st.metric("Database", _status_label(db))
    if db.get("message"):
        st.caption(f"⚠ {db['message'][:60]}")

with c2:
    uy = components.get("uyuni", {})
    st.metric("UYUNI", _status_label(uy))
    if uy.get("status") == "connected":
        st.caption(f"API v{uy.get('api_version','?')}")
    elif uy.get("message"):
        st.caption(f"⚠ {uy['message'][:60]}")

with c3:
    pr = components.get("prometheus", {})
    st.metric("Prometheus", _status_label(pr))
    if pr.get("status") == "unavailable":
        st.caption("Non critico")

with c4:
    started_at_raw = health.get("started_at")
    if started_at_raw:
        try:
            dt = datetime.fromisoformat(started_at_raw.replace("Z", "+00:00"))
            started_str = dt.strftime("%d %b %Y %H:%M")
            started_date = dt.strftime("%d %b %Y")
            started_time = dt.strftime("%H:%M UTC")
        except Exception:
            started_str = str(started_at_raw)[:16].replace("T", " ")
            started_date = started_str
            started_time = ""
        st.metric("Avviato il", started_date)
        st.caption(f"alle {started_time} — v{health.get('version','?')}")
    else:
        uptime_min = health.get("uptime_seconds", 0) // 60
        st.metric("Uptime", f"{uptime_min} min")
        st.caption(f"v{health.get('version','?')}")


st.divider()

# ── Notifiche non lette ──────────────────────────────────────────
notif_data, _ = api.notifications(limit=10)
if notif_data and notif_data.get("total_unread", 0) > 0:
    total_unread = notif_data["total_unread"]
    items_notif = notif_data.get("items", [])
    for n in items_notif[:5]:
        ntype = n.get("notification_type", "")
        icon = "⏳" if ntype == "pending_approval" else "❌"
        st.warning(f"{icon} {n.get('subject','')}")
    if total_unread > 5:
        st.caption(f"+ altre {total_unread - 5} notifiche non lette")
    if st.button("✓ Segna tutte come lette"):
        api.notifications_mark_read()
        st.rerun()

# ── Coda e test stats ────────────────────────────────────────────
stats, queue_err = api.queue_stats()
ts, ts_err = api.tests_status()

left, right = st.columns(2)

with left:
    st.subheader("Coda patch")
    if queue_err:
        st.error(queue_err)
    elif stats:
        _queued = stats.get("queued", 0)
        _retry = stats.get("retry_pending", 0)
        _testing = stats.get("testing", 0)
        _approval = stats.get("pending_approval", 0)
        _failed = stats.get("failed", 0)
        # Patch che richiedono ancora azione: da testare + in approvazione + fallite
        _pendenti = _queued + _retry + _approval + _failed

        s1, s2, s3, s4 = st.columns(4)
        s1.metric(
            "Patch pendenti",
            _pendenti,
            help="Da testare + in approvazione + fallite (richiedono azione)",
        )
        s2.metric(
            "In coda",
            _queued,
            help=f"Pronte al test: {_queued}"
            + (f" + {_retry} in retry" if _retry else ""),
        )
        s3.metric("In test", _testing)
        s4.metric("Da approvare", _approval)

        ubuntu = stats.get("ubuntu", 0)
        rhel = stats.get("rhel", 0)
        parts = []
        if ubuntu:
            parts.append(f"Ubuntu: **{ubuntu}**")
        if rhel:
            parts.append(f"RHEL: **{rhel}**")
        if _retry:
            parts.append(f"In retry: **{_retry}**")
        if _failed:
            parts.append(f"Falliti: **{_failed}**")
        if parts:
            st.caption("  |  ".join(parts))

with right:
    st.subheader("Test Engine")
    if ts_err:
        st.error(ts_err)
    elif ts:
        running = ts.get("engine_running", False)

        if running:
            st.info("Test in corso...")
        else:
            st.success("Engine inattivo")

        if not queue_err and stats:
            ta, tb = st.columns(2)
            ta.metric(
                "Da approvare",
                stats.get("pending_approval", 0),
                help="Patch che hanno superato il test e attendono approvazione",
            )
            tb.metric(
                "Fallite",
                stats.get("failed", 0),
                help="Patch con test fallito — visibili in Test Batch",
            )

        last = ts.get("last_result")
        if last and isinstance(last, dict):
            r = last.get("status", "?")
            eid = last.get("errata_id", "?")
            icons = {
                "pending_approval": "✅",
                "failed": "❌",
                "error": "🔥",
                "skipped": "⏭",
            }
            st.caption(f"Ultimo: {icons.get(r,'ℹ')} **{eid}** → {r}")


st.divider()

# ── Sync UYUNI ───────────────────────────────────────────────────
st.subheader("Sync UYUNI")
sc1, sc2 = st.columns(2)

with sc1:
    ss, err = api.sync_status()
    if err:
        st.error(err)
    elif ss:
        if ss.get("sync_running"):
            st.info("Sync in corso...")
        else:
            last_sync = ss.get("last_sync")
            if last_sync:
                last_str = str(last_sync)[:16].replace("T", " ")
                st.caption(f"Ultimo sync: **{last_str}**")
                if ss.get("last_error"):
                    st.caption(f"⚠ {ss['last_error'][:80]}")
                else:
                    st.caption(
                        f"Inseriti: **{ss.get('last_inserted', 0)}**  |  "
                        f"Aggiornati: **{ss.get('last_updated', 0)}**  |  "
                        f"Durata: **{ss.get('last_duration_seconds', '?')}s**"
                    )
            else:
                st.caption("Nessun sync eseguito ancora")

    if st.button("Sync manuale", use_container_width=True):
        with st.spinner("Sync in corso..."):
            res, e2 = api.sync_trigger()
        if e2:
            st.error(f"Sync fallito: {e2}")
        else:
            st.success(
                f"Sync completato — "
                f"{res.get('errata_count') or res.get('inserted',0) + res.get('updated',0)} errata  |  "
                f"{res.get('duration_s') or res.get('duration_seconds','?')}s"
            )
            st.rerun()

with sc2:
    _org_id = st.session_state.get("selected_org_id")
    gs, gs_err = _load_groups_summary(_org_id)
    if gs_err:
        st.error(gs_err)
    elif gs:
        bysev = gs.get("by_severity", {})
        e1, e2, e3 = st.columns(3)
        e1.metric(
            "Patch applicabili",
            gs.get("total_patches", 0),
            help="Patch applicabili ai sistemi nei gruppi test-* dell'organizzazione selezionata",
        )
        e2.metric(
            "Critical+High",
            (bysev.get("critical") or 0) + (bysev.get("high") or 0),
        )
        e3.metric(
            "Sistemi",
            gs.get("total_systems", 0),
            help="Sistemi unici nei gruppi test-* dell'organizzazione",
        )


st.divider()

# ── Azioni rapide ────────────────────────────────────────────────
st.subheader("Azioni rapide")
ac1, ac2 = st.columns(2)

with ac1:
    engine_running = ts.get("engine_running", False) if ts else False

    if st.button(
        "▶ Esegui prossimo test",
        use_container_width=True,
        disabled=engine_running,
        help="Prende il primo elemento 'queued' e lo testa",
    ):
        with st.spinner("Test in corso — può richiedere alcuni minuti..."):
            res, e2 = api.tests_run()
        if e2:
            st.error(f"Errore: {e2}")
        else:
            s = res.get("status", "?")
            if s == "skipped":
                st.info(f"Nessun test: {res.get('reason')}")
            elif s in ("pending_approval", "passed"):
                st.success(
                    f"Test superato — **{res.get('errata_id')}** ({res.get('duration_s','?')}s)"
                )
            elif s in ("failed", "error"):
                st.error(
                    f"Fallito — **{res.get('errata_id')}**  "
                    f"fase: {res.get('failure_phase','?')}  "
                    f"motivo: {(res.get('failure_reason') or '')[:100]}"
                )
            st.rerun()

with ac2:
    pa_count = 0
    pd2, _ = api.approvals_pending(limit=1)
    if pd2:
        pa_count = pd2.get("total", 0)
    if pa_count > 0:
        st.warning(f"**{pa_count} patch** in attesa di approvazione.", icon="⏳")
    else:
        st.info("Nessuna patch in attesa di approvazione.", icon="✅")
