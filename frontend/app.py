import streamlit as st
from components.navbar import render_navbar
from utils.theme_toggle import render_theme_toggle

st.set_page_config(page_title='Nexus Quantum I2A2', layout='wide', page_icon='💠')
st.markdown('<link rel="stylesheet" href="./styles/theme.css">', unsafe_allow_html=True)
render_navbar()
render_theme_toggle()
st.markdown('<h2 style="color:#00aaff;font-weight:600;">💠 Nexus QuantumI2A2</h2><p style="color:#94a3b8;">Interactive Insight & Intelligence from Fiscal Analysis</p>', unsafe_allow_html=True)
st.markdown('<div class="fade-in"><h4 style="color:#94a3b8;">Bem-vindo ao Nexus QuantumI2A2 Hybrid.</h4><p style="color:#64748b;">Aguarde enquanto os módulos são inicializados...</p></div>', unsafe_allow_html=True)
st.divider()
col1, col2 = st.columns([3, 2])
with col1:
    st.markdown('<h4 style="color:#e0e6f0;">1. Upload de Arquivos</h4>', unsafe_allow_html=True)
    uploaded = st.file_uploader(
        'Clique ou arraste seus arquivos',
        type=['xml', 'csv', 'xlsx', 'pdf', 'jpg', 'png', 'zip'],
        label_visibility='collapsed'
    )
    st.caption('Suportados: XML, CSV, XLSX, PDF, Imagens (PNG, JPG), ZIP (limite 200MB)')
    if uploaded:
        st.success('Arquivo carregado com sucesso.')
with col2:
    st.markdown('<div class="card"><b>💬 Chat Interativo</b><br><span style="color:#94a3b8;">Sua análise fiscal estará aqui. Faça perguntas sobre os dados processados.</span></div>', unsafe_allow_html=True)
