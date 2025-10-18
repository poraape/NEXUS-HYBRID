from __future__ import annotations

import html
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Tuple

import pandas as pd
import requests
import streamlit as st

if TYPE_CHECKING:  # pragma: no cover - hints only
    from streamlit.runtime.uploaded_file_manager import UploadedFile

from components.navbar import render_navbar
from utils.theme_toggle import render_theme_toggle
from utils.insights import show_incremental_insights


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


def _render_chat_history(messages: Iterable[Dict[str, str]]) -> str:
    rows: List[str] = []
    for message in messages:
        role = message.get("role", "assistant")
        role_class = "user" if role == "user" else "assistant"
        label = "Você" if role == "user" else "Nexus"
        safe_content = html.escape(message.get("content", "")).replace("\n", "<br>")
        rows.append(
            f"<div class='chat-bubble chat-bubble--{role_class}'><span class='chat-meta'>{label}</span><p>{safe_content}</p></div>"
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
            f"Atualmente acompanhamos {len(docs)} documento(s) consolidado(s).",
            f"O valor total dos produtos está em {_format_brl(totals.get('vProd', 0.0))}.",
        ]
        if totals.get("vICMS"):
            summary_parts.append(f"A projeção de ICMS soma {_format_brl(totals.get('vICMS', 0.0))}.")
        return "\n\n".join([f'Mensagem recebida: "{prompt}"', *summary_parts])
    return (
        "Mensagem recebida, mas ainda não há resultados processados. "
        "Adicione arquivos e execute a análise incremental para obter respostas contextualizadas."
    )


def display_summary(aggregated: Dict[str, Any], *, show_success: bool = True) -> None:
    totals = aggregated.get("totals", {})
    docs = aggregated.get("docs", [])

    if show_success:
        st.success("✅ Todos os arquivos foram processados com sucesso.")
    else:
        st.caption("Resumo consolidado da análise incremental")
    col_a, col_b, col_c = st.columns(3)
    col_a.metric("Documentos processados", len(docs))
    col_b.metric("Valor total dos produtos", _format_brl(totals.get("vProd", 0.0)))
    col_c.metric("ICMS estimado", _format_brl(totals.get("vICMS", 0.0)))

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

st.set_page_config(page_title='Nexus Quantum I2A2', layout='wide', page_icon='💠')
st.markdown('<link rel="stylesheet" href="./styles/theme.css">', unsafe_allow_html=True)
render_navbar()
render_theme_toggle()

if "uploaded_payloads" not in st.session_state:
    st.session_state["uploaded_payloads"] = []
if "uploaded_names" not in st.session_state:
    st.session_state["uploaded_names"] = []
if "analysis_results" not in st.session_state:
    st.session_state["analysis_results"] = []
if "aggregated_overview" not in st.session_state:
    st.session_state["aggregated_overview"] = None
if "analysis_errors" not in st.session_state:
    st.session_state["analysis_errors"] = []
if "analysis_completed" not in st.session_state:
    st.session_state["analysis_completed"] = False
if "chat_messages" not in st.session_state:
    st.session_state["chat_messages"] = [
        {
            "role": "assistant",
            "content": (
                "Olá! Carregue seus arquivos fiscais para começarmos a análise. "
                "Você pode enviar novos documentos a qualquer momento pelo painel lateral."
            ),
        }
    ]
if "chat_feedback" not in st.session_state:
    st.session_state["chat_feedback"] = None
