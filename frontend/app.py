from __future__ import annotations

import html
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Tuple

import pandas as pd
import requests
import streamlit as st

if TYPE_CHECKING:  # pragma: no cover - hints only
    from streamlit.runtime.uploaded_file_manager import UploadedFile

from utils.insights import render_discrepancies_panel, show_incremental_insights


API_BASE_URL = st.secrets.get("API_BASE_URL", "http://backend:8000")


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
    for file in files:
        if file.name not in st.session_state["uploaded_names"]:
            st.session_state["uploaded_payloads"].append(_prepare_payload(file))
            st.session_state["uploaded_names"].append(file.name)
            added += 1
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
                "cfop": classification.get("cfop")
                or _first_non_empty(itens, ["cfop"]),
                "cst": _first_non_empty(itens, ["cst", "cst_icms", "cstIcms"]),
                "ncm": classification.get("ncm")
                or _first_non_empty(itens, ["ncm"]),
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
        label = "Você" if role == "user" else "Nexus"
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
            "<div class='chat-placeholder'>Envie uma pergunta ou anexe novos arquivos para complementar a análise.</div>"
        )
    return "<div class='chat-history'>" + "".join(rows) + "</div>"


def _build_chat_reply(prompt: str) -> str:
    prompt = prompt.strip()
    aggregated = st.session_state.get("aggregated_overview")
    if aggregated:
        totals = aggregated.get("totals", {})
        docs = aggregated.get("docs", [])
        summary_parts = [
            f"Acompanhamos {len(docs)} documento(s) consolidado(s).",
            f"O valor total dos produtos está em {_format_brl(totals.get('vProd', 0.0))}.",
        ]
        if totals.get("vICMS"):
            summary_parts.append(f"A projeção de ICMS soma {_format_brl(totals.get('vICMS', 0.0))}.")
        return "\n\n".join([f'Mensagem recebida: "{prompt}"', *summary_parts])
    return (
        "Mensagem recebida, mas ainda não há resultados processados. "
        "Adicione arquivos e execute a análise incremental para obter respostas contextualizadas."
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
        st.info("Nenhum documento válido foi consolidado até o momento.")


def _reset_app_state() -> None:
    preserved_chat = st.session_state.get("chat_messages")
    st.session_state.clear()
    st.session_state["stage"] = "upload"
    st.session_state["chat_messages"] = preserved_chat or [
        {
            "role": "assistant",
            "content": (
                "Olá! Carregue seus arquivos fiscais para começarmos a análise. "
                "Você pode enviar novos documentos a qualquer momento pelo painel de conversa."
            ),
        }
    ]


st.set_page_config(page_title="Nexus Quantum I2A2", page_icon="💠", layout="wide")

assets_path = Path(__file__).parent / "assets" / "theme.css"
if assets_path.exists():
    st.markdown(f"<style>{assets_path.read_text()}</style>", unsafe_allow_html=True)

st.markdown(
    """
    <style>
        body {background: linear-gradient(145deg, #020611 0%, #071a33 100%) !important; color: #fff;}
        [data-testid="stHeader"] {background: none;}
        .block-container {padding-top: 2rem; max-width: 1100px;}
        h1, h2, h3, h4 {font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', sans-serif;}
        .metric-box {background: rgba(255,255,255,0.06); padding: 1rem; border-radius: 12px; text-align: center;}
        .metric-label {display: block; font-size: 0.8rem; letter-spacing: 0.08em; text-transform: uppercase; opacity: 0.7; margin-bottom: 0.35rem;}
        .metric-value {font-size: 1.6rem; font-weight: 700; color: #00bfff;}
        .upload-box {border: 2px dashed rgba(255,255,255,0.25); border-radius: 16px; padding: 2rem; text-align: center; transition: all 0.3s ease-in-out;}
        .upload-box:hover {border-color: #00bfff; background: rgba(255,255,255,0.05);}
        .stage-card {background: rgba(255,255,255,0.04); padding: 1.8rem; border-radius: 16px; backdrop-filter: blur(12px);}
        .chat-panel {background: rgba(4,10,25,0.55); border-radius: 16px; padding: 1.5rem; margin-top: 2rem;}
        .chat-history {max-height: 320px; overflow-y: auto; margin-bottom: 1rem; padding-right: 0.4rem;}
        .chat-bubble {padding: 0.75rem 1rem; border-radius: 12px; margin-bottom: 0.6rem; font-size: 0.95rem;}
        .chat-bubble--assistant {background: rgba(0,0,0,0.35); border: 1px solid rgba(255,255,255,0.08);}
        .chat-bubble--user {background: rgba(0,191,255,0.16); border: 1px solid rgba(0,191,255,0.35);}
        .chat-meta {display: block; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.06em; opacity: 0.7; margin-bottom: 0.25rem;}
        .chat-placeholder {padding: 1rem; border-radius: 12px; background: rgba(255,255,255,0.04); text-align: center;}
        .stage-actions {margin-top: 1.5rem; display: flex; gap: 0.75rem; flex-wrap: wrap;}
        .stage-actions button {flex: 1; min-width: 160px;}
    </style>
    """,
    unsafe_allow_html=True,
)

initial_chat_message = {
    "role": "assistant",
    "content": (
        "Olá! Carregue seus arquivos fiscais para começarmos a análise. "
        "Você pode enviar novos documentos a qualquer momento pelo painel de conversa."
    ),
}

state_defaults: Dict[str, Any] = {
    "stage": "upload",
    "uploaded_payloads": [],
    "uploaded_names": [],
    "analysis_results": [],
    "aggregated_overview": None,
    "analysis_errors": [],
    "analysis_completed": False,
    "chat_messages": [initial_chat_message],
    "chat_feedback": None,
    "comparison_result": None,
    "comparison_signature": "",
}

for key, value in state_defaults.items():
    if key not in st.session_state:
        if isinstance(value, list):
            st.session_state[key] = list(value)
        elif isinstance(value, dict):
            st.session_state[key] = dict(value)
        else:
            st.session_state[key] = value

st.markdown(
    "<h1 style=\"text-align:center; color:#00bfff;\">⚛️ Nexus <span style=\"color:#66ccff;\">Quantum I2A2</span></h1>",
    unsafe_allow_html=True,
)
st.markdown(
    "<p style=\"text-align:center; opacity:0.75;\">Interactive Insight & Intelligence from Fiscal Analysis</p>",
    unsafe_allow_html=True,
)

stage = st.session_state.get("stage", "upload")

if stage == "upload":
    st.markdown("<h3>1. Upload de Arquivos</h3>", unsafe_allow_html=True)
    with st.container():
        st.markdown("<div class='upload-box'>", unsafe_allow_html=True)
        files = st.file_uploader(
            "Clique ou arraste novos arquivos",
            type=["xml", "csv", "xlsx", "pdf", "png", "jpg", "zip"],
            accept_multiple_files=True,
            label_visibility="collapsed",
            key="primary_uploader",
        )
        st.markdown(
            "<p style='font-size:0.9rem; opacity:0.7;'>Suportados: XML, CSV, XLSX, PDF, Imagens, ZIP (limite 200 MB)</p>",
            unsafe_allow_html=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)

    if files:
        added, duplicates = _enqueue_files(files)
        if added:
            st.success(f"{added} arquivo(s) adicionado(s) à fila de análise.")
        if duplicates:
            st.warning("Arquivos ignorados por já estarem na fila: " + ", ".join(duplicates))

    if st.session_state["uploaded_names"]:
        st.markdown("#### Arquivos na fila")
        st.markdown(", ".join(st.session_state["uploaded_names"]))

    start_disabled = not bool(st.session_state["uploaded_payloads"])
    if st.button("▶️ Iniciar Análise", disabled=start_disabled):
        st.session_state["analysis_completed"] = False
        st.session_state["analysis_errors"] = []
        st.session_state["stage"] = "analysis"
        st.experimental_rerun()

elif stage == "analysis":
    st.markdown("<h3>2. Processamento Inteligente</h3>", unsafe_allow_html=True)
    payloads = st.session_state.get("uploaded_payloads", [])
    if not payloads:
        st.info("Nenhum arquivo na fila. Volte ao upload para adicionar documentos.")
        if st.button("⬅️ Voltar ao Upload"):
            st.session_state["stage"] = "upload"
            st.experimental_rerun()
    else:
        progress = st.progress(0)
        results: List[Dict[str, Any]] = []
        errors: List[str] = []
        for index, payload in enumerate(payloads):
            name = payload[0]
            with st.spinner(f"Processando {name}..."):
                try:
                    raw_result = process_uploaded_file(payload)
                    per_file_summary = aggregate_results([raw_result])
                    totals = per_file_summary.get("totals", {})
                    results.append({**raw_result, "source": name, "totals": totals})
                except Exception as exc:  # pragma: no cover - feedback ao usuário
                    errors.append(name)
                    st.error(f"Falha ao processar {name}: {exc}")
            progress.progress((index + 1) / len(payloads))
        progress.empty()

        aggregated = aggregate_results(results) if results else None
        st.session_state["analysis_results"] = results
        st.session_state["aggregated_overview"] = aggregated
        st.session_state["aggregated_totals"] = (aggregated or {}).get("totals", {}) if aggregated else {}
        st.session_state["aggregated_docs"] = (aggregated or {}).get("docs", []) if aggregated else []
        st.session_state["analysis_errors"] = errors
        st.session_state["analysis_completed"] = bool(results)
        st.session_state["comparison_result"] = None
        st.session_state["comparison_signature"] = ""
        st.session_state["stage"] = "dashboard"
        st.experimental_rerun()

elif stage == "dashboard":
    st.markdown("<h3>3. Dashboard Fiscal Inteligente</h3>", unsafe_allow_html=True)
    aggregated_overview = st.session_state.get("aggregated_overview")
    analysis_results = st.session_state.get("analysis_results", [])

    if aggregated_overview:
        display_summary(aggregated_overview)
    if analysis_results:
        show_incremental_insights(analysis_results)
    else:
        st.info("Execute uma análise para visualizar os insights incrementais.")

    controls = st.container()
    with controls:
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("➕ Adicionar novos arquivos"):
                st.session_state["stage"] = "upload"
                st.experimental_rerun()
        with col2:
            docs_for_compare = _prepare_docs_for_comparison(analysis_results)
            compare_disabled = not bool(docs_for_compare)
            if st.button("📊 Comparar Documentos", disabled=compare_disabled):
                if not docs_for_compare:
                    st.warning("Nenhum documento disponível para comparação.")
                else:
                    try:
                        response = requests.post(
                            f"{API_BASE_URL}/interdoc/compare",
                            json={"docs": docs_for_compare},
                            timeout=60,
                        )
                        response.raise_for_status()
                        data = response.json()
                        st.session_state["comparison_result"] = data.get("result")
                    except requests.RequestException as exc:
                        st.warning(f"Não foi possível comparar documentos: {exc}")
                        st.session_state["comparison_result"] = None
                    except ValueError:
                        st.warning("Resposta inválida do comparador fiscal.")
                        st.session_state["comparison_result"] = None
                    else:
                        st.session_state["stage"] = "insights"
                        st.experimental_rerun()
        with col3:
            if st.button("🔄 Nova análise"):
                _reset_app_state()
                st.experimental_rerun()

    chat_container = st.container()
    chat_container.markdown("<div class='chat-panel'>", unsafe_allow_html=True)
    chat_container.markdown("<h4 style='margin-top:0;'>💬 Conversa & Upload Incremental</h4>", unsafe_allow_html=True)
    chat_container.markdown(
        _render_chat_history(st.session_state.get("chat_messages", [])),
        unsafe_allow_html=True,
    )
    with chat_container.form("chat_form", clear_on_submit=True):
        prompt = st.text_area(
            "Mensagem",
            key="chat_prompt",
            placeholder="Faça uma pergunta ou descreva novos documentos a enviar...",
            height=120,
        )
        chat_files = st.file_uploader(
            "Anexar arquivos adicionais",
            type=["xml", "csv", "xlsx", "pdf", "jpg", "png", "zip"],
            accept_multiple_files=True,
            key="chat_file_uploader",
        )
        submitted = st.form_submit_button("Enviar", use_container_width=True)

    feedback = None
    if submitted:
        attachments = chat_files or []
        added, duplicates = _enqueue_files(attachments)
        text = (prompt or "").strip()
        if text:
            st.session_state["chat_messages"].append({"role": "user", "content": text})
            st.session_state["chat_messages"].append({"role": "assistant", "content": _build_chat_reply(text)})
        if added:
            feedback = (
                "success",
                f"{added} arquivo(s) foram adicionados à fila. Volte à etapa de upload para reprocessar a análise.",
            )
        elif attachments:
            duplicate_list = ", ".join(duplicates) if duplicates else "os arquivos enviados"
            feedback = (
                "warning",
                f"Não houve anexos novos; {duplicate_list} já estava(m) presente(s).",
            )
        elif text:
            feedback = (
                "info",
                "Mensagem registrada. Execute ou atualize a análise para obter novos insights.",
            )
        else:
            feedback = ("info", "Nenhuma mensagem ou arquivo foi enviado.")
        st.session_state["chat_feedback"] = feedback

    feedback = st.session_state.get("chat_feedback")
    if feedback:
        level, message = feedback
        getattr(chat_container, level)(message)
        st.session_state["chat_feedback"] = None

    chat_container.markdown("</div>", unsafe_allow_html=True)

    errors = st.session_state.get("analysis_errors", [])
    if errors:
        st.warning(
            f"{len(errors)} arquivo(s) não foram processados. Reavalie os documentos ou consulte os logs detalhados no backend."
        )

elif stage == "insights":
    st.markdown("<h3>4. Insights Interdocumentais</h3>", unsafe_allow_html=True)
    render_discrepancies_panel(st.session_state.get("comparison_result"))

    col1, col2 = st.columns(2)
    if col1.button("⬅️ Voltar ao dashboard"):
        st.session_state["stage"] = "dashboard"
        st.experimental_rerun()
    if col2.button("🔄 Nova análise"):
        _reset_app_state()
        st.experimental_rerun()

else:
    st.session_state["stage"] = "upload"
    st.experimental_rerun()
