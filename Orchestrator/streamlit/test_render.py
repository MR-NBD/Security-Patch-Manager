"""
test_render — funzioni di rendering condivise per la visualizzazione
dei risultati test (pipeline, fasi, metriche Prometheus).

Usato da 2_Test_Batch.py e 3_Approvazioni.py.
"""

from datetime import datetime, timezone
import pandas as pd
import streamlit as st

# ─────────────────────────────────────────────────────────────────
# Costanti
# ─────────────────────────────────────────────────────────────────

PHASE_ICON = {
    "completed":   "✅",
    "failed":      "❌",
    "skipped":     "—",
    "in_progress": "⏳",
}

PHASE_LABEL = {
    "pre_check":     "⓪ Pre-check",
    "snapshot":      "① Snapshot",
    "patch":         "② Patch",
    "reboot":        "③ Reboot",
    "validate":      "④ Validate (Prometheus)",
    "services":      "⑤ Service check",
    "rollback":      "↩ Rollback",
    "post_rollback": "↩✓ Post-rollback verify",
}

PIPELINE_STEPS = [
    "pre_check", "snapshot", "patch", "reboot",
    "validate", "services",
]


# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────

def fmt_duration(seconds) -> str:
    if seconds is None:
        return "—"
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    return f"{s // 60}m {s % 60}s"


def elapsed(iso_start: str) -> str:
    try:
        start = datetime.fromisoformat(iso_start.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - start
        s = int(delta.total_seconds())
        return f"{s}s" if s < 60 else f"{s // 60}m {s % 60}s"
    except Exception:
        return "?"


def phase_detail(phase: dict) -> str:
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
            parts.append("Reboot pendente")
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
            return "Prometheus non disponibile — validazione saltata"
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
        return f"DOWN: {', '.join(failed)}"

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
        return f"Servizi ancora DOWN: {', '.join(failed)}" if failed else err

    return err or "—"


# ─────────────────────────────────────────────────────────────────
# Rendering
# ─────────────────────────────────────────────────────────────────

def render_pipeline(phases: list) -> None:
    """Mostra la pipeline di esecuzione come riga di badge colorati."""
    phase_map = {p["phase_name"]: p for p in phases}
    cols = st.columns(len(PIPELINE_STEPS) + 2)  # +2 per rollback e esito finale

    for i, step in enumerate(PIPELINE_STEPS):
        p = phase_map.get(step)
        if not p:
            label = PHASE_LABEL.get(step, step).split(" ", 1)[-1]
            cols[i].markdown(f"· *{label}*")
        else:
            status = p.get("status", "")
            icon   = PHASE_ICON.get(status, "·")
            label  = PHASE_LABEL.get(step, step).split(" ", 1)[-1]
            cols[i].markdown(f"{icon} **{label}**")

    rb = phase_map.get("rollback")
    if rb:
        icon = PHASE_ICON.get(rb["status"], "·")
        cols[-2].markdown(f"{icon} **Rollback**")
    else:
        cols[-2].markdown("· *Rollback*")

    all_done = all(
        phase_map.get(s, {}).get("status") in ("completed", "skipped")
        for s in PIPELINE_STEPS
        if s != "reboot" or s in phase_map
    )
    if rb:
        cols[-1].markdown("❌ **Fallita**")
    elif all_done and phase_map:
        cols[-1].markdown("✅ **Approvazione**")
    else:
        cols[-1].markdown("· *Esito*")


def render_phases_table(phases: list) -> None:
    """Tabella dettagliata di tutte le fasi."""
    if not phases:
        st.caption("Nessuna fase registrata.")
        return

    rows = []
    for p in phases:
        name   = p.get("phase_name", "?")
        status = p.get("status", "?")
        icon   = PHASE_ICON.get(status, "⬜")
        dur    = fmt_duration(p.get("duration_seconds"))
        detail = phase_detail(p)
        started = (p.get("started_at") or "")[:19].replace("T", " ")
        rows.append({
            "Fase":      PHASE_LABEL.get(name, name),
            "Stato":     f"{icon} {status}",
            "Inizio":    started,
            "Durata":    dur,
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


def render_prometheus_section(test: dict) -> None:
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
        icon = " ✅" if ok else (" ❌" if ok is False else "")
        return f"{v:+.1f}%{icon}"

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("CPU baseline",   _fmt(cpu_base))
    c2.metric("CPU post-patch", _fmt(cpu_post),
              delta=_fmt_delta(cpu_d, cpu_ok),
              delta_color="inverse" if cpu_ok is False else "normal")
    c3.metric("MEM baseline",   _fmt(mem_base))
    c4.metric("MEM post-patch", _fmt(mem_post),
              delta=_fmt_delta(mem_d, mem_ok),
              delta_color="inverse" if mem_ok is False else "normal")

    if evalu.get("skipped"):
        st.caption("Validazione Prometheus saltata (dati non disponibili al momento del test).")


def render_test_detail(test_data: dict, *, show_system_info: bool = True) -> None:
    """
    Rendering completo di un test: info sistema, pipeline, fasi, Prometheus,
    motivo fallimento. Usabile sia da batch che da approvazioni.
    """
    phases         = test_data.get("phases") or []
    failure_phase  = test_data.get("failure_phase")
    failure_reason = test_data.get("failure_reason")

    if show_system_info:
        c1, c2, c3 = st.columns(3)
        c1.metric("Sistema", test_data.get("test_system_name") or test_data.get("test_system_ip") or "?")
        c2.metric("Durata",  fmt_duration(test_data.get("duration_seconds")))
        snap_id = test_data.get("snapshot_id")
        c3.metric("Snapshot", f"#{snap_id}" if snap_id else (test_data.get("snapshot_type") or "—"))

    if phases:
        st.caption("**Pipeline:**")
        render_pipeline(phases)
        st.divider()

    tab_fasi, tab_prom = st.tabs(["Fasi", "Prometheus"])
    with tab_fasi:
        render_phases_table(phases)
    with tab_prom:
        render_prometheus_section(test_data)

    if failure_reason:
        label = f"Fase: **{failure_phase}** — " if failure_phase else ""
        st.error(f"**Motivo fallimento:** {label}{failure_reason}")
