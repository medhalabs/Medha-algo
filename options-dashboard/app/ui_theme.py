"""Global Streamlit styling: futuristic dark HUD aesthetic."""

from __future__ import annotations

import streamlit as st

FUTURE_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@500;700;800&family=Exo+2:ital,wght@0,400;0,500;0,600;1,400&display=swap');

.stApp {
  font-family: "Exo 2", system-ui, sans-serif;
  background:
    radial-gradient(ellipse 100% 60% at 50% -15%, rgba(0, 229, 255, 0.14), transparent 55%),
    radial-gradient(ellipse 60% 40% at 100% 50%, rgba(255, 0, 170, 0.06), transparent 45%),
    linear-gradient(165deg, #05080d 0%, #0a1018 45%, #060a10 100%) !important;
}

.stApp::before {
  content: "";
  position: fixed;
  inset: 0;
  background-image:
    linear-gradient(rgba(0, 229, 255, 0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0, 229, 255, 0.03) 1px, transparent 1px);
  background-size: 48px 48px;
  pointer-events: none;
  z-index: 0;
  mask-image: radial-gradient(ellipse 80% 60% at 50% 30%, black 20%, transparent 75%);
}

.block-container {
  position: relative;
  z-index: 1;
  padding-top: 1.25rem !important;
  max-width: 1400px !important;
}

section[data-testid="stSidebar"] {
  background: linear-gradient(175deg, rgba(12, 18, 32, 0.97) 0%, rgba(5, 8, 14, 0.99) 100%) !important;
  border-right: 1px solid rgba(0, 229, 255, 0.22) !important;
  box-shadow: 4px 0 40px rgba(0, 0, 0, 0.45);
}

section[data-testid="stSidebar"] .stMarkdown h2,
section[data-testid="stSidebar"] .stMarkdown h3 {
  font-family: "Orbitron", sans-serif !important;
  letter-spacing: 0.06em;
  color: #7df9ff !important;
  text-transform: uppercase;
  font-size: 0.78rem !important;
}

section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] span {
  color: #b8d4e8 !important;
}

section[data-testid="stSidebar"] .stSlider [data-baseweb="slider"] {
  filter: drop-shadow(0 0 8px rgba(0, 229, 255, 0.35));
}

.stButton > button[kind="primary"] {
  font-family: "Orbitron", sans-serif !important;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  font-size: 0.72rem !important;
  background: linear-gradient(135deg, #00c8e8 0%, #0099cc 100%) !important;
  border: 1px solid rgba(125, 249, 255, 0.5) !important;
  box-shadow: 0 0 24px rgba(0, 229, 255, 0.25), inset 0 1px 0 rgba(255, 255, 255, 0.15) !important;
  color: #021018 !important;
}

.stButton > button[kind="secondary"] {
  border-color: rgba(0, 229, 255, 0.35) !important;
  color: #7df9ff !important;
}

[data-testid="stMetric"] {
  background: linear-gradient(145deg, rgba(0, 229, 255, 0.07) 0%, rgba(0, 40, 60, 0.35) 100%) !important;
  border: 1px solid rgba(0, 229, 255, 0.28) !important;
  border-radius: 14px !important;
  padding: 1rem 1.1rem !important;
  overflow: visible !important;
  box-shadow:
    0 0 0 1px rgba(0, 0, 0, 0.3),
    0 8px 32px rgba(0, 0, 0, 0.35),
    inset 0 1px 0 rgba(255, 255, 255, 0.06) !important;
}

[data-testid="stMetric"] label {
  font-family: "Orbitron", sans-serif !important;
  font-size: 0.65rem !important;
  letter-spacing: 0.14em !important;
  text-transform: uppercase !important;
  color: #6ab8cc !important;
}

[data-testid="stMetric"] [data-testid="stMetricValue"] {
  font-family: "Exo 2", sans-serif !important;
  color: #f0fbff !important;
  white-space: normal !important;
  overflow: visible !important;
  text-overflow: clip !important;
  word-break: break-word !important;
  line-height: 1.3 !important;
  font-size: 1.05rem !important;
}

/* Avoid flex column squishing metrics into ellipsis on narrow viewports */
[data-testid="column"] [data-testid="stMetric"] {
  min-width: 0 !important;
  overflow: visible !important;
}

[data-testid="stDataFrame"],
[data-testid="stDataEditor"] {
  border: 1px solid rgba(0, 229, 255, 0.2) !important;
  border-radius: 12px !important;
  overflow: hidden !important;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.4) !important;
}

.stAlert {
  border-radius: 12px !important;
  border: 1px solid rgba(0, 229, 255, 0.25) !important;
  background: rgba(0, 30, 45, 0.6) !important;
}

.medha-hero {
  margin-bottom: 1.75rem;
  padding: 1.5rem 1.75rem 1.35rem;
  border-radius: 16px;
  background: linear-gradient(135deg, rgba(0, 229, 255, 0.08) 0%, rgba(255, 0, 170, 0.04) 100%);
  border: 1px solid rgba(0, 229, 255, 0.28);
  box-shadow:
    0 0 60px rgba(0, 229, 255, 0.08),
    inset 0 1px 0 rgba(255, 255, 255, 0.06);
  position: relative;
  overflow: hidden;
}

.medha-hero::after {
  content: "";
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 2px;
  background: linear-gradient(90deg, transparent, #00e5ff, #ff00aa, transparent);
  opacity: 0.85;
}

.medha-hero__badge {
  font-family: "Orbitron", sans-serif;
  font-size: 0.65rem;
  letter-spacing: 0.35em;
  color: #00e5ff;
  text-shadow: 0 0 20px rgba(0, 229, 255, 0.6);
  margin-bottom: 0.5rem;
}

.medha-hero__title {
  font-family: "Orbitron", sans-serif;
  font-weight: 800;
  font-size: 1.85rem;
  letter-spacing: 0.06em;
  margin: 0 0 0.35rem 0;
  background: linear-gradient(90deg, #e8f8ff 0%, #7df9ff 45%, #c8f0ff 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.medha-hero__sub {
  margin: 0;
  font-size: 0.95rem;
  color: #8aa8bc;
  font-weight: 400;
}

.medha-section-title {
  font-family: "Orbitron", sans-serif !important;
  font-size: 1rem !important;
  letter-spacing: 0.1em !important;
  text-transform: uppercase !important;
  color: #7df9ff !important;
  margin-top: 1.5rem !important;
  padding-bottom: 0.35rem !important;
  border-bottom: 1px solid rgba(0, 229, 255, 0.2) !important;
}

.medha-underline {
  font-family: "Orbitron", sans-serif;
  font-size: 1.05rem;
  letter-spacing: 0.04em;
  color: #c8e8f0;
  margin: 1rem 0 0.75rem;
}

.medha-glow-caption {
  color: #6a8fa8 !important;
  font-size: 0.82rem !important;
}

div[data-testid="stSpinner"] > div {
  border-top-color: #00e5ff !important;
}
</style>
"""


def inject_theme() -> None:
    st.markdown(FUTURE_CSS, unsafe_allow_html=True)
