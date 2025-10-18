import streamlit as st
from typing import List, Dict, Any
def kpi_grid(items: List[Dict[str, Any]], cols=3):
    rows = [items[i:i+cols] for i in range(0, len(items), cols)]
    for row in rows:
        cols_row = st.columns(len(row))
        for c, k in zip(cols_row, row):
            with c:
                st.markdown(f'''
<div class="block kpi">
  <div class="label">{k.get("label","")}</div>
  <div class="value">{k.get("value","")}</div>
</div>
''', unsafe_allow_html=True)
