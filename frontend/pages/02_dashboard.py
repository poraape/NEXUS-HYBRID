import streamlit as st
import plotly.express as px
import pandas as pd

st.markdown('<div class="fade-in">', unsafe_allow_html=True)
st.markdown('<h3 style="color:#00aaff;">Dashboard</h3>', unsafe_allow_html=True)
data = pd.DataFrame({'Categoria': ['ICMS', 'PIS', 'COFINS'], 'Valor': [23000, 15000, 8000]})
fig = px.bar(data, x='Categoria', y='Valor', color='Categoria', title='Distribuição de Tributos', template='plotly_dark')
col1, col2 = st.columns([2, 1])
with col1:
    st.plotly_chart(fig, use_container_width=True)
with col2:
    st.markdown('<div class="card"><h4 style="color:#e0e6f0;">KPIs Fiscais</h4>', unsafe_allow_html=True)
    st.metric('Total NFes', 'R$ 3.204.000,00')
    st.metric('ICMS Médio', 'R$ 23.000,00')
    st.metric('Margem Tributária', '15,6 %')
    st.markdown('</div>', unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)
