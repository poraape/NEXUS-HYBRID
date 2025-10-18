import streamlit as st
import pandas as pd

st.markdown('<h3 style="color:#00aaff;">Relatório de Análise</h3>', unsafe_allow_html=True)
col1, col2 = st.columns([2, 1])
with col1:
    st.markdown('<div class="card"><h4 style="color:#e0e6f0;">Análise Executiva</h4><p style="color:#94a3b8;">A análise preliminar revela inconsistências nos dados agregados das NFes...</p></div>', unsafe_allow_html=True)
    st.markdown('<div class="card"><h4 style="color:#e0e6f0;">Métricas Chave</h4>', unsafe_allow_html=True)
    k1, k2, k3 = st.columns(3)
    k1.metric('Número de Documentos Válidos', '1')
    k2.metric('Valor Total das NFes', 'R$ 0,00')
    k3.metric('Valor Total dos Produtos', 'R$ 0,00')
    k4, k5 = st.columns(2)
    k4.metric('Total de Itens Processados', '665')
    k5.metric('Maior Transação na Amostra', 'R$ 1.292.418,75')
    st.markdown('</div>', unsafe_allow_html=True)
with col2:
    st.markdown('<div class="card"><h4 style="color:#e0e6f0;">Chat Interativo</h4><textarea placeholder="Faça uma pergunta sobre os dados..." style="width:100%;height:200px;background:#1a2233;color:white;border-radius:8px;"></textarea><br><button style="margin-top:8px;width:100%;">Enviar Pergunta</button></div>', unsafe_allow_html=True)
