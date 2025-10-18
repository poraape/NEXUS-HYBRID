import streamlit as st
from components.ui_inject import inject_theme

st.set_page_config(page_title="Nexus Quantum I2A2 (Python UI)", layout="wide")
inject_theme()
st.sidebar.title("Nexus (Python)")
st.sidebar.write("Use as páginas para carregar arquivos, auditar e exportar relatórios.")
st.title("Nexus Quantum I2A2 — Interface Python/Streamlit")
st.write("Vá para **Upload & Auditoria** na barra lateral para começar.")
