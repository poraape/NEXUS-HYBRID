import streamlit as st, requests
from components.ui_inject import inject_theme

API = st.secrets.get("API_BASE_URL", "http://backend:8000")
inject_theme()
st.title("Upload & Auditoria")

tab1, tab2 = st.tabs(["Upload ZIP","Upload Arquivo Único"])

with tab1:
    zip_file = st.file_uploader("Selecione um .zip (até 200 MB)", type=["zip"], key="zip")
    if st.button("Enviar ZIP", type="primary") and zip_file:
        with st.spinner("Processando..."):
            r = requests.post(f"{API}/upload/zip", files={"file": (zip_file.name, zip_file.getvalue(), "application/zip")}, timeout=300)
            r.raise_for_status()
            st.session_state["reports"] = r.json()["reports"]
            st.success("Processado! Vá para 'Relatórios & Exportação'.")

with tab2:
    f = st.file_uploader("Selecione um arquivo", type=["xml","csv","xlsx","pdf","png","jpg","jpeg"], key="single")
    if st.button("Enviar Arquivo", type="primary") and f:
        with st.spinner("Processando..."):
            r = requests.post(f"{API}/upload/file", files={"file": (f.name, f.getvalue(), f"type/{f.type}")}, timeout=300)
            r.raise_for_status()
            st.session_state["reports"] = r.json()["reports"]
            st.success("Processado! Vá para 'Relatórios & Exportação'.")
