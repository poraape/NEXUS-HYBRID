import streamlit as st, pandas as pd
from typing import List, Dict, Any
def inconsistencies_table(inconsistencies: List[Dict[str, Any]]):
    if not inconsistencies:
        st.success("Sem inconsistências detectadas.")
        return
    df = pd.DataFrame(inconsistencies)
    st.dataframe(df, use_container_width=True)
