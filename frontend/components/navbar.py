import streamlit as st


def render_navbar():
    st.markdown(
        """
    <div class="navbar fade-in" style="display:flex;justify-content:space-between;align-items:center;padding:10px 0;flex-wrap:wrap;">
        <div style="min-width:240px;">
            <h2 style="color:#00aaff;margin:0;">Nexus QuantumI2A2</h2>
            <p style="margin:0;color:#94a3b8;font-size:0.8rem;">Interactive Insight & Intelligence from Fiscal Analysis</p>
        </div>
        <div style="display:flex;flex-wrap:wrap;gap:6px;">
            <button style="background:#1a2233;color:#e0e6f0;border:1px solid #2d3748;padding:6px 12px;border-radius:8px;">H</button>
            <button style="background:#1a2233;color:#e0e6f0;border:1px solid #2d3748;padding:6px 12px;border-radius:8px;">P</button>
            <button style="background:#1a2233;color:#e0e6f0;border:1px solid #2d3748;padding:6px 12px;border-radius:8px;">M</button>
            <button style="background:linear-gradient(90deg,#00ffcc,#00aaff);color:black;font-weight:600;padding:6px 12px;border-radius:8px;">SPED</button>
        </div>
    </div>
    <hr style="opacity:0.1;"/>
    """,
        unsafe_allow_html=True,
    )
