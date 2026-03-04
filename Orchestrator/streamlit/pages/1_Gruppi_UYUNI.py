"""
SPM Dashboard — Gruppi UYUNI

Mostra i gruppi di test UYUNI con i relativi sistemi e le patch applicabili.
L'operatore può selezionare le patch da inserire in coda per il batch test.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
import pandas as pd
import api_client as api

st.title("🖥 Gruppi UYUNI")
st.caption("Patch applicabili ai sistemi di test, organizzate per gruppo.")

# ── Carica gruppi ─────────────────────────────────────────────────
with st.spinner("Caricamento gruppi UYUNI..."):
    gdata, gerr = api.groups_list()

if gerr:
    st.error(f"Errore API: {gerr}")
    st.stop()

groups = (gdata or {}).get("groups", [])
if not groups:
    st.info("Nessun gruppo test trovato in UYUNI (prefisso 'test-').")
    st.stop()

# ── Selezione gruppo ──────────────────────────────────────────────
group_names  = [g["name"] for g in groups]
group_by_name = {g["name"]: g for g in groups}

selected_group = st.selectbox("Seleziona gruppo", group_names)
g = group_by_name[selected_group]

# ── Info gruppo ───────────────────────────────────────────────────
info1, info2, info3 = st.columns(3)
info1.metric("OS",               g.get("os", "?").upper())
info2.metric("Sistemi",          g.get("system_count", 0))
info3.metric("Patch applicabili", g.get("patch_count", 0))

# Sistemi nel gruppo
systems = g.get("systems", [])
if systems:
    st.caption("**Sistemi:** " + "  |  ".join(
        f"`{s['name']}`" for s in systems
    ))

st.divider()

# ── Carica patch del gruppo ───────────────────────────────────────
with st.spinner(f"Caricamento patch per {selected_group}..."):
    pdata, perr = api.group_patches(selected_group)

if perr:
    st.error(f"Errore patch: {perr}")
    st.stop()

patches = (pdata or {}).get("patches", [])

if not patches:
    st.info("Nessuna patch applicabile per questo gruppo.")
    st.stop()

st.subheader(f"Patch applicabili — {len(patches)} trovate")

# ── Tabella patch con selezione ───────────────────────────────────
_TYPE_ICON = {
    "Security Advisory":            "🔴",
    "Bug Fix Advisory":             "🟡",
    "Product Enhancement Advisory": "🔵",
}

rows = []
for p in patches:
    atype = p.get("advisory_type", "")
    rows.append({
        "Seleziona":      False,
        "Advisory":       p.get("advisory_name", "?"),
        "Tipo":           f"{_TYPE_ICON.get(atype,'⚪')} {atype}",
        "Synopsis":       (p.get("synopsis") or "")[:70],
        "Data":           (p.get("date") or "")[:10],
        "Sistemi":        len(p.get("systems_affected", [])),
    })

df = pd.DataFrame(rows)
edited = st.data_editor(
    df,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Seleziona": st.column_config.CheckboxColumn("Seleziona", default=False),
    },
    disabled=["Advisory", "Tipo", "Synopsis", "Data", "Sistemi"],
    key="patch_selection",
)

selected_patches = edited[edited["Seleziona"] == True]["Advisory"].tolist()

if selected_patches:
    st.success(f"**{len(selected_patches)}** patch selezionate.")
else:
    st.caption("Seleziona le patch da testare nella colonna 'Seleziona'.")

st.divider()

# ── Aggiungi patch selezionate alla coda ──────────────────────────
st.subheader("Aggiungi in coda")

os_map = {"ubuntu": "ubuntu", "rhel": "rhel"}
target_os = os_map.get(g.get("os", ""), "ubuntu")

col_by, col_prio = st.columns(2)
with col_by:
    created_by = st.text_input(
        "Creato da (tuo nome/cognome)", placeholder="nome.cognome"
    )
with col_prio:
    priority = st.number_input("Priorità", min_value=0, max_value=10, value=0)

if st.button(
    f"➕ Aggiungi {len(selected_patches)} patch in coda",
    type="primary",
    disabled=not selected_patches,
    use_container_width=True,
):
    if not selected_patches:
        st.warning("Seleziona almeno una patch.")
    else:
        added = 0
        errors = []
        progress = st.progress(0, text="Aggiunta patch in coda...")
        for i, errata_id in enumerate(selected_patches):
            res, err = api.queue_add(
                errata_id=errata_id,
                target_os=target_os,
                priority_override=priority,
                created_by=created_by.strip() or None,
            )
            progress.progress((i + 1) / len(selected_patches))
            if err:
                errors.append(f"{errata_id}: {err}")
            else:
                queued = res.get("queued", [])
                added += len(queued)
                for e in res.get("errors", []):
                    errors.append(f"{e.get('errata_id')}: {e.get('error')}")

        progress.empty()
        if added:
            st.success(
                f"**{added}** patch aggiunte in coda. "
                "Vai su **Test Batch** per avviare il test."
            )
        for e in errors:
            st.error(e)
        if added:
            st.page_link("pages/2_Test_Batch.py", label="→ Vai a Test Batch")
