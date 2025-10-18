import streamlit as st

DARK_STYLE = """
<style>
:root {
  --bg-color: #0b0f19;
  --card-bg: #141a26;
  --accent: #00aaff;
  --text-color: #e0e6f0;
  --text-muted: #94a3b8;
}
body, .stApp { background: var(--bg-color); color: var(--text-color); }
.card, .metric-card { background: var(--card-bg); color: var(--text-color); }
</style>
"""

LIGHT_STYLE = """
<style>
:root {
  --bg-color: #f8fafc;
  --card-bg: #ffffff;
  --accent: #2563eb;
  --text-color: #0f172a;
  --text-muted: #475569;
}
body, .stApp { background: var(--bg-color); color: var(--text-color); }
.card, .metric-card { background: var(--card-bg); color: var(--text-color); }
.metric-value { color: var(--accent); }
</style>
"""


def render_theme_toggle():
    mode = st.session_state.get("theme", "dark")
    toggle = st.toggle("🌗 Modo Escuro", value=(mode == "dark"))
    if toggle:
        st.session_state["theme"] = "dark"
        st.markdown(DARK_STYLE, unsafe_allow_html=True)
    else:
        st.session_state["theme"] = "light"
        st.markdown(LIGHT_STYLE, unsafe_allow_html=True)
