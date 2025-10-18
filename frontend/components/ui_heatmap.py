import streamlit as st, pandas as pd, plotly.express as px
def risk_heatmap(data: pd.DataFrame|None):
    if data is None or data.empty:
        st.info("Sem dados suficientes para heatmap de risco.")
        return
    fig = px.density_heatmap(data, x="cfop", y="fornecedor", z="score", histfunc="avg")
    st.plotly_chart(fig, use_container_width=True)
