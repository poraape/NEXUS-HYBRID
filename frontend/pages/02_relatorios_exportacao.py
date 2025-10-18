import streamlit as st, requests, pandas as pd
from components.ui_inject import inject_theme
from components.ui_kpis import kpi_grid
from components.ui_tables import inconsistencies_table

API = st.secrets.get("API_BASE_URL", "http://backend:8000")
inject_theme()
st.title("Relatórios & Exportação")

reports = st.session_state.get("reports", [])
if not reports:
    st.info("Nenhum relatório disponível. Processe arquivos na página anterior.")
    st.stop()

for idx, rep in enumerate(reports, start=1):
    with st.expander(f"Relatório {idx}: {rep.get('title')}"):
        st.subheader("KPIs")
        kpi_grid(rep.get("kpis", []), cols=3)

        st.subheader("Inconsistências")
        inc = rep.get("compliance",{}).get("inconsistencies",[])
        inconsistencies_table(inc)

        st.subheader("Classificação")
        st.json(rep.get("classification",{}))

        st.subheader("Tributos")
        st.json(rep.get("taxes",{}))

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            if st.button(f"Baixar DOCX #{idx}"):
                r = requests.post(f"{API}/export/docx", json={"dataset": rep})
                st.download_button("Download .docx", data=r.content, file_name="relatorio.docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        with c2:
            if st.button(f"Baixar PDF #{idx}"):
                r = requests.post(f"{API}/export/pdf", json={"dataset": rep})
                st.download_button("Download .pdf", data=r.content, file_name="relatorio.pdf", mime="application/pdf")
        with c3:
            if st.button(f"Baixar HTML #{idx}"):
                r = requests.post(f"{API}/export/html", json={"dataset": rep})
                st.download_button("Download .html", data=r.content, file_name="relatorio.html", mime="text/html")
        with c4:
            if st.button(f"Baixar SPED/EFD (protótipo) #{idx}"):
                r = requests.post(f"{API}/export/sped", json={"dataset": rep})
                st.download_button("Download .txt", data=r.content, file_name="sped_efd_prototipo.txt", mime="text/plain")
