from __future__ import annotations

import html
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd
import requests
import streamlit as st

if not hasattr(st, "experimental_rerun") and hasattr(st, "rerun"):
    st.experimental_rerun = st.rerun  # type: ignore[attr-defined]

if TYPE_CHECKING:  # pragma: no cover
    from streamlit.runtime.uploaded_file_manager import UploadedFile

from utils.insights import render_discrepancies_panel, show_incremental_insights


API_BASE_URL = st.secrets.get("API_BASE_URL", "http://backend:8000")

PRIMARY_COLOR = "#2563eb"
ACCENT_COLOR = "#38b2ac"
BACKGROUND_COLOR = "#040b18"
TEXT_COLOR = "#eef5ff"

AGENT_STEPS = [
    ("ocr", "1. Ag. OCR"),
    ("auditor", "2. Ag. Auditor"),
    ("classifier", "3. Ag. Classificador"),
    ("intelligence", "4. Ag. Inteligência"),
    ("accountant", "5. Ag. Contador"),
]

EXPORT_ENDPOINTS = {
    "docx": ("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "relatorio.docx"),
    "html": ("html", "text/html", "relatorio.html"),
    "pdf": ("pdf", "application/pdf", "relatorio.pdf"),
    "md": ("md", "text/markdown", "relatorio.md"),
    "sped": ("sped", "text/plain", "sped_efd.txt"),
}

INITIAL_CHAT_MESSAGE = {
    "id": "assistant-hello",
    "sender": "ai",
    "text": "Olá! Posso ajudar a interpretar os resultados fiscais. Faça uma pergunta ou envie novos documentos.",
}


def _format_brl(value: float) -> str:
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _format_file_size(size_bytes: Optional[float]) -> str:
    if size_bytes is None:
        return "-"
    return f"{size_bytes / 1024:.1f} KB"


def _prepare_payload(file: "UploadedFile") -> Tuple[str, bytes, str]:
    return file.name, file.getvalue(), file.type or "application/octet-stream"


def _set_toast(message: Optional[str], level: str = "error") -> None:
    st.session_state["toast"] = {"message": message, "level": level} if message else None


def _clear_analysis_state() -> None:
    st.session_state["analysis_results"] = []
    st.session_state["aggregated_overview"] = None
    st.session_state["aggregated_totals"] = {}
    st.session_state["aggregated_docs"] = []
    st.session_state["logs_payload"] = []


def process_uploaded_file(payload: Tuple[str, bytes, str]) -> Dict[str, Any]:
    name, content, mime = payload
    endpoint = f"{API_BASE_URL}/upload/file"
    if name.lower().endswith(".zip"):
        endpoint = f"{API_BASE_URL}/upload/zip"
    response = requests.post(endpoint, files={"file": (name, content, mime)}, timeout=300)
    response.raise_for_status()
    return response.json()


def _trigger_export(fmt: str, dataset: Dict[str, Any]) -> None:
    if fmt not in EXPORT_ENDPOINTS:
        _set_toast(f"Formato de exportação desconhecido: {fmt}")
        return
    endpoint, mime, default_name = EXPORT_ENDPOINTS[fmt]
    try:
        response = requests.post(
            f"{API_BASE_URL}/export/{endpoint}",
            json={"dataset": dataset},
            timeout=120,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        _set_toast(f"Falha ao exportar ({fmt.upper()}): {exc}")
        return
    filename = dataset.get("title") or default_name
    st.download_button(
        label=f"Baixar {fmt.upper()}",
        data=response.content,
        mime=mime,
        file_name=filename if filename else default_name,
        key=f"download-{fmt}",
    )


def _init_session_state() -> None:
    defaults: Dict[str, Any] = {
        "pipelineStep": "UPLOAD",
        "activeView": "report",
        "showLogs": False,
        "upload_queue": [],
        "analysis_results": [],
        "aggregated_overview": None,
        "aggregated_totals": {},
        "aggregated_docs": [],
        "logs_payload": [],
        "agent_status": {step_id: "pending" for step_id, _ in AGENT_STEPS},
        "processing_status": "",
        "chat_messages": [dict(INITIAL_CHAT_MESSAGE)],
        "chat_streaming": False,
        "toast": None,
        "comparison_result": None,
        "analysis_history": [],
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value if not isinstance(value, list) else list(value)


def _inject_theme() -> None:
    st.set_page_config(
        page_title="Nexus QuantumI2A2",
        page_icon="💠",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    assets_path = Path(__file__).parent / "assets" / "theme.css"
    if assets_path.exists():
        st.markdown(f"<style>{assets_path.read_text()}</style>", unsafe_allow_html=True)

    css_template = Template("""
    <style>
        header, [data-testid="stSidebar"], [data-testid="collapsedControl"], [data-testid="stToolbar"] {
            display: none !important;
        }
        body {
            background: $background;
            color: $text;
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        }
        [data-testid="stAppViewContainer"] > .main {
            background: $background;
        }
        .block-container {
            padding: 0 2.4rem 4rem;
            max-width: 1180px;
            margin: 0 auto;
        }
        .nxq-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 20px 0 18px;
            margin-bottom: 26px;
            border-bottom: 1px solid rgba(130, 160, 210, 0.25);
        }
        .nxq-brand { display: flex; align-items: center; gap: 18px; }
        .nxq-brand-logo {
            width: 56px;
            height: 56px;
            border-radius: 16px;
            border: 1px solid rgba(118, 227, 255, 0.45);
            background: linear-gradient(140deg, rgba(59, 130, 246, 0.4), rgba(20, 184, 166, 0.4));
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 9px;
            box-shadow: 0 14px 30px rgba(3, 11, 28, 0.55);
        }
        .nxq-brand-logo svg { width: 100%; height: 100%; }
        .nxq-brand-title {
            margin: 0;
            font-size: 1.9rem;
            font-weight: 700;
            background: linear-gradient(100deg, #9fdcff 0%, #6ee7d7 70%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .nxq-brand-subtitle {
            margin: 2px 0 0;
            font-size: 0.95rem;
            color: rgba(198, 212, 238, 0.8);
        }
        .nxq-header-actions { display: flex; align-items: center; gap: 12px; }
        .nxq-header-actions .stButton button {
            border-radius: 12px;
            border: 1px solid rgba(118, 158, 238, 0.35);
            background: rgba(14, 24, 50, 0.9);
            color: #d8e6ff;
            font-weight: 600;
            padding: 0.4rem 0.9rem;
        }
        .nxq-export-group { display: flex; gap: 8px; }
        .nxq-export-group .stButton button {
            width: 48px;
            height: 48px;
            border-radius: 14px;
            border: 1px solid rgba(118, 180, 255, 0.35);
            background: rgba(23, 36, 64, 0.92);
            color: #cfe4ff;
            font-weight: 700;
        }
        .nxq-upload-wrapper { display: flex; justify-content: center; margin-top: 20px; }
        .nxq-upload-card {
            max-width: 640px;
            width: 100%;
            background: rgba(13, 22, 38, 0.94);
            border: 1px solid rgba(118, 160, 210, 0.32);
            border-radius: 22px;
            padding: 36px 44px;
            box-shadow: 0 24px 46px rgba(3, 10, 28, 0.55);
        }
        .nxq-upload-title { font-size: 1.12rem; font-weight: 600; margin-bottom: 24px; }
        .nxq-dropzone {
            border: 2px dashed rgba(140, 178, 226, 0.45);
            border-radius: 18px;
            background: rgba(8, 14, 26, 0.9);
            padding: 54px 20px 46px;
            display: flex;
            flex-direction: column;
            align-items: center;
            text-align: center;
            gap: 10px;
        }
        .nxq-dropzone svg { display: none; }
        .nxq-dropzone::before { content: "\u2191"; font-size: 2.8rem; color: #8ed7ff; }
        .nxq-dropzone::after { content: "Clique ou arraste novos arquivos"; color: #a9cfff; font-size: 1.05rem; font-weight: 600; }
        .nxq-hint { margin-top: 16px; text-align: center; font-size: 0.88rem; color: rgba(180, 200, 230, 0.78); }
        .nxq-demo-link .stButton button { background: none; border: none; color: #7fb6ff; text-decoration: underline; padding: 0; }
        .nxq-upload-extras {
            max-width: 640px;
            margin: 26px auto 0;
            background: rgba(12, 20, 34, 0.9);
            border: 1px solid rgba(118, 152, 211, 0.3);
            border-radius: 16px;
            padding: 22px 26px;
        }
        .nxq-upload-actions .stButton button { width: 100%; border-radius: 12px; padding: 0.75rem 1rem; font-weight: 600; }
        .nxq-upload-actions .stButton:nth-child(1) button { background: linear-gradient(135deg, rgba(67,97,238,0.92), rgba(56,189,248,0.92)) !important; border: none !important; color: #f9fbff !important; }
        .nxq-upload-actions .stButton:nth-child(2) button { background: rgba(30,41,59,0.9) !important; border: 1px solid rgba(148,163,184,0.35) !important; color: rgba(203,213,225,0.9) !important; }
        .nxq-progress-steps { display: flex; align-items: center; gap: 10px; margin: 32px 0 18px; }
        .nxq-progress-step { display: flex; flex-direction: column; align-items: center; gap: 6px; flex: 1; }
        .nxq-progress-node { width: 48px; height: 48px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: 600; border: 2px solid rgba(125,160,255,0.35); background: rgba(14,26,54,0.9); }
        .nxq-progress-node.running { border-color: rgba(59,130,246,0.7); color: #9fd0ff; }
        .nxq-progress-node.completed { border-color: rgba(34,197,94,0.7); color: #a7f3d0; }
        .nxq-progress-node.error { border-color: rgba(248,113,113,0.8); color: #fecaca; }
        .nxq-progress-label { font-size: 0.82rem; text-align: center; color: rgba(200,210,235,0.85); }
        .nxq-progress-connector { height: 2px; flex: 1; background: linear-gradient(90deg, rgba(59,130,246,0.45), rgba(59,130,246,0.15)); }
        .nxq-view-switcher .stRadio > label { display: none; }
        .nxq-view-switcher .st-bc { display: flex; gap: 12px; flex-wrap: wrap; }
        .nxq-view-switcher [role="radiogroup"] > label { border-radius: 999px; padding: 0.45rem 1.35rem; border: 1px solid rgba(148,163,184,0.35); background: rgba(20,30,48,0.9); font-weight: 500; }
        .nxq-chat-panel { background: rgba(12,20,35,0.92); border: 1px solid rgba(110,145,210,0.28); border-radius: 18px; padding: 1.3rem; box-shadow: 0 18px 38px rgba(3,10,28,0.55); position: sticky; top: 6.5rem; }
        .nxq-chat-messages { max-height: 420px; overflow-y: auto; margin-bottom: 1rem; padding-right: 8px; }
        .nxq-chat-bubble { margin-bottom: 0.8rem; padding: 0.75rem 1rem; border-radius: 14px; line-height: 1.45; font-size: 0.95rem; }
        .nxq-chat-bubble.ai { background: rgba(59,130,246,0.12); border: 1px solid rgba(59,130,246,0.25); }
        .nxq-chat-bubble.user { background: rgba(56,178,172,0.18); border: 1px solid rgba(56,178,172,0.32); }
        .nxq-toast { position: fixed; right: 28px; bottom: 28px; background: rgba(30,41,59,0.95); border: 1px solid rgba(248,113,113,0.4); border-radius: 14px; padding: 0.9rem 1.1rem; display: flex; align-items: center; gap: 10px; box-shadow: 0 15px 30px rgba(3,10,28,0.45); z-index: 99; }
        .nxq-logs-overlay { position: fixed; top: 80px; right: 48px; width: min(420px, 92vw); max-height: 72vh; overflow-y: auto; background: rgba(11,18,32,0.96); border: 1px solid rgba(120,160,210,0.35); border-radius: 16px; padding: 1.4rem; box-shadow: 0 24px 45px rgba(2,8,22,0.6); z-index: 120; }
        .nxq-logs-entry { border-left: 3px solid rgba(59,130,246,0.45); padding: 0.55rem 0.8rem; margin-bottom: 0.6rem; background: rgba(16,24,40,0.85); }
        .nxq-logs-entry small { color: rgba(198,212,238,0.65); display: block; margin-bottom: 3px; }
    </style>
    """)

    css = css_template.substitute(background=BACKGROUND_COLOR, text=TEXT_COLOR)
    st.markdown(css, unsafe_allow_html=True)

def _enqueue_files(files: Iterable["UploadedFile"]) -> Tuple[int, List[str]]:
    added = 0
    duplicates: List[str] = []
    names = {entry["name"] for entry in st.session_state["upload_queue"]}
    for file in files:
        if file.name in names:
            duplicates.append(file.name)
            continue
        payload = _prepare_payload(file)
        st.session_state["upload_queue"].append({"name": file.name, "size": getattr(file, "size", 0), "payload": payload})
        names.add(file.name)
        added += 1
    return added, duplicates


def _clear_upload_queue() -> None:
    st.session_state["upload_queue"] = []


def _update_agent_status(status: str) -> None:
    for key, _ in AGENT_STEPS:
        st.session_state["agent_status"][key] = status


def _aggregate_local(results: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    totals = {"vNF": 0.0, "vProd": 0.0, "vICMS": 0.0, "vPIS": 0.0, "vCOFINS": 0.0}
    docs: List[Dict[str, Any]] = []
    for result in results:
        for report in result.get("reports", []):
            source = report.get("source") or {}
            itens = source.get("itens") or []
            valor_produtos = sum(float(item.get("valor") or 0) for item in itens)
            resumo = (report.get("taxes") or {}).get("resumo") or {}
            totals["vProd"] += valor_produtos
            totals["vNF"] += valor_produtos
            totals["vICMS"] += float(resumo.get("totalICMS") or 0)
            totals["vPIS"] += float(resumo.get("totalPIS") or 0)
            totals["vCOFINS"] += float(resumo.get("totalCOFINS") or 0)
            docs.append({"Documento": report.get("title"), "Valor dos Produtos": valor_produtos, "Score": (report.get("compliance") or {}).get("score")})
    return {"totals": totals, "docs": docs}


def _process_queue() -> None:
    if not st.session_state["upload_queue"]:
        _set_toast("Nenhum arquivo na fila.")
        return
    st.session_state["pipelineStep"] = "PROCESSING"
    st.session_state["processing_status"] = "Iniciando pipeline"
    _update_agent_status("pending")
    st.session_state.pop("_processing_started", None)
    st.experimental_rerun()


def _run_pipeline() -> None:
    queue = list(st.session_state.get("upload_queue") or [])
    if not queue:
        st.session_state["pipelineStep"] = "UPLOAD"
        st.experimental_rerun()
        return
    results: List[Dict[str, Any]] = []
    logs: List[Dict[str, Any]] = []
    errors: List[str] = []
    for index, entry in enumerate(queue, start=1):
        name = entry["name"]
        payload = entry["payload"]
        st.session_state["processing_status"] = f"Processando {index}/{len(queue)}: {name}"
        for step_id, _ in AGENT_STEPS:
            st.session_state["agent_status"][step_id] = "running"
        st.experimental_rerun()
        try:
            raw_result = process_uploaded_file(payload)
            results.append(raw_result)
            logs.extend(raw_result.get("logs") or [])
            for step_id, _ in AGENT_STEPS:
                st.session_state["agent_status"][step_id] = "completed"
        except Exception as exc:
            errors.append(f"{name}: {exc}")
            for step_id, _ in AGENT_STEPS:
                st.session_state["agent_status"][step_id] = "error"
    st.session_state["analysis_results"] = results
    st.session_state["logs_payload"] = logs
    aggregated = _aggregate_local(results)
    st.session_state["aggregated_overview"] = {
        "reports": [r for result in results for r in result.get("reports", [])],
        "docs": aggregated.get("docs", []),
        "totals": aggregated.get("totals", {}),
        "logs": logs,
    }
    st.session_state["aggregated_totals"] = aggregated.get("totals", {})
    st.session_state["aggregated_docs"] = aggregated.get("docs", [])
    st.session_state["upload_queue"] = []
    if errors:
        st.session_state["pipelineStep"] = "ERROR"
        st.session_state["processing_status"] = "\n".join(errors)
    else:
        st.session_state["pipelineStep"] = "COMPLETE"
        st.session_state["analysis_history"].append(aggregated)
    st.experimental_rerun()


def render_header() -> None:
    show_exports = st.session_state["pipelineStep"] == "COMPLETE" and bool(st.session_state.get("aggregated_overview"))
    st.markdown("<div class='nxq-header'>", unsafe_allow_html=True)
    brand_html = """
        <div class='nxq-brand'>
            <div class='nxq-brand-logo'>
                <svg viewBox="0 0 36 36" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <defs>
                        <linearGradient id="nxq-logo-gradient" x1="4" y1="4" x2="32" y2="32" gradientUnits="userSpaceOnUse">
                            <stop stop-color="#60a5fa"/>
                            <stop offset="1" stop-color="#38bdf8"/>
                        </linearGradient>
                    </defs>
                    <path d="M8 28V8L18 18L28 8V28" stroke="url(#nxq-logo-gradient)" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"/>
                    <path d="M8 28L18 18L28 28" stroke="url(#nxq-logo-gradient)" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round" opacity="0.6"/>
                </svg>
            </div>
            <div>
                <h1 class='nxq-brand-title'>Nexus QuantumI2A2</h1>
                <p class='nxq-brand-subtitle'>Interactive Insight & Intelligence from Fiscal Analysis</p>
            </div>
        </div>
    """
    st.markdown(brand_html, unsafe_allow_html=True)
    actions = st.container()
    with actions:
        st.markdown("<div class='nxq-header-actions'>", unsafe_allow_html=True)
        if show_exports:
            reports = st.session_state.get("aggregated_overview", {}).get("reports") or []
            if reports:
                col_select, col_buttons = st.columns([2, 3], gap="small")
                labels = [r.get("title") or f"Documento {i+1}" for i, r in enumerate(reports)]
                with col_select:
                    selection = st.selectbox(
                        "Documento para exportar",
                        labels,
                        index=min(st.session_state.get("selected_export_index", 0), len(labels) - 1),
                        label_visibility="hidden",
                        key="export-selector",
                    )
                    st.session_state["selected_export_index"] = labels.index(selection)
                with col_buttons:
                    st.markdown("<div class='nxq-export-group'>", unsafe_allow_html=True)
                    dataset = reports[st.session_state["selected_export_index"]]
                    cols = st.columns(4)
                    for fmt, col in zip(["pdf", "docx", "html", "md"], cols):
                        with col:
                            if st.button(fmt.upper(), key=f"export-{fmt}"):
                                _trigger_export(fmt, dataset)
                    st.markdown("</div>", unsafe_allow_html=True)
                    if st.button("SPED", key="export-sped"):
                        _trigger_export("sped", dataset)
        if st.button("Logs", key="toggle-logs"):
            st.session_state["showLogs"] = not st.session_state.get("showLogs")
        st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)


def render_toast() -> None:
    toast = st.session_state.get("toast")
    if not toast:
        return
    message = toast.get("message")
    if not message:
        return
    icon = "⚠️" if toast.get("level") == "error" else "ℹ️"
    html_block = f"<div class='nxq-toast'><span>{icon}</span><span>{html.escape(message)}</span></div>"
    st.markdown(html_block, unsafe_allow_html=True)
    st.session_state["toast"] = None


def render_logs_overlay() -> None:
    if not st.session_state.get("showLogs"):
        return
    logs = st.session_state.get("logs_payload") or []
    st.markdown("<div class='nxq-logs-overlay'>", unsafe_allow_html=True)
    st.markdown("### Logs de Execução")
    if not logs:
        st.info("Nenhum log disponível.")
    else:
        for entry in logs[-200:]:
            stamp = entry.get("timestamp") or entry.get("time") or "--"
            level = entry.get("level") or entry.get("levelname") or "INFO"
            message = entry.get("message") or entry.get("msg") or ""
            agent = entry.get("agent") or entry.get("stage") or "pipeline"
            block = f"""<div class='nxq-logs-entry'><small>[{level}] [{agent}] {stamp}</small><div>{html.escape(str(message))}</div></div>"""
            st.markdown(block, unsafe_allow_html=True)
    if st.button("Fechar", key="close-logs"):
        st.session_state["showLogs"] = False
    st.markdown("</div>", unsafe_allow_html=True)


def render_upload_view() -> None:
    render_header()
    st.markdown("<div class='nxq-upload-wrapper'><div class='nxq-upload-card'>", unsafe_allow_html=True)
    st.markdown("<div class='nxq-upload-title'>1. Upload de Arquivos</div>", unsafe_allow_html=True)
    files = st.file_uploader(
        "Selecione arquivos",
        type=["xml", "csv", "xlsx", "pdf", "png", "jpeg", "jpg", "zip"],
        accept_multiple_files=True,
        label_visibility="collapsed",
        key="primary_uploader",
    )
    if files:
        added, duplicates = _enqueue_files(files)
        if added:
            _set_toast(f"{added} arquivo(s) adicionados à fila.", level="info")
        if duplicates:
            _set_toast("Arquivos ignorados: " + ", ".join(duplicates), level="info")
    st.markdown(
        "<p class='nxq-hint'>Suportados: XML, CSV, XLSX, PDF, Imagens (PNG, JPG), ZIP (limite de 200 MB)</p>",
        unsafe_allow_html=True,
    )
    st.markdown("</div></div>", unsafe_allow_html=True)
    st.markdown("<div class='nxq-demo-link'>", unsafe_allow_html=True)
    if st.button("Use um exemplo de demonstração", key="demo-button"):
        _set_toast("Modo demonstração indisponível no momento.", level="info")
    st.markdown("</div>", unsafe_allow_html=True)
    queue = st.session_state.get("upload_queue") or []
    if queue:
        st.markdown("<div class='nxq-upload-extras'>", unsafe_allow_html=True)
        st.markdown("#### Arquivos na fila")
        df = pd.DataFrame([{ "Nome do arquivo": item["name"], "Tamanho": _format_file_size(item["size"])} for item in queue])
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.markdown("<div class='nxq-upload-actions'>", unsafe_allow_html=True)
        col1, col2 = st.columns(2, gap="large")
        with col1:
            st.button(f"Analisar {len(queue)} arquivo(s)", on_click=_process_queue, use_container_width=True)
        with col2:
            st.button("Limpar fila", on_click=_clear_upload_queue, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)


def render_processing_view() -> None:
    render_header()
    status = st.session_state.get("processing_status") or "Aguardando"
    st.write(f"#### {status}")
    st.markdown("<div class='nxq-progress-steps'>", unsafe_allow_html=True)
    for idx, (step_id, label) in enumerate(AGENT_STEPS):
        step_state = st.session_state["agent_status"].get(step_id, "pending")
        node = "✓" if step_state == "completed" else str(idx + 1)
        html_block = f"<div class='nxq-progress-step'><div class='nxq-progress-node {step_state}'>{node}</div><div class='nxq-progress-label'>{label}</div></div>"
        st.markdown(html_block, unsafe_allow_html=True)
        if idx < len(AGENT_STEPS) - 1:
            st.markdown("<div class='nxq-progress-connector'></div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)
    st.progress(0.5)
    if not st.session_state.get("_processing_started"):
        st.session_state["_processing_started"] = True
        _run_pipeline()


def _render_report_tab(aggregated: Dict[str, Any]) -> None:
    display_summary(aggregated)
    reports = aggregated.get("reports") or []
    if not reports:
        st.info("Nenhum relatório disponível.")
        return
    for idx, report in enumerate(reports, start=1):
        with st.expander(report.get("title") or f"Documento {idx}", expanded=idx == 1):
            st.json(report)


def _render_dashboard_tab(aggregated: Dict[str, Any], results: List[Dict[str, Any]]) -> None:
    display_summary(aggregated)
    docs = aggregated.get("docs") or []
    if docs:
        df = pd.DataFrame(docs)
        df["Valor dos Produtos"] = df["Valor dos Produtos"].map(_format_brl)
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("Envie arquivos para gerar métricas.")
    totals = aggregated.get("totals") or {}
    base_icms = float(totals.get("vICMS") or 0.0)
    col_slider, col_metric = st.columns([2, 1])
    with col_slider:
        aliquot = st.slider("Alíquota de ICMS Simulado (%)", 0.0, 30.0, 18.0, 0.5, key="icms-slider")
    with col_metric:
        simulated = base_icms * (aliquot / 18.0) if base_icms else 0.0
        st.metric("ICMS Simulado", _format_brl(simulated), delta=_format_brl(simulated - base_icms))
    show_incremental_insights(results)


def _render_comparative_tab(results: List[Dict[str, Any]]) -> None:
    comparison = st.session_state.get("comparison_result")
    if not comparison:
        st.info("Envie ao menos duas análises para comparação.")
        return
    render_discrepancies_panel(comparison)
    show_incremental_insights(results)


def render_complete_view() -> None:
    render_header()
    aggregated = st.session_state.get("aggregated_overview") or {}
    results = st.session_state.get("analysis_results") or []
    st.markdown("<div class='nxq-view-switcher'>", unsafe_allow_html=True)
    options = [("report", "Relatório de Análise"), ("dashboard", "Dashboard")]
    if len(st.session_state.get("analysis_history", [])) > 1:
        options.append(("comparative", "Análise Comparativa"))
    labels = [label for _, label in options]
    values = [value for value, _ in options]
    selected = st.radio(
        "Visualização",
        labels,
        index=values.index(st.session_state.get("activeView", "report")),
        horizontal=True,
        label_visibility="hidden",
        key="view-switcher-radio",
    )
    st.session_state["activeView"] = values[labels.index(selected)]
    st.markdown("</div>", unsafe_allow_html=True)
    main_col, chat_col = st.columns([2, 1], gap="large")
    with main_col:
        view = st.session_state["activeView"]
        if view == "report":
            _render_report_tab(aggregated)
        elif view == "dashboard":
            _render_dashboard_tab(aggregated, results)
        elif view == "comparative":
            _render_comparative_tab(results)
    with chat_col:
        render_chat_panel()


def render_error_view() -> None:
    render_header()
    st.error("Falha na análise")
    st.write(st.session_state.get("processing_status") or "O pipeline encontrou uma falha.")
    if st.button("Tentar Novamente"):
        st.session_state["pipelineStep"] = "UPLOAD"
        _clear_analysis_state()
        st.experimental_rerun()


def render_chat_panel() -> None:
    st.markdown("<div class='nxq-chat-panel'>", unsafe_allow_html=True)
    st.markdown("### 3. Chat Interativo")
    messages = st.session_state.get("chat_messages", [])
    st.markdown("<div class='nxq-chat-messages'>", unsafe_allow_html=True)
    for message in messages:
        bubble_class = "ai" if message.get("sender") != "user" else "user"
        safe_text = html.escape(message.get("text", "")).replace("\n", "<br>")
        st.markdown(f"<div class='nxq-chat-bubble {bubble_class}'>{safe_text}</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)
    with st.form("chat-form", clear_on_submit=True):
        cols = st.columns([1, 6, 1, 1])
        with cols[0]:
            attachments = st.file_uploader(
                "Adicionar anexos",
                type=["xml", "csv", "xlsx", "pdf", "png", "jpeg", "jpg", "zip"],
                accept_multiple_files=True,
                label_visibility="collapsed",
                key="chat-uploader",
            )
        with cols[1]:
            prompt = st.text_input("", placeholder="Faça uma pergunta ou adicione arquivos…")
        with cols[2]:
            send = st.form_submit_button("Enviar", use_container_width=True)
        with cols[3]:
            st.form_submit_button("Parar", disabled=not st.session_state.get("chat_streaming"))
    if attachments:
        added, duplicates = _enqueue_files(attachments)
        if added:
            _set_toast(f"{added} arquivo(s) adicionados à fila. Volte ao upload para reprocessar.", level="info")
        if duplicates:
            _set_toast("Arquivos ignorados: " + ", ".join(duplicates), level="info")
    if send and prompt.strip():
        st.session_state["chat_messages"].append({"id": f"user-{len(messages)}", "sender": "user", "text": prompt})
        st.session_state["chat_messages"].append({"id": f"ai-{len(messages)+1}", "sender": "ai", "text": "Esta é uma resposta estática de exemplo. Integre a IA para respostas dinâmicas."})
        st.experimental_rerun()
    st.markdown("</div>", unsafe_allow_html=True)


def display_summary(aggregated: Dict[str, Any]) -> None:
    totals = aggregated.get("totals", {})
    docs = aggregated.get("docs", [])
    metrics = [
        ("Documentos", f"{len(docs)}"),
        ("Valor Total dos Produtos", _format_brl(totals.get("vProd", 0.0))),
        ("ICMS Estimado", _format_brl(totals.get("vICMS", 0.0))),
    ]
    cols = st.columns(len(metrics))
    for col, (label, value) in zip(cols, metrics):
        col.metric(label, value)


def render_toast_and_logs() -> None:
    render_toast()
    render_logs_overlay()


def main() -> None:
    _init_session_state()
    _inject_theme()
    render_toast_and_logs()
    step = st.session_state.get("pipelineStep", "UPLOAD")
    if step == "UPLOAD":
        render_upload_view()
    elif step == "PROCESSING":
        render_processing_view()
    elif step == "COMPLETE":
        render_complete_view()
    elif step == "ERROR":
        render_error_view()
    else:
        st.session_state["pipelineStep"] = "UPLOAD"
        st.experimental_rerun()


main()
