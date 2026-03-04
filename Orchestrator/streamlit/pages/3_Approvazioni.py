"""
SPM Dashboard — Approvazioni

Workflow approvazione patch dopo test superato:
  • Lista patch in pending_approval
  • Dettaglio: CVE, pacchetti, fasi test, risk profile
  • Azioni: Approva / Rifiuta / Snooze
  • Storico approvazioni
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timezone, timedelta
import pandas as pd

import streamlit as st
import api_client as api

st.title("✅ Approvazioni Patch")

tab_pending, tab_history = st.tabs(["⏳ In attesa", "📜 Storico"])


# ════════════════════════════════════════════════════════════════
# TAB: PENDING
# ════════════════════════════════════════════════════════════════
with tab_pending:
    data, err = api.approvals_pending(limit=50)
    if err:
        st.error(f"Errore API: {err}")
        st.stop()

    items = data.get("items", []) if isinstance(data, dict) else (data or [])
    total = data.get("total", len(items)) if isinstance(data, dict) else len(items)

    if total == 0:
        st.success("Nessuna patch in attesa di approvazione.")
    else:
        st.info(f"**{total}** patch in attesa di approvazione.")

    op = st.session_state.get("operator", "").strip()
    if not op and total > 0:
        st.warning("Inserisci il tuo nome nel campo 'Operatore' nella barra laterale per effettuare azioni.")

    for item in items:
        queue_id   = item.get("queue_id")
        errata_id  = item.get("errata_id", "?")
        severity   = item.get("severity", "?")
        synopsis   = item.get("synopsis") or "—"
        target_os  = item.get("target_os", "?")
        score      = item.get("success_score", "?")
        cves       = item.get("cves") or []
        req_reboot = item.get("requires_reboot", False)
        affects_k  = item.get("affects_kernel", False)
        test_id    = item.get("test_id")
        hours_p    = item.get("hours_pending")

        sev_icons = {"Critical": "🔴", "High": "🟠", "Medium": "🟡", "Low": "🔵"}
        sev_icon = sev_icons.get(severity, "⚪")

        with st.expander(
            f"{sev_icon} **{errata_id}** — {synopsis[:70]} "
            f"| OS: {target_os} | Score: {score} "
            + (f"| {hours_p:.0f}h in attesa" if hours_p else ""),
            expanded=(severity in ("Critical", "High")),
        ):
            c_info, c_risk, c_actions = st.columns([3, 2, 2])

            with c_info:
                st.markdown(f"**Synopsis:** {synopsis}")
                st.markdown(f"**Severity:** {severity}")
                st.markdown(f"**OS:** {target_os}")
                if cves:
                    cve_str = ", ".join(cves[:8])
                    if len(cves) > 8:
                        cve_str += f" + altri {len(cves)-8}"
                    st.markdown(f"**CVE:** {cve_str}")
                else:
                    st.markdown("**CVE:** nessuno")

            with c_risk:
                st.markdown("**Risk profile**")
                st.markdown(f"Score: **{score}** / 100")
                st.markdown(f"Reboot: {'⚠ Sì' if req_reboot else '✅ No'}")
                st.markdown(f"Kernel: {'⚠ Sì' if affects_k else '✅ No'}")
                if test_id:
                    st.markdown(f"Test ID: `{test_id}`")

            with c_actions:
                st.markdown("**Azione**")
                disabled = not bool(op)

                reason = st.text_input(
                    "Motivo (opzionale per approve)",
                    key=f"reason_{queue_id}",
                    placeholder="es. testato in staging",
                )

                ba, br = st.columns(2)
                with ba:
                    if st.button("✅ Approva", key=f"app_{queue_id}",
                                 disabled=disabled, use_container_width=True,
                                 type="primary"):
                        res, e2 = api.approve(queue_id, op, reason or None)
                        if e2:
                            st.error(e2)
                        else:
                            st.success(f"Approvato: {errata_id}")
                            st.rerun()
                with br:
                    if st.button("🚫 Rifiuta", key=f"rej_{queue_id}",
                                 disabled=disabled, use_container_width=True):
                        if not reason.strip():
                            st.error("Motivo obbligatorio per il rifiuto")
                        else:
                            res, e2 = api.reject(queue_id, op, reason)
                            if e2:
                                st.error(e2)
                            else:
                                st.warning(f"Rifiutato: {errata_id}")
                                st.rerun()

                snooze_hours = st.selectbox(
                    "Rimanda di",
                    [4, 8, 24, 48, 72, 168],
                    format_func=lambda h: f"{h}h" if h < 48 else f"{h//24}gg",
                    key=f"snooze_h_{queue_id}",
                )
                if st.button("💤 Snooze", key=f"snz_{queue_id}",
                             disabled=disabled, use_container_width=True):
                    until = (
                        datetime.now(timezone.utc) + timedelta(hours=snooze_hours)
                    ).isoformat()
                    res, e2 = api.snooze(queue_id, op, until, reason or None)
                    if e2:
                        st.error(e2)
                    else:
                        st.info(f"Rimandato di {snooze_hours}h: {errata_id}")
                        st.rerun()

            if test_id:
                test_data, _ = api.test_detail(test_id)
                if test_data:
                    phases = test_data.get("phases", [])
                    if phases:
                        st.markdown("**Fasi test:**")
                        phase_icons = {
                            "completed": "✅", "failed": "❌",
                            "skipped": "⏭", "in_progress": "🔄",
                        }
                        cols = st.columns(len(phases))
                        for i, ph in enumerate(phases):
                            pname = ph.get("phase_name", "?")
                            pstat = ph.get("status", "?")
                            pdur  = ph.get("duration_seconds")
                            icon  = phase_icons.get(pstat, "⬜")
                            dur_s = f" ({pdur}s)" if pdur else ""
                            with cols[i]:
                                st.caption(f"{icon} **{pname}**{dur_s}")
                                if ph.get("error_message"):
                                    st.caption(f"⚠ {ph['error_message'][:60]}")


# ════════════════════════════════════════════════════════════════
# TAB: STORICO
# ════════════════════════════════════════════════════════════════
with tab_history:
    hist, err = api.approvals_history(limit=100)
    if err:
        st.error(f"Errore API: {err}")
    else:
        history_items = hist.get("items", []) if isinstance(hist, dict) else (hist or [])
        if not history_items:
            st.info("Nessuna azione registrata.")
        else:
            rows = []
            for h in history_items:
                action = h.get("action", "?")
                icons_act = {"approved": "✅", "rejected": "🚫", "snoozed": "💤"}
                rows.append({
                    "Data":      (str(h.get("action_at") or "")[:16]).replace("T", " "),
                    "Azione":    f"{icons_act.get(action,'?')} {action}",
                    "Errata":    h.get("errata_id", "?"),
                    "Operatore": h.get("action_by", "?"),
                    "Motivo":    (h.get("reason") or "")[:60],
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
