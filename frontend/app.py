from __future__ import annotations

import html
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Tuple

import pandas as pd
import requests
import streamlit as st

# Backward compatibility for Streamlit rerun API changes
if not hasattr(st, "experimental_rerun") and hasattr(st, "rerun"):
    st.experimental_rerun = st.rerun  # type: ignore[attr-defined]

if TYPE_CHECKING:  # pragma: no cover - hints only
    from streamlit.runtime.uploaded_file_manager import UploadedFile

from utils.insights import render_discrepancies_panel, show_incremental_insights


API_BASE_URL = st.secrets.get("API_BASE_URL", "http://backend:8000")

PRIMARY_COLOR = "#2563eb"  # Tailwind blue-600
ACCENT_COLOR = "#38b2ac"  # Tailwind teal-400
BACKGROUND_COLOR = "#111827"  # Tailwind gray-900
TEXT_COLOR = "#f3f4f6"  # Tailwind gray-100

AGENT_STEPS = ["OCR", "Auditor", "Classificador", "Contador"]
EXPORT_ENDPOINTS = {
    "DOCX": ("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "relatorio.docx"),
    "PDF": ("pdf", "application/pdf", "relatorio.pdf"),
    "HTML": ("html", "text/html", "relatorio.html"),
    "SPED": ("sped", "text/plain", "sped_efd.txt"),
}

INITIAL_CHAT_MESSAGE = {
    "role": "assistant",
    "content": (
        "Ola! Carregue seus arquivos fiscais para comecar a analise. "
        "Voce pode enviar novos documentos a qualquer momento pelo painel de conversa."
    ),
}


def _format_brl(value: float) -> str:
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _prepare_payload(file: "UploadedFile") -> Tuple[str, bytes, str]:
    return file.name, file.getvalue(), file.type or "application/octet-stream"


def process_uploaded_file(payload: Tuple[str, bytes, str]) -> Dict[str, Any]:
    name, content, mime = payload
    endpoint = f"{API_BASE_URL}/upload/file"
    if name.lower().endswith(".zip"):
        endpoint = f"{API_BASE_URL}/upload/zip"

    response = requests.post(
        endpoint,
        files={"file": (name, content, mime)},
        timeout=300,
    )
    response.raise_for_status()
    return response.json()


def aggregate_results(responses: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    reports: List[Dict[str, Any]] = []
    logs: List[Dict[str, Any]] = []
    docs: List[Dict[str, Any]] = []
    totals = {"vNF": 0.0, "vProd": 0.0, "vICMS": 0.0, "vPIS": 0.0, "vCOFINS": 0.0}

    for response in responses:
        current_reports = response.get("reports") or []
        current_logs = response.get("logs") or []
        reports.extend(current_reports)
        logs.extend(current_logs)

        for report in current_reports:
            source = report.get("source") or {}
            itens = source.get("itens") or []
            valor_produtos = sum(float(item.get("valor") or 0) for item in itens)
            taxes_resumo = ((report.get("taxes") or {}).get("resumo") or {})

            totals["vProd"] += valor_produtos
            totals["vNF"] += valor_produtos
            totals["vICMS"] += float(taxes_resumo.get("totalICMS") or 0)
            totals["vPIS"] += float(taxes_resumo.get("totalPIS") or 0)
            totals["vCOFINS"] += float(taxes_resumo.get("totalCOFINS") or 0)

            docs.append(
                {
                    "documento": report.get("title"),
                    "itens": len(itens),
                    "valor_produtos": valor_produtos,
                    "score": (report.get("compliance") or {}).get("score"),
                }
            )

    return {"reports": reports, "logs": logs, "docs": docs, "totals": totals}


def _enqueue_files(files: Iterable["UploadedFile"]) -> Tuple[int, List[str]]:
    added = 0
    duplicates: List[str] = []
    queue_meta = st.session_state.setdefault("uploaded_queue_meta", [])
    existing_names = set(st.session_state.get("uploaded_names", []))

    for file in files:
        if file.name not in existing_names:
            payload = _prepare_payload(file)
            st.session_state["uploaded_payloads"].append(payload)
            st.session_state["uploaded_names"].append(file.name)
            queue_meta.append({"name": file.name, "size": getattr(file, "size", 0)})
            added += 1
            existing_names.add(file.name)
        else:
            duplicates.append(file.name)
    return added, duplicates


def _first_non_empty(itens: Iterable[Dict[str, Any]], keys: Iterable[str]) -> str:
    for item in itens:
        for key in keys:
            value = item.get(key)
            if value:
                return str(value)
    return ""


def _prepare_docs_for_comparison(results: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    docs: List[Dict[str, Any]] = []
    for result in results:
        reports = result.get("reports") or []
        file_source = result.get("source")
        for report in reports:
            source_snapshot = report.get("source") or {}
            itens = source_snapshot.get("itens") or []
            totals = report.get("taxes") or {}
            resumo = totals.get("resumo") or {}
            classification = report.get("classification") or {}

            valor_produtos = 0.0
            for item in itens:
                try:
                    valor_produtos += float(item.get("valor") or 0.0)
                except (TypeError, ValueError):
                    continue

            icms_total = float(resumo.get("totalICMS") or 0.0)
            pis_total = float(resumo.get("totalPIS") or 0.0)
            cofins_total = float(resumo.get("totalCOFINS") or 0.0)

            aliquota_icms = icms_total / valor_produtos if valor_produtos else 0.0
            aliquota_pis = pis_total / valor_produtos if valor_produtos else 0.0
            aliquota_cofins = cofins_total / valor_produtos if valor_produtos else 0.0

            doc_entry = {
                "source": file_source or report.get("title"),
                "emitente": classification.get("emitente")
                or (source_snapshot.get("emitente") or {}).get("nome"),
                "cfop": classification.get("cfop") or _first_non_empty(itens, ["cfop"]),
                "cst": _first_non_empty(itens, ["cst", "cst_icms", "cstIcms"]),
                "ncm": classification.get("ncm") or _first_non_empty(itens, ["ncm"]),
                "regime": totals.get("regime"),
                "aliquota_icms": aliquota_icms,
                "aliquota_pis": aliquota_pis,
                "aliquota_cofins": aliquota_cofins,
                "vNF": valor_produtos,
                "vProd": valor_produtos,
                "vICMS": icms_total,
                "vPIS": pis_total,
                "vCOFINS": cofins_total,
            }
            docs.append(doc_entry)
    return docs


def _render_chat_history(messages: Iterable[Dict[str, str]]) -> str:
    rows: List[str] = []
    for message in messages:
        role = message.get("role", "assistant")
        role_class = "user" if role == "user" else "assistant"
        label = "Voce" if role == "user" else "Nexus"
        safe_content = html.escape(message.get("content", "")).replace("\n", "<br>")
        rows.append(
            """
            <div class='chat-bubble chat-bubble--{role_class}'>
                <span class='chat-meta'>{label}</span>
                <p>{safe}</p>
            </div>
            """.format(role_class=role_class, label=label, safe=safe_content)
        )
    if not rows:
        rows.append(
            "<div class='chat-placeholder'>Envie uma pergunta ou anexe novos arquivos para complementar a analise.</div>"
        )
    return "<div class='chat-history'>" + "".join(rows) + "</div>"


def _build_chat_reply(prompt: str) -> str:
    prompt = prompt.strip()
    aggregated = st.session_state.get("aggregated_overview")
    if aggregated:
        totals = aggregated.get("totals", {})
        docs = aggregated.get("docs", [])
        summary_parts = [
            f"Acompanhamos {len(docs)} documento(s) consolidados.",
            f"O valor total dos produtos esta em {_format_brl(totals.get('vProd', 0.0))}.",
        ]
        if totals.get("vICMS"):
            summary_parts.append(f"A projecao de ICMS soma {_format_brl(totals.get('vICMS', 0.0))}.")
        return "\n\n".join([f'Mensagem recebida: "{prompt}"', *summary_parts])
    return (
        "Mensagem recebida, mas ainda nao ha resultados processados. "
        "Adicione arquivos e execute a analise incremental para obter respostas contextualizadas."
    )


def display_summary(aggregated: Dict[str, Any]) -> None:
    totals = aggregated.get("totals", {})
    docs = aggregated.get("docs", [])

    metrics = [
        ("Documentos processados", f"{len(docs)}"),
        ("Valor total dos produtos", _format_brl(totals.get("vProd", 0.0))),
        ("ICMS estimado", _format_brl(totals.get("vICMS", 0.0))),
    ]

    columns = st.columns(len(metrics))
    for column, (label, value) in zip(columns, metrics):
        column.markdown(
            f"""
            <div class="metric-box">
                <span class="metric-label">{label}</span>
                <div class="metric-value">{value}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    if docs:
        df = pd.DataFrame(docs)
        df.rename(
            columns={
                "documento": "Documento",
                "itens": "Itens",
                "valor_produtos": "Valor dos Produtos",
                "score": "Score",
            },
            inplace=True,
        )
        formatted = df.assign(
            **{
                "Valor dos Produtos": df["Valor dos Produtos"].map(_format_brl),
                "Score": df["Score"].map(lambda x: f"{x:.2f}" if x is not None else "-"),
            }
        )
        st.dataframe(formatted, use_container_width=True)
    else:
        st.info("Nenhum documento valido foi consolidado ate o momento.")


def _slugify(text: str) -> str:
    cleaned = "".join(char.lower() if char.isalnum() else "_" for char in text)
    slug = "_".join(filter(None, cleaned.split("_")))
    return slug or "relatorio"


def _build_markdown_export(dataset: Dict[str, Any]) -> Tuple[bytes, str, str]:
    title = dataset.get("title") or "Relatorio Fiscal"
    totals = (dataset.get("taxes") or {}).get("resumo") or {}
    compliance = dataset.get("compliance") or {}
    inconsistencies = compliance.get("inconsistencies") or []

    lines = [
        f"# {title}",
        "",
        "## Resumo de tributos",
    ]
    if totals:
        for key, value in totals.items():
            lines.append(f"- {key}: {value}")
    else:
        lines.append("- Totais nao informados.")

    lines.append("")
    lines.append("## Inconsistencias")
    if inconsistencies:
        for item in inconsistencies:
            code = item.get("code") or "-"
            message = item.get("message") or "-"
            severity = item.get("severity") or "-"
            lines.append(f"- [{severity}] {code}: {message}")
    else:
        lines.append("- Nenhuma inconsistencia registrada.")

    content = "\n".join(lines)
    filename = f"{_slugify(title)}.md"
    return content.encode("utf-8"), "text/markdown", filename


def _reset_app_state(preserve_chat: bool = True) -> None:
    previous_chat = st.session_state.get("chat_messages") if preserve_chat else None
    st.session_state.clear()
    st.session_state["pipelineStep"] = "UPLOAD"
    st.session_state["activeView"] = "report"
    st.session_state["uploaded_payloads"] = []
    st.session_state["uploaded_names"] = []
    st.session_state["uploaded_queue_meta"] = []
    st.session_state["analysis_results"] = []
    st.session_state["aggregated_overview"] = None
    st.session_state["aggregated_totals"] = {}
    st.session_state["aggregated_docs"] = []
    st.session_state["analysis_errors"] = []
    st.session_state["analysis_completed"] = False
    st.session_state["chat_messages"] = (
        [dict(item) for item in previous_chat] if previous_chat else [dict(INITIAL_CHAT_MESSAGE)]
    )
    st.session_state["chat_feedback"] = None
    st.session_state["comparison_result"] = None
    st.session_state["comparison_signature"] = ""
    st.session_state["show_logs_panel"] = False
    st.session_state["agent_status"] = {agent: "pending" for agent in AGENT_STEPS}
    st.session_state["last_export"] = None
    st.session_state["processing_status"] = ""
    st.session_state["demo_loaded"] = False
    st.session_state["chat_streaming"] = False
    st.session_state["selected_report_index"] = 0


def _ensure_state_defaults() -> None:
    state_defaults: Dict[str, Any] = {
        "pipelineStep": "UPLOAD",
        "activeView": "report",
        "uploaded_payloads": [],
        "uploaded_names": [],
        "uploaded_queue_meta": [],
        "analysis_results": [],
        "aggregated_overview": None,
        "aggregated_totals": {},
        "aggregated_docs": [],
        "analysis_errors": [],
        "analysis_completed": False,
        "chat_messages": [dict(INITIAL_CHAT_MESSAGE)],
        "chat_feedback": None,
        "comparison_result": None,
        "comparison_signature": "",
        "show_logs_panel": False,
        "agent_status": {agent: "pending" for agent in AGENT_STEPS},
        "last_export": None,
        "processing_status": "",
        "demo_loaded": False,
        "chat_streaming": False,
        "selected_report_index": 0,
    }
    for key, default in state_defaults.items():
        if key not in st.session_state:
            if isinstance(default, list):
                if default and isinstance(default[0], dict):
                    st.session_state[key] = [dict(item) for item in default]
                else:
                    st.session_state[key] = list(default)
            elif isinstance(default, dict):
                st.session_state[key] = dict(default)
            else:
                st.session_state[key] = default
    for agent in AGENT_STEPS:
        st.session_state["agent_status"].setdefault(agent, "pending")


def _inject_theme() -> None:
    st.set_page_config(page_title="Nexus QuantumI2A2", page_icon="NQ", layout="wide")

    assets_path = Path(__file__).parent / "assets" / "theme.css"
    if assets_path.exists():
        st.markdown(f"<style>{assets_path.read_text()}</style>", unsafe_allow_html=True)

    css = """
    <style>
        :root {{
            --nxq-primary: {primary};
            --nxq-accent: {accent};
            --nxq-bg: {background};
            --nxq-text: {text};
        }}
        body {{
            background: var(--nxq-bg);
            color: var(--nxq-text);
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        }}
        [data-testid="stHeader"] {{
            background: transparent;
        }}
        .block-container {{
            padding-top: 0.75rem;
            max-width: 1200px;
        }}
        .nxq-header {{
            position: sticky;
            top: 0;
            z-index: 50;
            background: rgba(17, 24, 39, 0.92);
            backdrop-filter: blur(14px);
            border: 1px solid rgba(59, 130, 246, 0.25);
            border-radius: 0 0 18px 18px;
            padding: 1.25rem 1.5rem 1.1rem;
            margin-bottom: 1.75rem;
            box-shadow: 0 14px 28px rgba(2, 6, 23, 0.48);
        }}
        .nxq-header-grid {{
            display: flex;
            justify-content: space-between;
            gap: 1.5rem;
            flex-wrap: wrap;
            align-items: center;
        }}
        .nxq-header-brand {{
            display: flex;
            align-items: center;
            gap: 1rem;
        }}
        .nxq-logo {{
            width: 44px;
            height: 44px;
            border-radius: 12px;
            background: linear-gradient(135deg, var(--nxq-primary), var(--nxq-accent));
            display: flex;
            align-items: center;
            justify-content: center;
            color: #0b1220;
            font-weight: 700;
            font-size: 1.1rem;
        }}
        .nxq-header-brand h2 {{
            margin: 0;
            font-size: 1.35rem;
            letter-spacing: 0.04em;
        }}
        .nxq-header-brand p {{
            margin: 0;
            opacity: 0.7;
            font-size: 0.9rem;
        }}
        .nxq-status-chip {{
            display: inline-flex;
            align-items: center;
            gap: 0.45rem;
            padding: 0.4rem 0.8rem;
            border-radius: 999px;
            background: rgba(37, 99, 235, 0.18);
            border: 1px solid rgba(37, 99, 235, 0.35);
            font-size: 0.8rem;
            letter-spacing: 0.05em;
            text-transform: uppercase;
        }}
        .nxq-actions {{
            display: flex;
            flex-direction: column;
            gap: 0.5rem;
            margin-top: 1rem;
        }}
        .nxq-upload {{
            border: 2px dashed rgba(148, 163, 184, 0.35);
            border-radius: 18px;
            padding: 2rem;
            text-align: center;
            background: rgba(15, 23, 42, 0.6);
            transition: border 0.3s ease, background 0.3s ease;
        }}
        .nxq-upload:hover {{
            border-color: var(--nxq-primary);
            background: rgba(37, 99, 235, 0.18);
        }}
        .nxq-upload-help {{
            font-size: 0.9rem;
            opacity: 0.7;
            margin-top: 0.75rem;
        }}
        .metric-box {{
            background: rgba(15, 23, 42, 0.8);
            padding: 1rem;
            border-radius: 14px;
            border: 1px solid rgba(148, 163, 184, 0.25);
            text-align: center;
        }}
        .metric-label {{
            display: block;
            font-size: 0.8rem;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            opacity: 0.6;
            margin-bottom: 0.4rem;
        }}
        .metric-value {{
            font-size: 1.6rem;
            font-weight: 700;
            color: var(--nxq-primary);
        }}
        .nxq-agent-card {{
            border: 1px solid rgba(148, 163, 184, 0.3);
            border-radius: 14px;
            padding: 1rem;
            background: rgba(15, 23, 42, 0.7);
            text-align: center;
            min-height: 110px;
        }}
        .nxq-agent-card strong {{
            display: block;
            margin-bottom: 0.35rem;
            font-size: 0.95rem;
        }}
        .nxq-agent-status {{
            display: inline-flex;
            align-items: center;
            gap: 0.4rem;
            font-size: 0.82rem;
            padding: 0.25rem 0.6rem;
            border-radius: 999px;
            background: rgba(37, 99, 235, 0.18);
        }}
        .nxq-agent-status.running {{
            background: rgba(56, 178, 172, 0.18);
        }}
        .nxq-agent-status.completed {{
            background: rgba(22, 163, 74, 0.2);
        }}
        .nxq-agent-status.error {{
            background: rgba(239, 68, 68, 0.2);
        }}
        .nxq-view-tabs .st-bc {{
            display: flex;
            flex-wrap: wrap;
            gap: 0.5rem;
        }}
        .nxq-view-tabs .st-bc div[role="radiogroup"] > label {{
            border: 1px solid rgba(148, 163, 184, 0.35);
            border-radius: 999px;
            padding: 0.4rem 1.1rem;
            background: rgba(15, 23, 42, 0.8);
            cursor: pointer;
        }}
        .nxq-view-tabs .st-bc div[role="radiogroup"] > label:hover {{
            border-color: var(--nxq-primary);
        }}
        .nxq-sticky-chat {{
            position: sticky;
            top: 6.75rem;
        }}
        .chat-panel {{
            background: rgba(15, 23, 42, 0.85);
            border-radius: 18px;
            border: 1px solid rgba(148, 163, 184, 0.25);
            padding: 1.25rem;
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.05);
        }}
        .chat-history {{
            max-height: 360px;
            overflow-y: auto;
            margin-bottom: 1rem;
            padding-right: 0.4rem;
        }}
        .chat-bubble {{
            padding: 0.75rem 1rem;
            border-radius: 12px;
            margin-bottom: 0.6rem;
            font-size: 0.95rem;
            border: 1px solid rgba(148, 163, 184, 0.25);
        }}
        .chat-bubble--assistant {{
            background: rgba(37, 99, 235, 0.12);
        }}
        .chat-bubble--user {{
            background: rgba(56, 178, 172, 0.12);
        }}
        .chat-meta {{
            display: block;
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            opacity: 0.65;
            margin-bottom: 0.25rem;
        }}
        .chat-placeholder {{
            padding: 1rem;
            border-radius: 12px;
            border: 1px dashed rgba(148, 163, 184, 0.3);
            text-align: center;
            opacity: 0.7;
        }}
        .nxq-modal {{
            position: fixed;
            top: 76px;
            right: 48px;
            width: min(420px, 90vw);
            max-height: 70vh;
            overflow-y: auto;
            background: rgba(15, 23, 42, 0.96);
            border: 1px solid rgba(148, 163, 184, 0.35);
            border-radius: 16px;
            padding: 1.25rem;
            box-shadow: 0 20px 45px rgba(2, 6, 23, 0.55);
            z-index: 100;
        }}
        .nxq-modal h4 {{
            margin-top: 0;
            margin-bottom: 0.75rem;
        }}
        .nxq-log-item {{
            border-left: 3px solid rgba(37, 99, 235, 0.4);
            padding: 0.5rem 0.75rem;
            margin-bottom: 0.5rem;
            background: rgba(17, 24, 39, 0.8);
        }}
        .nxq-log-item small {{
            display: block;
            opacity: 0.6;
            font-size: 0.75rem;
        }}
    </style>
    """.format(
        primary=PRIMARY_COLOR,
        accent=ACCENT_COLOR,
        background=BACKGROUND_COLOR,
        text=TEXT_COLOR,
    )
    st.markdown(css, unsafe_allow_html=True)


def _prepare_report_choices() -> List[Tuple[str, Dict[str, Any]]]:
    choices: List[Tuple[str, Dict[str, Any]]] = []
    results = st.session_state.get("analysis_results", [])
    for result_index, result in enumerate(results, start=1):
        for report_index, report in enumerate(result.get("reports") or [], start=1):
            title = report.get("title") or result.get("source") or f"Documento {report_index}"
            label = f"{result_index}.{report_index} - {title}"
            choices.append((label, report))
    return choices


def _trigger_export(format_id: str, dataset: Dict[str, Any]) -> None:
    try:
        if format_id == "MD":
            data, mime, filename = _build_markdown_export(dataset)
        else:
            endpoint, mime, default_name = EXPORT_ENDPOINTS.get(format_id, (None, None, None))
            if not endpoint:
                st.toast(f"Formato de exportacao desconhecido: {format_id}")
                return
            response = requests.post(
                f"{API_BASE_URL}/export/{endpoint}",
                json={"dataset": dataset},
                timeout=120,
            )
            response.raise_for_status()
            data = response.content
            stem = _slugify(dataset.get("title") or "relatorio")
            extension = default_name.split(".")[-1]
            filename = f"{stem}.{extension}"
        st.session_state["last_export"] = {
            "format": format_id,
            "data": data,
            "mime": mime,
            "name": filename,
        }
        st.toast(f"Exportacao {format_id} pronta para download.")
    except requests.RequestException as exc:
        st.toast(f"Falha na exportacao {format_id}: {exc}")


def _agent_card_html(agent: str, status: str) -> str:
    icon_map = {"pending": "...", "running": ">>", "completed": "ok", "error": "!!"}
    label_map = {
        "pending": "Pendente",
        "running": "Processando",
        "completed": "Concluido",
        "error": "Erro",
    }
    status_class = status if status in {"running", "completed", "error"} else "pending"
    icon = icon_map.get(status, "...")
    label = label_map.get(status, status.title())
    return (
        f"<div class='nxq-agent-card'><strong>{agent}</strong>"
        f"<span class='nxq-agent-status {status_class}'>{icon} {label}</span></div>"
    )


def _render_header() -> None:
    pipeline_step = st.session_state.get("pipelineStep", "UPLOAD")
    current_view = st.session_state.get("activeView", "report")
    report_choices = _prepare_report_choices()

    with st.container():
        st.markdown("<div class='nxq-header'>", unsafe_allow_html=True)
        st.markdown("<div class='nxq-header-grid'>", unsafe_allow_html=True)
        cols = st.columns([3, 2], gap="large")
        with cols[0]:
            st.markdown(
                "<div class='nxq-header-brand'>"
                "<div class='nxq-logo'>NQ</div>"
                "<div>"
                "<h2>Nexus QuantumI2A2</h2>"
                "<p>SPA fiscal interativa orquestrada por IA multiagente.</p>"
                "</div>"
                "</div>",
                unsafe_allow_html=True,
            )
        with cols[1]:
            status_text = {
                "UPLOAD": "Upload",
                "PROCESSING": "Processando",
                "COMPLETE": "Concluido",
                "ERROR": "Erro",
            }.get(pipeline_step, pipeline_step)
            st.markdown(
                f"<span class='nxq-status-chip'>Etapa atual: {status_text}</span>",
                unsafe_allow_html=True,
            )
            toggle_label = "Ocultar logs" if st.session_state.get("show_logs_panel") else "Ver logs"
            if st.button(toggle_label, key="toggle_logs"):
                st.session_state["show_logs_panel"] = not st.session_state.get("show_logs_panel")
                st.experimental_rerun()
        st.markdown("</div>", unsafe_allow_html=True)

        if pipeline_step == "COMPLETE" and current_view == "report" and report_choices:
            st.markdown("<div class='nxq-actions'>", unsafe_allow_html=True)
            action_cols = st.columns([2, 3], gap="small")
            labels = [label for label, _ in report_choices]
            default_index = min(st.session_state.get("selected_report_index", 0), len(labels) - 1)
            with action_cols[0]:
                selection = st.selectbox(
                    "Documento para exportar",
                    labels,
                    index=default_index,
                    label_visibility="collapsed",
                )
            selected_index = labels.index(selection)
            st.session_state["selected_report_index"] = selected_index
            dataset = report_choices[selected_index][1]
            with action_cols[1]:
                export_labels = ["PDF", "DOCX", "HTML", "MD", "SPED"]
                export_cols = st.columns(len(export_labels), gap="small")
                for idx, label in enumerate(export_labels):
                    if export_cols[idx].button(label, key=f"export_{label.lower()}"):
                        _trigger_export(label, dataset)
            st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)


def _render_pending_export() -> None:
    payload = st.session_state.get("last_export")
    if not payload:
        return
    st.success(f"Exportacao {payload['format']} pronta para download.")
    st.download_button(
        label=f"Baixar {payload['format']}",
        data=payload["data"],
        mime=payload["mime"],
        file_name=payload["name"],
        key=f"download_{payload['format'].lower()}",
    )


def render_logs_overlay() -> None:
    if not st.session_state.get("show_logs_panel"):
        return

    logs = (st.session_state.get("aggregated_overview") or {}).get("logs") or []
    with st.container():
        st.markdown("<div class='nxq-modal'>", unsafe_allow_html=True)
        st.markdown("<h4>Logs do pipeline</h4>", unsafe_allow_html=True)
        if not logs:
            st.info("Nenhum log disponivel no momento.")
        else:
            for entry in logs[-100:]:
                level = entry.get("level") or entry.get("levelname") or "INFO"
                message = entry.get("message") or entry.get("msg") or ""
                timestamp = entry.get("timestamp") or entry.get("time") or ""
                st.markdown(
                    f"<div class='nxq-log-item'><strong>{html.escape(str(level))}</strong>"
                    f"<small>{html.escape(str(timestamp))}</small>"
                    f"<div>{html.escape(str(message))}</div></div>",
                    unsafe_allow_html=True,
                )
        json_payload = json.dumps(logs, indent=2, ensure_ascii=False)
        text_payload = "\n".join(
            f"[{entry.get('timestamp') or entry.get('time')}] "
            f"{entry.get('level') or entry.get('levelname')}: {entry.get('message') or entry.get('msg') or ''}"
            for entry in logs
        )
        st.download_button(
            "Exportar JSON",
            data=json_payload.encode("utf-8"),
            mime="application/json",
            file_name="logs_pipeline.json",
            key="download_logs_json",
            use_container_width=True,
        )
        st.download_button(
            "Exportar TXT",
            data=text_payload.encode("utf-8"),
            mime="text/plain",
            file_name="logs_pipeline.txt",
            key="download_logs_txt",
            use_container_width=True,
        )
        if st.button("Fechar painel", key="close_logs_panel", use_container_width=True):
            st.session_state["show_logs_panel"] = False
            st.experimental_rerun()
        st.markdown("</div>", unsafe_allow_html=True)


def _request_interdoc_comparison() -> None:
    docs_for_compare = _prepare_docs_for_comparison(st.session_state.get("analysis_results", []))
    if not docs_for_compare:
        st.toast("Nenhum documento disponivel para comparacao.")
        return
    try:
        response = requests.post(
            f"{API_BASE_URL}/interdoc/compare",
            json={"docs": docs_for_compare},
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        st.toast(f"Falha ao comparar documentos: {exc}")
        st.session_state["comparison_result"] = None
    else:
        st.session_state["comparison_result"] = data.get("result")
        st.session_state["comparison_signature"] = str(len(docs_for_compare))
        st.session_state["activeView"] = "comparative"
        st.experimental_rerun()


def render_upload_view() -> None:
    st.subheader("Upload de arquivos")
    st.markdown(
        "Prepare os documentos fiscais para processamento. Arraste e solte arquivos ou escolha manualmente."
    )
    with st.container():
        st.markdown("<div class='nxq-upload'>", unsafe_allow_html=True)
        files = st.file_uploader(
            "Clique ou arraste novos arquivos",
            type=["xml", "csv", "xlsx", "pdf", "png", "jpg", "zip"],
            accept_multiple_files=True,
            label_visibility="collapsed",
            key="primary_uploader",
        )
        st.markdown(
            "<p class='nxq-upload-help'>Formatos suportados: XML, CSV, XLSX, PDF, imagens e ZIP (limite 200 MB).</p>",
            unsafe_allow_html=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)

    if st.button("Carregar exemplo de demonstracao", key="load_demo"):
        st.session_state["demo_loaded"] = True
        st.toast("Exemplo de demonstracao pronto. Substitua pelos seus documentos reais para obter insights.")

    if files:
        added, duplicates = _enqueue_files(files)
        if added:
            st.toast(f"{added} arquivo(s) adicionado(s) a fila.")
        if duplicates:
            st.toast("Arquivos ignorados por ja estarem na fila: " + ", ".join(duplicates))

    queue_meta = st.session_state.get("uploaded_queue_meta", [])
    if queue_meta:
        queue_df = pd.DataFrame(
            [
                {
                    "Arquivo": item.get("name"),
                    "Tamanho (KB)": f"{(float(item.get('size', 0)) / 1024):.1f}" if item.get("size") else "-",
                }
                for item in queue_meta
            ]
        )
        st.markdown("#### Arquivos na fila")
        st.dataframe(queue_df, use_container_width=True, hide_index=True)

    start_disabled = not bool(st.session_state.get("uploaded_payloads"))
    actions = st.columns([1, 1])
    with actions[0]:
        if st.button("Iniciar analise", disabled=start_disabled, use_container_width=True):
            st.session_state["pipelineStep"] = "PROCESSING"
            st.session_state["analysis_errors"] = []
            st.session_state["processing_status"] = ""
            st.session_state["agent_status"] = {agent: "running" for agent in AGENT_STEPS}
            st.experimental_rerun()
    with actions[1]:
        if st.button("Limpar fila", disabled=not queue_meta, use_container_width=True):
            st.session_state["uploaded_payloads"] = []
            st.session_state["uploaded_names"] = []
            st.session_state["uploaded_queue_meta"] = []
            st.toast("Fila de arquivos limpa.")


def render_processing_view() -> None:
    st.subheader("Processamento com agentes especialistas")
    cols = st.columns(len(AGENT_STEPS))
    placeholders = [col.empty() for col in cols]

    def refresh_agent_cards() -> None:
        statuses = st.session_state.get("agent_status", {})
        for placeholder, agent in zip(placeholders, AGENT_STEPS):
            placeholder.markdown(
                _agent_card_html(agent, statuses.get(agent, "pending")),
                unsafe_allow_html=True,
            )

    refresh_agent_cards()

    payloads = st.session_state.get("uploaded_payloads", [])
    if not payloads:
        st.info("Nenhum arquivo na fila. Volte para a etapa de upload.")
        if st.button("Voltar para upload", use_container_width=True):
            st.session_state["pipelineStep"] = "UPLOAD"
            st.experimental_rerun()
        return

    progress = st.progress(0)
    results: List[Dict[str, Any]] = []
    errors: List[str] = []

    for index, payload in enumerate(payloads, start=1):
        name = payload[0]
        st.session_state["processing_status"] = f"Processando {index}/{len(payloads)}: {name}"
        st.write(f"**{st.session_state['processing_status']}**")

        st.session_state["agent_status"] = {agent: "running" for agent in AGENT_STEPS}
        refresh_agent_cards()

        with st.spinner(st.session_state["processing_status"]):
            try:
                raw_result = process_uploaded_file(payload)
                per_file_summary = aggregate_results([raw_result])
                totals = per_file_summary.get("totals", {})
                results.append({**raw_result, "source": name, "totals": totals})
                st.session_state["agent_status"] = {agent: "completed" for agent in AGENT_STEPS}
            except Exception as exc:  # pragma: no cover - feedback ao usuario
                errors.append(name)
                st.session_state["agent_status"] = {agent: "error" for agent in AGENT_STEPS}
                st.error(f"Falha ao processar {name}: {exc}")
        refresh_agent_cards()
        progress.progress(index / len(payloads))

    progress.empty()

    aggregated = aggregate_results(results) if results else None
    st.session_state["analysis_results"] = results
    st.session_state["aggregated_overview"] = aggregated
    st.session_state["aggregated_totals"] = (aggregated or {}).get("totals", {}) if aggregated else {}
    st.session_state["aggregated_docs"] = (aggregated or {}).get("docs", []) if aggregated else []
    st.session_state["analysis_errors"] = errors
    st.session_state["analysis_completed"] = bool(results)
    st.session_state["uploaded_payloads"] = []
    st.session_state["uploaded_names"] = []
    st.session_state["uploaded_queue_meta"] = []
    st.session_state["pipelineStep"] = "ERROR" if errors and not results else "COMPLETE"
    st.experimental_rerun()


def _render_report_view(aggregated: Dict[str, Any], results: List[Dict[str, Any]]) -> None:
    display_summary(aggregated)
    reports = aggregated.get("reports") or []

    if reports:
        for idx, report in enumerate(reports, start=1):
            title = report.get("title") or f"Documento {idx}"
            with st.expander(f"Detalhes: {title}", expanded=idx == 1):
                classification = report.get("classification") or {}
                taxes = report.get("taxes") or {}
                compliance = report.get("compliance") or {}
                st.markdown("**Resumo fiscal**")
                st.json({"classification": classification, "taxes": taxes})
                if compliance:
                    st.markdown("**Conformidade**")
                    st.json(compliance)
    if results:
        st.caption("Consulte a aba Dashboard para acompanhar o historico incremental.")


def _render_dashboard_view(aggregated: Dict[str, Any], results: List[Dict[str, Any]]) -> None:
    docs = aggregated.get("docs") or []
    if docs:
        df = pd.DataFrame(docs)
        if {"documento", "valor_produtos"}.issubset(df.columns):
            numeric = df[["documento", "valor_produtos"]].copy()
            numeric["valor_produtos"] = pd.to_numeric(numeric["valor_produtos"], errors="coerce").fillna(0.0)
            numeric.set_index("documento", inplace=True)
            st.markdown("#### Valor por documento")
            st.bar_chart(numeric)
    else:
        st.info("Inclua documentos para visualizar o painel interativo.")

    totals = aggregated.get("totals") or {}
    base_icms = float(totals.get("vICMS") or 0.0)
    slider = st.slider("Ajuste percentual da aliquota de ICMS", 70, 130, 100, step=1)
    projected = base_icms * slider / 100
    delta = projected - base_icms
    st.metric("ICMS projetado", _format_brl(projected), delta=_format_brl(delta))

    show_incremental_insights(results)

    if st.session_state.get("comparison_result"):
        st.success("Comparacao interdocumental pronta. Consulte a aba Analise Comparativa.")
    else:
        st.info("Execute a acao 'Comparar documentos' para ativar discrepancias interdocumentais.")


def _render_comparative_view(results: List[Dict[str, Any]]) -> None:
    comparison = st.session_state.get("comparison_result")
    if not comparison:
        st.info("Nenhum resultado de comparacao disponivel. Clique em 'Comparar documentos'.")
        return

    render_discrepancies_panel(comparison)

    totals_rows = []
    for index, result in enumerate(results, start=1):
        totals = result.get("totals") or {}
        totals_rows.append(
            {
                "Execucao": f"Execucao {index}",
                "Valor total": float(totals.get("vNF") or 0.0),
            }
        )
    if totals_rows:
        chart_df = pd.DataFrame(totals_rows).set_index("Execucao")
        st.markdown("#### Evolucao do valor total por execucao")
        st.bar_chart(chart_df)

    show_incremental_insights(results)


def render_results_view() -> None:
    aggregated = st.session_state.get("aggregated_overview")
    results = st.session_state.get("analysis_results", [])

    if not aggregated:
        st.info("Nenhum resultado disponivel. Adicione arquivos e execute o processamento.")
        if st.button("Voltar para upload", use_container_width=True):
            st.session_state["pipelineStep"] = "UPLOAD"
            st.experimental_rerun()
        return

    view_options = [("report", "Relatorio de Analise"), ("dashboard", "Dashboard")]
    if len(results) > 1 or st.session_state.get("comparison_result"):
        view_options.append(("comparative", "Analise Comparativa"))

    labels = [label for _, label in view_options]
    current_view = st.session_state.get("activeView", "report")
    default_index = next((i for i, (value, _) in enumerate(view_options) if value == current_view), 0)

    with st.container():
        st.markdown("<div class='nxq-view-tabs'>", unsafe_allow_html=True)
        selected_label = st.radio(
            "Selecionar visualizacao",
            labels,
            index=default_index,
            horizontal=True,
            key="view_selector",
        )
        st.markdown("</div>", unsafe_allow_html=True)
    selected_view = next(value for value, label in view_options if label == selected_label)
    st.session_state["activeView"] = selected_view

    main_col, chat_col = st.columns([2, 1], gap="large")
    with main_col:
        if selected_view == "report":
            _render_report_view(aggregated, results)
        elif selected_view == "dashboard":
            _render_dashboard_view(aggregated, results)
        elif selected_view == "comparative":
            _render_comparative_view(results)

    with chat_col:
        render_chat_panel()

    st.markdown("---")
    action_cols = st.columns([1, 1, 1])
    if action_cols[0].button("Adicionar novos arquivos", use_container_width=True):
        st.session_state["pipelineStep"] = "UPLOAD"
        st.experimental_rerun()
    if action_cols[1].button("Comparar documentos", use_container_width=True):
        _request_interdoc_comparison()
    if action_cols[2].button("Iniciar nova analise", use_container_width=True):
        _reset_app_state()
        st.experimental_rerun()

    errors = st.session_state.get("analysis_errors", [])
    if errors:
        st.warning(f"{len(errors)} arquivo(s) nao foram processados: {', '.join(errors)}")


def render_chat_panel() -> None:
    chat_container = st.container()
    chat_container.markdown("<div class='chat-panel nxq-sticky-chat'>", unsafe_allow_html=True)
    chat_container.markdown("<h4>Chat fiscal</h4>", unsafe_allow_html=True)
    chat_container.markdown(
        _render_chat_history(st.session_state.get("chat_messages", [])),
        unsafe_allow_html=True,
    )
    chat_container.caption("Pergunte em linguagem natural ou anexe novos documentos durante a analise.")

    with chat_container.form("chat_form", clear_on_submit=True):
        prompt = st.text_area(
            "Mensagem",
            key="chat_prompt",
            placeholder="Pergunte sobre valores, impostos ou discrepancias...",
            height=120,
        )
        chat_files = st.file_uploader(
            "Adicionar anexos",
            type=["xml", "csv", "xlsx", "pdf", "jpg", "png", "zip"],
            accept_multiple_files=True,
            key="chat_file_uploader",
        )
        submitted = st.form_submit_button("Enviar", use_container_width=True)

    if submitted:
        attachments = chat_files or []
        added, duplicates = _enqueue_files(attachments)
        text = (prompt or "").strip()
        if text:
            st.session_state["chat_messages"].append({"role": "user", "content": text})
            st.session_state["chat_messages"].append({"role": "assistant", "content": _build_chat_reply(text)})
        if added:
            st.toast(f"{added} anexo(s) adicionado(s) para a proxima execucao.")
        if duplicates:
            st.toast("Arquivos ignorados por ja estarem na fila: " + ", ".join(duplicates))
        if not attachments and not text:
            st.toast("Nenhuma mensagem ou arquivo foi enviado.")
        st.session_state["chat_streaming"] = False

    chat_export = json.dumps(st.session_state.get("chat_messages", []), indent=2, ensure_ascii=False)
    chat_container.download_button(
        "Exportar conversa (JSON)",
        data=chat_export.encode("utf-8"),
        file_name="conversa_nexus.json",
        mime="application/json",
        use_container_width=True,
        key="download_chat_history",
    )
    if chat_container.button("Interromper geracao", key="stop_generation", use_container_width=True):
        st.session_state["chat_streaming"] = False
        st.toast("Geracao interrompida.")
    if chat_container.button("Limpar conversa", key="clear_chat", use_container_width=True):
        st.session_state["chat_messages"] = [dict(INITIAL_CHAT_MESSAGE)]
        st.toast("Conversa reiniciada.")
        st.experimental_rerun()
    chat_container.markdown("</div>", unsafe_allow_html=True)


def render_error_view() -> None:
    st.subheader("Falha no pipeline")
    message = st.session_state.get("processing_status") or "O pipeline interrompeu a execucao."
    st.error(message)
    errors = st.session_state.get("analysis_errors", [])
    if errors:
        st.write("Arquivos com erro: " + ", ".join(errors))

    control_cols = st.columns([1, 1])
    if control_cols[0].button("Tentar novamente", use_container_width=True):
        st.session_state["pipelineStep"] = "UPLOAD"
        st.experimental_rerun()
    if control_cols[1].button("Reiniciar aplicacao", use_container_width=True):
        _reset_app_state()
        st.experimental_rerun()


def main() -> None:
    _inject_theme()
    _ensure_state_defaults()
    _render_header()
    _render_pending_export()
    render_logs_overlay()

    pipeline_step = st.session_state.get("pipelineStep", "UPLOAD")

    if pipeline_step == "UPLOAD":
        render_upload_view()
    elif pipeline_step == "PROCESSING":
        render_processing_view()
    elif pipeline_step == "COMPLETE":
        render_results_view()
    elif pipeline_step == "ERROR":
        render_error_view()
    else:
        st.session_state["pipelineStep"] = "UPLOAD"
        st.experimental_rerun()


main()
