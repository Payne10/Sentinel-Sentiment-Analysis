# Sentinel

A Dockerized trading sentiment engine that scrapes Reddit and NewsAPI, analyzes sentiment via a remote Ollama LLM instance, and surfaces narrative shifts through a Streamlit dashboard.

## Architecture

- **db**: PostgreSQL 16 (Alpine)
- **worker**: Python 3.12 (Alpine) — scrapers + Ollama analysis loop
- **dashboard**: Streamlit — sentiment table, LEAPS alerts, and 7-day Plotly trends

## Quick Start

1. Copy the environment file and fill in your credentials:
   ```bash
   cp .env.example .env
   ```

2. Build and run:
   ```bash
   docker compose up --build
   ```

3. Open the dashboard at [http://localhost:8501](http://localhost:8501)

## Ollama Integration

The worker communicates with a remote Ollama instance using native **Tool Calling** (`/api/chat`). The LLM invokes `record_sentiment(ticker, score, catalyst, confidence)` to persist data.

The Streamlit dashboard polls the Ollama host for available models and lets you switch the active model dynamically for future runs.

## Environment Variables

| Variable | Description |
|----------|-------------|
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | Postgres credentials |
| `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` / `REDDIT_USER_AGENT` | Reddit API (PRAW) |
| `NEWS_API_KEY` | NewsAPI key |
| `OLLAMA_HOST` | Remote Ollama URL (e.g. `http://192.168.1.100:11434`) |
| `INITIAL_MODEL` | Default Ollama model |
| `WATCHLIST` | Comma-separated stock tickers to analyze |
| `SUBREDDITS` | Comma-separated subreddits to search |
