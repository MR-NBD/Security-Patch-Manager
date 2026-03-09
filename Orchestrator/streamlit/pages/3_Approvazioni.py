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
import auth_guard

auth_guard.require_auth()

st.title("✅ Approvazioni Patch")

tab_pending, tab_history = st.tabs(["In attesa", "Storico"])


# ════════════════════════════════════════════════════════════════
# TAB: PENDING
# ════════════════════════════════════════════════════════════════
with tab_pending:
    # Paginazione pending
    if "pending_page" not in st.session_state:
        st.session_state["pending_page"] = 0
    _pending_per_page = 20

    _pending_offset = st.session_state["pending_page"] * _pending_per_page
    data, err = api.approvals_pending(limit=_pending_per_page, offset=_pending_offset)
    if err:
        st.error(f"Errore API: {err}")
        st.stop()

    items      = data.get("items", []) if isinstance(data, dict) else (data or [])
    total      = data.get("total", len(items)) if isinstance(data, dict) else len(items)
    _tot_pages = max(1, -(-total // _pending_per_page))
    _cur_page  = st.session_state["pending_page"]

    if total == 0:
        st.success("Nessuna patch in attesa di approvazione.")
    else:
        st.info(
            f"**{total}** patch in attesa di approvazione — "
            f"pagina **{_cur_page + 1}** di **{_tot_pages}**"
        )

    op = st.session_state.get("user_upn", "").strip()

    for item in items:
        queue_id = item.get("queue_id")
        errata_id = item.get("errata_id", "?")
        severity = item.get("severity", "?")
        synopsis = item.get("synopsis") or "—"
        target_os = item.get("target_os", "?")
        score = item.get("success_score", "?")
        cves = item.get("cves") or []
        req_reboot = item.get("requires_reboot", False)
        affects_k = item.get("affects_kernel", False)
        test_id = item.get("test_id")
        hours_p = item.get("hours_pending")

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
                    if st.button(
                        "✅ Approva",
                        key=f"app_{queue_id}",
                        disabled=disabled,
                        use_container_width=True,
                        type="primary",
                    ):
                        res, e2 = api.approve(queue_id, op, reason or None)
                        if e2:
                            st.error(e2)
                        else:
                            st.success(f"Approvato: {errata_id}")
                            st.rerun()
                with br:
                    if st.button(
                        "🚫 Rifiuta",
                        key=f"rej_{queue_id}",
                        disabled=disabled,
                        use_container_width=True,
                    ):
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
                if st.button(
                    "💤 Snooze",
                    key=f"snz_{queue_id}",
                    disabled=disabled,
                    use_container_width=True,
                ):
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
                            "completed": "✅",
                            "failed": "❌",
                            "skipped": "⏭",
                            "in_progress": "🔄",
                        }
                        cols = st.columns(len(phases))
                        for i, ph in enumerate(phases):
                            pname = ph.get("phase_name", "?")
                            pstat = ph.get("status", "?")
                            pdur = ph.get("duration_seconds")
                            icon = phase_icons.get(pstat, "⬜")
                            dur_s = f" ({pdur}s)" if pdur else ""
                            with cols[i]:
                                st.caption(f"{icon} **{pname}**{dur_s}")
                                if ph.get("error_message"):
                                    st.caption(f"⚠ {ph['error_message'][:60]}")

    # ── Navigazione pagine pending ────────────────────────────────
    if _tot_pages > 1:
        st.divider()
        pp1, pp2, pp3 = st.columns([1, 1, 2])
        with pp1:
            if st.button(
                "◀ Prec",
                key="pending_prev",
                disabled=(_cur_page == 0),
                use_container_width=True,
            ):
                st.session_state["pending_page"] = _cur_page - 1
                st.rerun()
        with pp2:
            if st.button(
                "Succ ▶",
                key="pending_next",
                disabled=(_cur_page >= _tot_pages - 1),
                use_container_width=True,
            ):
                st.session_state["pending_page"] = _cur_page + 1
                st.rerun()


# ════════════════════════════════════════════════════════════════
# TAB: STORICO
# ════════════════════════════════════════════════════════════════
with tab_history:
    # ── Controlli filtro e paginazione ───────────────────────────
    fc1, fc2, fc3 = st.columns([2, 2, 2])

    with fc1:
        action_filter = st.selectbox(
            "Filtra per azione",
            ["Tutte", "approved", "rejected", "snoozed"],
            format_func=lambda x: {
                "Tutte": "Tutte le azioni",
                "approved": "✅ Approvate",
                "rejected": "🚫 Rifiutate",
                "snoozed":  "💤 Rimandate",
            }.get(x, x),
            key="hist_action_filter",
        )

    with fc2:
        per_page = st.selectbox(
            "Righe per pagina",
            [25, 50, 100],
            index=1,
            key="hist_per_page",
        )

    # Reset automatico pagina se cambiano filtro o per_page
    filter_key = f"{action_filter}_{per_page}"
    if st.session_state.get("hist_filter_key") != filter_key:
        st.session_state["hist_filter_key"] = filter_key
        st.session_state["hist_page"] = 0

    if "hist_page" not in st.session_state:
        st.session_state["hist_page"] = 0

    offset = st.session_state["hist_page"] * per_page

    # ── Carica dati ───────────────────────────────────────────────
    hist, err = api.approvals_history(limit=per_page, offset=offset)
    if err:
        st.error(f"Errore API: {err}")
    else:
        hist_data     = hist if isinstance(hist, dict) else {}
        history_items = hist_data.get("items", [])
        total_hist    = hist_data.get("total", len(history_items))

        # Filtra localmente per azione (il backend non ha filtro action)
        if action_filter != "Tutte":
            history_items = [
                h for h in history_items if h.get("action") == action_filter
            ]

        total_pages = max(1, -(-total_hist // per_page))  # ceil division
        current_page = st.session_state["hist_page"]

        if not history_items and offset == 0:
            st.info("Nessuna azione registrata.")
        else:
            st.caption(
                f"Totale: **{total_hist}** azioni | "
                f"Pagina **{current_page + 1}** di **{total_pages}**"
            )

            icons_act = {"approved": "✅", "rejected": "🚫", "snoozed": "💤"}
            rows = []
            for h in history_items:
                action = h.get("action", "?")
                rows.append({
                    "Data":       (str(h.get("action_at") or "")[:16]).replace("T", " "),
                    "Azione":     f"{icons_act.get(action, '?')} {action}",
                    "Errata":     h.get("errata_id", "?"),
                    "OS":         h.get("target_os", "?"),
                    "Operatore":  h.get("action_by", "?"),
                    "Motivo":     (h.get("reason") or "")[:70],
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

            # ── Navigazione pagine ────────────────────────────────────
            p1, p2, p3, p4 = st.columns([1, 1, 3, 1])
            with p1:
                if st.button(
                    "⬅ Prima",
                    disabled=(current_page == 0),
                    use_container_width=True,
                ):
                    st.session_state["hist_page"] = 0
                    st.rerun()
            with p2:
                if st.button(
                    "◀ Prec",
                    disabled=(current_page == 0),
                    use_container_width=True,
                ):
                    st.session_state["hist_page"] = current_page - 1
                    st.rerun()
            with p4:
                if st.button(
                    "Succ ▶",
                    disabled=(current_page >= total_pages - 1),
                    use_container_width=True,
                ):
                    st.session_state["hist_page"] = current_page + 1
                    st.rerun()
