import os
import logging
from datetime import datetime, timedelta

import streamlit as st
import pandas as pd
import plotly.express as px
import requests

from database import init_db, get_latest_sentiments, get_sentiment_history, get_config, set_config, Sentiment

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://192.168.1.100:11434")

st.set_page_config(page_title="Sentinel | Trading Sentiment Engine", layout="wide")

@st.cache_data(ttl=60)
def fetch_available_models():
    try:
        resp = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        models = [m["name"] for m in data.get("models", [])]
        return sorted(models)
    except Exception as e:
        logger.error(f"Failed to fetch models from Ollama: {e}")
        return []

@st.cache_data(ttl=60)
def load_sentiments(search: str = ""):
    return get_latest_sentiments(search)

init_db()

st.title("Sentinel")
st.caption("Dockerized Trading Sentiment Engine")

# --- Sidebar: Model Selection ---
st.sidebar.header("LLM Configuration")
models = fetch_available_models()
current_model = get_config("selected_model") or os.getenv("INITIAL_MODEL", "llama3.1")

if models:
    if current_model in models:
        idx = models.index(current_model)
    else:
        idx = 0
    selected = st.sidebar.selectbox("Select Ollama Model", models, index=idx)
    if selected != current_model:
        set_config("selected_model", selected)
        st.sidebar.success(f"Model set to {selected}. Next worker run will use this model.")
else:
    st.sidebar.warning("Could not fetch models from Ollama. Is it online?")
    selected = current_model

st.sidebar.markdown(f"**Active Model:** `{selected}`")
st.sidebar.markdown(f"**Ollama Host:** `{OLLAMA_HOST}`")

# --- Main Content ---
st.subheader("Latest Sentiment Snapshot")

col1, col2 = st.columns([1, 3])

with col1:
    search = st.text_input("Search Ticker", "")
    sort_order = st.selectbox("Sort by Delta 24h", ["Descending", "Ascending"])

records = load_sentiments(search)

if records:
    df = pd.DataFrame([{
        "Ticker": r.ticker,
        "Score": r.sentiment_score,
        "Delta 24h": r.delta_24h,
        "Catalyst": r.catalyst,
        "Timestamp": r.timestamp
    } for r in records])

    df = df.sort_values(by="Delta 24h", ascending=(sort_order == "Ascending"))

    st.dataframe(df, use_container_width=True, hide_index=True)

    # --- LEAPS Alert ---
    st.subheader("LEAPS Alert")
    leaps = df[(df["Score"] > 0.6) & (df["Delta 24h"] > 0.3)]
    if not leaps.empty:
        st.success("Strong bullish momentum shift detected!")
        st.dataframe(leaps[["Ticker", "Score", "Delta 24h", "Catalyst"]], use_container_width=True, hide_index=True)
    else:
        st.info("No tickers currently meet LEAPS criteria (Score > 0.6 AND Delta > 0.3).")

    # --- Trend Visualization ---
    st.subheader("7-Day Sentiment Trend")
    tickers = sorted(df["Ticker"].unique().tolist())
    selected_tickers = st.multiselect("Select Tickers", tickers, default=tickers[:3])

    if selected_tickers:
        trend_data = []
        for tick in selected_tickers:
            hist = get_sentiment_history(tick, days=7)
            for row in hist:
                trend_data.append({
                    "Ticker": row.ticker,
                    "Score": row.sentiment_score,
                    "Timestamp": row.timestamp
                })
        if trend_data:
            trend_df = pd.DataFrame(trend_data)
            fig = px.line(
                trend_df,
                x="Timestamp",
                y="Score",
                color="Ticker",
                title="Sentiment Score Over Last 7 Days",
                labels={"Score": "Sentiment Score", "Timestamp": "Date"},
                template="plotly_white"
            )
            fig.update_yaxes(range=[-1.1, 1.1])
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No historical data available for selected tickers yet.")
    else:
        st.info("Select at least one ticker to view trends.")
else:
    st.info("No sentiment data available yet. The worker may still be running its first analysis cycle.")