st.markdown('<h2 style="color:#00aaff;font-weight:600;">💠 Nexus QuantumI2A2</h2><p style="color:#94a3b8;">Interactive Insight & Intelligence from Fiscal Analysis</p>', unsafe_allow_html=True)
st.markdown('<div class="fade-in"><h4 style="color:#94a3b8;">Bem-vindo ao Nexus QuantumI2A2 Hybrid.</h4><p style="color:#64748b;">Aguarde enquanto os módulos são inicializados...</p></div>', unsafe_allow_html=True)
st.divider()
col1, col2 = st.columns([3, 2])
with col1:
    st.markdown('<h4 style="color:#e0e6f0;">1. Upload de Arquivos</h4>', unsafe_allow_html=True)
    new_files = st.file_uploader(
        'Envie novos arquivos para adicionar à análise (incremental)',
        type=['xml', 'csv', 'xlsx', 'pdf', 'jpg', 'png', 'zip'],
        accept_multiple_files=True,
        label_visibility='collapsed',
        key='incremental_uploader'
    )
    st.caption('Suportados: XML, CSV, XLSX, PDF, Imagens (PNG, JPG), ZIP (limite 200MB)')

    if new_files:
        added, duplicates = _enqueue_files(new_files)
        if added:
            st.info(f"{added} novo(s) arquivo(s) adicionado(s) à análise.")
        elif duplicates:
            st.warning('Nenhum arquivo novo foi adicionado; todos já estavam na fila.')

    total_files = len(st.session_state['uploaded_payloads'])
    if total_files:
        st.markdown(f"### Total de arquivos no conjunto: {total_files}")
        if st.session_state['uploaded_names']:
            st.caption('Fila atual: ' + ', '.join(st.session_state['uploaded_names']))

        process_clicked = st.button('▶️ Processar todos os arquivos (análise incremental)')
        if process_clicked:
            results: List[Dict[str, Any]] = []
            errors: List[str] = []
            progress = st.progress(0)

            for index, payload in enumerate(st.session_state['uploaded_payloads']):
                name, _, _ = payload
                with st.spinner(f'Processando {name}...'):
                    try:
                        raw_result = process_uploaded_file(payload)
                        per_file_summary = aggregate_results([raw_result])
                        totals = per_file_summary.get('totals', {})
                        results.append({**raw_result, 'source': name, 'totals': totals})
                    except Exception as exc:  # pragma: no cover - feedback ao usuário
                        errors.append(name)
                        st.error(f'Falha ao processar {name}: {exc}')
                progress.progress((index + 1) / total_files)

            progress.empty()

            st.session_state['analysis_results'] = results
            st.session_state['analysis_errors'] = errors

            if results:
                aggregated = aggregate_results(results)
                st.session_state['aggregated_overview'] = aggregated
                st.session_state['reports'] = aggregated.get('reports', [])
                st.session_state['processing_logs'] = aggregated.get('logs', [])
                st.session_state['aggregated_totals'] = aggregated.get('totals', {})
                st.session_state['aggregated_docs'] = aggregated.get('docs', [])
            else:
                st.session_state['aggregated_overview'] = None

            st.session_state['analysis_completed'] = bool(results)
with col2:
    chat_container = st.container()
    chat_container.markdown(
        '<div class="card chat-card"><b>💬 Chat Interativo</b><br><span style="color:#94a3b8;">Converse sobre a análise fiscal, anexe novos arquivos a qualquer momento e acompanhe os destaques automaticamente.</span>',
        unsafe_allow_html=True,
    )
    chat_container.markdown(
        _render_chat_history(st.session_state.get('chat_messages', [])),
        unsafe_allow_html=True,
    )
    with chat_container.form('chat_form', clear_on_submit=True):
        prompt = st.text_area(
            'Mensagem',
            key='chat_prompt',
            placeholder='Faça uma pergunta ou descreva novos documentos a enviar...',
            height=120,
        )
        chat_files = st.file_uploader(
            'Anexar arquivos adicionais',
            type=['xml', 'csv', 'xlsx', 'pdf', 'jpg', 'png', 'zip'],
            accept_multiple_files=True,
            key='chat_file_uploader',
        )
        submitted = st.form_submit_button('Enviar', use_container_width=True)
    feedback = None
    if submitted:
        attachments = chat_files or []
        added, duplicates = _enqueue_files(attachments)
        text = (prompt or '').strip()
        if text:
            st.session_state['chat_messages'].append({'role': 'user', 'content': text})
            st.session_state['chat_messages'].append({'role': 'assistant', 'content': _build_chat_reply(text)})
        if added:
            feedback = ('success', f'{added} arquivo(s) foram adicionados à fila de processamento.')
        elif attachments:
            duplicate_list = ', '.join(duplicates) if duplicates else 'os arquivos enviados'
            feedback = ('warning', f'Não houve anexos novos; {duplicate_list} já estava(m) presente(s).')
        elif text:
            feedback = ('info', 'Mensagem registrada. Execute ou atualize a análise para obter novos insights.')
        else:
            feedback = ('info', 'Nenhuma mensagem ou arquivo foi enviado.')
        st.session_state['chat_feedback'] = feedback
    feedback = st.session_state.get('chat_feedback')
    if feedback:
        level, message = feedback
        getattr(chat_container, level)(message)
        st.session_state['chat_feedback'] = None
    chat_container.markdown('</div>', unsafe_allow_html=True)

aggregated_overview = st.session_state.get('aggregated_overview')
analysis_results = st.session_state.get('analysis_results', [])

if aggregated_overview:
    display_summary(
        aggregated_overview,
        show_success=st.session_state.pop('analysis_completed', False),
    )
    show_incremental_insights(analysis_results)
elif analysis_results:
    show_incremental_insights(analysis_results)

errors = st.session_state.get('analysis_errors', [])
if errors:
    st.warning(f"{len(errors)} arquivo(s) não foram processados. Verifique os logs acima.")
