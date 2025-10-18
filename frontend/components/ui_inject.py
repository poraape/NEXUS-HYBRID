import streamlit as st, pathlib
def inject_theme():
    css_path = pathlib.Path(__file__).resolve().parents[1] / "styles" / "theme.css"
    with open(css_path, "r", encoding="utf-8") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
