import time

import requests
import streamlit as st

from components.ui_inject import inject_theme

API = st.secrets.get("API_BASE_URL", "http://backend:8000")
inject_theme()
st.title("Upload & Auditoria")


def _animate_logs(logs):
    if not logs:
        return
    events = []
    for entry in logs:
        for event in entry.get("events", []):
            enriched = dict(event)
            enriched["document_id"] = entry.get("document_id")
            events.append(enriched)
    if not events:
        return
    progress = st.progress(0)
    placeholder = st.empty()
    total = max(len(events), 1)
    for idx, event in enumerate(events, start=1):
        progress.progress(idx / total)
        placeholder.info(
            f"{event.get('document_id', 'doc')} · {event.get('stage')} → {event.get('status')} ({event.get('duration')} s)"
        )
        time.sleep(0.1)
    progress.empty()


def _dispatch(endpoint: str, payload):
    with st.spinner("Processando..."):
        response = requests.post(endpoint, **payload, timeout=300)
        response.raise_for_status()
        body = response.json()
        st.session_state["reports"] = body.get("reports", [])
        st.session_state["processing_logs"] = body.get("logs", [])
        aggregated = body.get("aggregated") or {}
        st.session_state["aggregated_totals"] = aggregated.get("totals", {})
        st.session_state["aggregated_docs"] = aggregated.get("docs", [])
        _animate_logs(body.get("logs", []))
        st.success("Processado! Vá para 'Relatórios & Exportação'.")


tab1, tab2, tab3 = st.tabs(["Upload ZIP", "Upload Arquivo Único", "Upload Múltiplo"])

with tab1:
    zip_file = st.file_uploader("Selecione um .zip (até 200 MB)", type=["zip"], key="zip")
    if st.button("Enviar ZIP", type="primary") and zip_file:
        _dispatch(
            f"{API}/upload/zip",
            {"files": {"file": (zip_file.name, zip_file.getvalue(), "application/zip")}},
        )

with tab2:
    f = st.file_uploader(
        "Selecione um arquivo",
        type=["xml", "csv", "xlsx", "pdf", "png", "jpg", "jpeg"],
        key="single",
    )
    if st.button("Enviar Arquivo", type="primary") and f:
        _dispatch(
            f"{API}/upload/file",
            {"files": {"file": (f.name, f.getvalue(), f.type or "application/octet-stream")}},
        )

with tab3:
    files = st.file_uploader(
        "Selecione múltiplos arquivos",
        type=["xml", "csv", "xlsx", "pdf", "png", "jpg", "jpeg", "zip"],
        accept_multiple_files=True,
        key="batch",
    )
    if st.button("Enviar em Lote", type="primary", key="send-multi") and files:
        payload = [
            (
                "files",
                (file.name, file.getvalue(), file.type or "application/octet-stream"),
            )
            for file in files
        ]
        _dispatch(f"{API}/upload/multiple", {"files": payload})

st.divider()
st.subheader("Logs mais recentes")
logs = st.session_state.get("processing_logs", [])
if logs:
    st.dataframe(
        [
            {
                "Documento": report.get("title"),
                "ID": report.get("documentId"),
                "Etapa": event.get("stage"),
                "Status": event.get("status"),
                "Início": event.get("started_at"),
                "Duração": event.get("duration"),
            }
            for report in st.session_state.get("reports", [])
            for event in report.get("logs", [])
        ]
        or logs,
        use_container_width=True,
    )
else:
    st.info("Faça um processamento para visualizar os logs em tempo real.")
