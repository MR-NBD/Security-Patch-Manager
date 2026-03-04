"""
SPM Dashboard — Deployments

Gestione deployment patch in produzione:
  • Lista deployments con stato
  • Crea nuovo deployment (da patch approvata)
  • Dettaglio deployment con risultati per sistema
  • Rollback deployment
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
import pandas as pd
import api_client as api

st.set_page_config(
    page_title="Deployments — SPM",
    page_icon="🚀",
    layout="wide",
)

# ── Sidebar ──────────────────────────────────────────────────────
with st.sidebar:
    st.title("🔒 SPM")
    st.caption(f"Orchestrator: `{api.base_url()}`")
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

st.title("🚀 Deployments Produzione")

op = st.session_state.get("operator", "").strip()

# ── Tab: Lista | Nuovo | Dettaglio ───────────────────────────────
tab_list, tab_new, tab_detail = st.tabs(["📋 Lista", "➕ Nuovo", "🔍 Dettaglio"])


# ════════════════════════════════════════════════════════════════
# TAB: LISTA
# ════════════════════════════════════════════════════════════════
with tab_list:
    f_col, _ = st.columns([2, 3])
    with f_col:
        f_status = st.selectbox("Filtra per stato", [
            "", "running", "completed", "partial_failure",
            "failed", "rolled_back",
        ])

    deps, err = api.deployments_list(status=f_status or None, limit=50)
    if err:
        st.error(f"Errore API: {err}")
    else:
        items = deps.get("items", []) if isinstance(deps, dict) else (deps or [])
        total = deps.get("total", len(items)) if isinstance(deps, dict) else len(items)

        if not items:
            st.info("Nessun deployment trovato.")
        else:
            st.caption(f"**{total}** deployments totali")

            status_icons = {
                "running":         "🔄",
                "completed":       "✅",
                "partial_failure": "⚠",
                "failed":          "❌",
                "rolled_back":     "↩",
            }
            rows = []
            for d in items:
                s = d.get("status", "?")
                rows.append({
                    "ID":        d.get("id"),
                    "Errata":    d.get("errata_id", "?"),
                    "Stato":     f"{status_icons.get(s,'⬜')} {s}",
                    "Sistemi OK":   d.get("systems_succeeded", 0),
                    "Sistemi KO":   d.get("systems_failed", 0),
                    "Creato da":    d.get("created_by") or "",
                    "Data":      (str(d.get("started_at") or "")[:16]).replace("T", " "),
                    "Durata":    f"{d.get('duration_s','?')}s" if d.get("duration_s") else "—",
                })
            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True, hide_index=True)

            # Rollback rapido dalla lista
            st.divider()
            st.subheader("Rollback")
            if not op:
                st.warning("Inserisci il nome operatore nella barra laterale.")
            else:
                rb_col1, rb_col2, rb_col3 = st.columns(3)
                with rb_col1:
                    rb_id = st.number_input("ID deployment", min_value=1, step=1,
                                             value=None, placeholder="ID...")
                with rb_col2:
                    rb_reason = st.text_input("Motivazione *", placeholder="es. regressione rilevata")
                with rb_col3:
                    st.write("")
                    st.write("")
                    if st.button("↩ Rollback", type="secondary", use_container_width=True):
                        if not rb_id:
                            st.error("ID obbligatorio")
                        elif not rb_reason.strip():
                            st.error("Motivazione obbligatoria")
                        else:
                            with st.spinner("Rollback in corso..."):
                                res, e2 = api.deployment_rollback(
                                    int(rb_id), op, rb_reason.strip()
                                )
                            if e2:
                                st.error(f"Errore: {e2}")
                            else:
                                ok  = res.get("systems_succeeded", 0)
                                ko  = res.get("systems_failed", 0)
                                if ko == 0:
                                    st.success(f"Rollback completato — {ok} sistemi OK")
                                else:
                                    st.warning(f"Rollback parziale — OK:{ok} KO:{ko}")
                            st.rerun()


# ════════════════════════════════════════════════════════════════
# TAB: NUOVO DEPLOYMENT
# ════════════════════════════════════════════════════════════════
with tab_new:
    st.markdown("""
    Crea un nuovo deployment in produzione.
    La patch deve essere in stato **`approved`** (approva prima nella pagina Approvazioni).
    """)

    if not op:
        st.warning("Inserisci il nome operatore nella barra laterale.")

    # Mostra patch approvate disponibili
    approved_data, _ = api.queue_list(status="approved", limit=50)
    approved_items = (
        approved_data.get("items", [])
        if isinstance(approved_data, dict)
        else (approved_data or [])
    )

    if not approved_items:
        st.info("Nessuna patch approvata disponibile per il deployment.")
    else:
        st.success(f"**{len(approved_items)}** patch approvate pronte per il deployment.")

    with st.form("new_deployment"):
        st.subheader("Configura deployment")

        # Queue ID — selezione da approvate o input manuale
        if approved_items:
            options = {
                f"#{it['id']} — {it.get('errata_id')} ({it.get('target_os')}) "
                f"score={it.get('success_score')}": it["id"]
                for it in approved_items
            }
            sel = st.selectbox("Patch approvata *", list(options.keys()))
            queue_id_val = options[sel]
        else:
            queue_id_val = st.number_input(
                "Queue ID *", min_value=1, step=1, value=None,
                placeholder="ID elemento approvato",
            )

        # Sistemi target
        st.markdown("**Sistemi target** (uno per riga, nome minion Salt):")
        systems_text = st.text_area(
            "Sistemi",
            placeholder="prod-ubuntu-01\nprod-ubuntu-02\nprod-ubuntu-03",
            height=100,
            help="Nome del minion Salt (es. hostname o IP)",
        )

        notes_val = st.text_input(
            "Note", placeholder="es. finestra manutenzione 2026-03-10 22:00"
        )

        submitted = st.form_submit_button(
            "🚀 Avvia Deployment", type="primary",
            disabled=not bool(op), use_container_width=True,
        )

        if submitted:
            if not queue_id_val:
                st.error("Queue ID obbligatorio")
            elif not systems_text.strip():
                st.error("Almeno un sistema target obbligatorio")
            else:
                systems = [
                    {"name": s.strip()}
                    for s in systems_text.strip().splitlines()
                    if s.strip()
                ]
                with st.spinner(f"Deployment in corso su {len(systems)} sistemi..."):
                    res, e2 = api.deployment_create(
                        queue_id=int(queue_id_val),
                        target_systems=systems,
                        created_by=op,
                        notes=notes_val.strip() or None,
                    )
                if e2:
                    st.error(f"Deployment fallito: {e2}")
                elif res:
                    ok = res.get("systems_succeeded", 0)
                    ko = res.get("systems_failed", 0)
                    dur = res.get("duration_s", "?")
                    if ko == 0:
                        st.success(
                            f"Deployment completato — {ok} sistemi OK "
                            f"({dur}s) | ID: {res.get('deployment_id')}"
                        )
                    else:
                        st.warning(
                            f"Deployment parziale — OK:{ok} KO:{ko} "
                            f"({dur}s) | ID: {res.get('deployment_id')}"
                        )
                        failed = res.get("failed_systems", [])
                        if failed:
                            st.error(f"Sistemi falliti: {', '.join(str(s) for s in failed)}")
                    st.rerun()


# ════════════════════════════════════════════════════════════════
# TAB: DETTAGLIO
# ════════════════════════════════════════════════════════════════
with tab_detail:
    dep_id_input = st.number_input(
        "ID Deployment", min_value=1, step=1, value=None,
        placeholder="Inserisci ID deployment...",
    )

    if dep_id_input:
        dep, derr = api.deployment_detail(int(dep_id_input))
        if derr:
            st.error(derr)
        elif dep:
            status_icons = {
                "running": "🔄", "completed": "✅",
                "partial_failure": "⚠", "failed": "❌", "rolled_back": "↩",
            }
            s = dep.get("status", "?")

            c1, c2 = st.columns(2)
            with c1:
                st.markdown(f"**Errata:** {dep.get('errata_id')}")
                st.markdown(f"**Status:** {status_icons.get(s,'?')} {s}")
                st.markdown(f"**Creato da:** {dep.get('created_by') or '—'}")
                started = str(dep.get("started_at") or "")[:16].replace("T", " ")
                completed = str(dep.get("completed_at") or "")[:16].replace("T", " ")
                st.markdown(f"**Avviato:** {started}  |  **Completato:** {completed}")
                if dep.get("notes"):
                    st.markdown(f"**Note:** {dep.get('notes')}")
            with c2:
                st.markdown(f"**Sistemi OK:** {dep.get('systems_succeeded', 0)}")
                st.markdown(f"**Sistemi KO:** {dep.get('systems_failed', 0)}")
                if dep.get("failed_systems"):
                    st.markdown(f"**Falliti:** {', '.join(str(x) for x in dep['failed_systems'])}")
                st.markdown(f"**Durata:** {dep.get('duration_s','?')}s")

            # Risultati per sistema
            sys_results = dep.get("system_results") or {}
            if sys_results:
                st.divider()
                st.markdown("**Risultati per sistema:**")
                for sname, sres in sys_results.items():
                    sstat  = sres.get("status", "?")
                    serr   = sres.get("error")
                    pkgs   = sres.get("packages_applied") or {}
                    sicon  = "✅" if sstat == "success" else ("❌" if sstat == "failed" else "⚠")
                    with st.expander(f"{sicon} {sname} — {sstat}"):
                        if serr:
                            st.error(serr)
                        if pkgs:
                            pkg_rows = [
                                {"Pacchetto": k,
                                 "Versione precedente": v.get("old","?") if isinstance(v,dict) else "?",
                                 "Versione nuova": v.get("new","?") if isinstance(v,dict) else "?"}
                                for k, v in pkgs.items()
                            ]
                            st.dataframe(pd.DataFrame(pkg_rows), hide_index=True,
                                         use_container_width=True)

            # Rollback dal dettaglio
            if s in ("completed", "partial_failure"):
                st.divider()
                if not op:
                    st.warning("Inserisci il nome operatore nella barra laterale per il rollback.")
                else:
                    with st.form(f"rollback_{dep_id_input}"):
                        rb_reason2 = st.text_input(
                            "Motivazione rollback *",
                            placeholder="es. regressione nelle performance",
                        )
                        if st.form_submit_button("↩ Esegui Rollback", type="secondary"):
                            if not rb_reason2.strip():
                                st.error("Motivazione obbligatoria")
                            else:
                                with st.spinner("Rollback in corso..."):
                                    res, e2 = api.deployment_rollback(
                                        int(dep_id_input), op, rb_reason2.strip()
                                    )
                                if e2:
                                    st.error(f"Errore: {e2}")
                                else:
                                    ok = res.get("systems_succeeded", 0)
                                    ko = res.get("systems_failed", 0)
                                    if ko == 0:
                                        st.success(f"Rollback completato — {ok} sistemi OK")
                                    else:
                                        st.warning(f"Rollback parziale — OK:{ok} KO:{ko}")
                                    st.rerun()
