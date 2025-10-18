import altair as alt
import pandas as pd
import plotly.express as px
import streamlit as st

from components.ui_heatmap import risk_heatmap
from components.ui_inject import inject_theme

inject_theme()
st.title("Dashboards e Simulações")

reports = st.session_state.get("reports", [])
if not reports:
    st.info("Nenhum relatório carregado ainda. Faça o upload de documentos para habilitar os dashboards.")
    st.stop()

rows = []
for report in reports:
    source = report.get("source") or {}
    classification = report.get("classification") or {}
    emitente = (source.get("emitente") or {}).get("nome")
    destinatario = (source.get("destinatario") or {}).get("nome")
    uf = (source.get("emitente") or {}).get("uf") or (source.get("destinatario") or {}).get("uf")
    score = report.get("compliance", {}).get("score", 0)
    for item in source.get("itens", []):
        rows.append(
            {
                "documento": report.get("title"),
                "emitente": emitente,
                "destinatario": destinatario,
                "uf": uf,
                "cfop": item.get("cfop"),
                "ncm": item.get("ncm"),
                "descricao": item.get("descricao"),
                "valor": float(item.get("valor", 0) or 0),
                "ramo": classification.get("ramo"),
                "score": score,
            }
        )

df = pd.DataFrame(rows)
if df.empty:
    st.warning("Não há itens para compor os gráficos.")
    st.stop()

col1, col2, col3 = st.columns(3)
col1.metric("Documentos", len(reports))
col2.metric("Total de Itens", len(df))
col3.metric("Score médio", f"{df['score'].mean():.2f}")

st.subheader("Distribuição por CFOP")
cfop_chart = px.bar(
    df.groupby("cfop", dropna=False)["valor"].sum().reset_index(),
    x="cfop",
    y="valor",
    title="Total por CFOP",
)
st.plotly_chart(cfop_chart, use_container_width=True)

st.subheader("NCM por ramo de atividade")
ncm_chart = (
    alt.Chart(df)
    .mark_bar()
    .encode(x="ncm:N", y="sum(valor):Q", color="ramo:N", tooltip=["documento", "valor", "ramo"])
    .interactive()
)
st.altair_chart(ncm_chart, use_container_width=True)

st.subheader("Heatmap de Risco Fiscal")
heatmap_df = df.rename(columns={"emitente": "fornecedor"})[["cfop", "fornecedor", "score"]]
risk_heatmap(heatmap_df)

st.subheader("Logs consolidados")
log_placeholder = st.empty()
log_table = []
for report in reports:
    for event in report.get("logs", []):
        log_table.append({
            "Documento": report.get("title"),
            "Etapa": event.get("stage"),
            "Status": event.get("status"),
            "Início": event.get("started_at"),
            "Duração": event.get("duration"),
        })
if log_table:
    log_placeholder.dataframe(pd.DataFrame(log_table))
else:
    log_placeholder.info("Nenhum log disponível para os documentos carregados.")

st.success("Dashboards atualizados com base nos dados mais recentes.")
