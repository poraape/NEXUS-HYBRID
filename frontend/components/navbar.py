import streamlit as st


def render_navbar():
    st.markdown(
        """
<div style="display:flex;justify-content:space-between;align-items:center;padding:10px 0;">
  <div><h2 style="color:#00aaff;margin:0;">Nexus QuantumI2A2</h2><p style="margin:0;color:#94a3b8;font-size:0.8rem;">Interactive Insight & Intelligence from Fiscal Analysis</p></div>
  <div><button style="margin-right:8px;">H</button><button style="margin-right:8px;">P</button><button style="margin-right:8px;">M</button><button style="background:#00ff9d;color:black;font-weight:600;">SPED</button></div>
</div>
<hr style="opacity:0.1;"/>
""",
        unsafe_allow_html=True,
    )
