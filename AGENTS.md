# Sentinel-Sentiment-Analysis — Agent Guide

## Project Overview

Sentinel is a Dockerized trading sentiment engine. It fetches news via **NewsAPI**, sends collected text to a remote Ollama LLM instance (native tool calling), and persists sentiment scores into PostgreSQL. A Streamlit dashboard visualizes the data.

**Primary Goal:** Surface narrative shifts and bullish momentum by tracking per-ticker sentiment scores and their 24-hour deltas.

---

## Service Architecture

| Service | Tech | Role |
|---------|------|------|
| `db` | PostgreSQL 16 (Alpine) | Stores `sentiments` and `config` tables |
| `worker` | Python 3.12 (Alpine) | NewsAPI fetcher + Ollama analysis loop via APScheduler (every 4h) |
| `dashboard` | Streamlit (Alpine) | UI on port `8501`. Polls Ollama for models. Lets users switch the active model. |

All runtime configuration (API keys, Ollama IP, model name) is sourced from `.env`. The `docker-compose.yml` does **not** hardcode secrets.

---

## Key Files

| File | Purpose |
|------|---------|
| `docker-compose.yml` | 3-service orchestration with healthchecks |
| `Dockerfile` | Multi-stage Alpine build (`builder` → `worker` / `dashboard`) |
| `worker.py` | NewsAPI scraper. Calls Ollama `/api/chat` with tools. Reads active model from DB `config` table |
| `dashboard.py` | Streamlit. Searchable ticker table, LEAPS alert, 7-day Plotly trends, Ollama model selector |
| `database.py` | SQLAlchemy models, session management, `record_sentiment` tool function, delta calculations |
| `.env.example` | Template of all required env vars |

---

## Running the Project

```bash
cp .env.example .env
# edit .env with real credentials and OLLAMA_HOST
docker compose up --build
```

- Dashboard: http://localhost:8501
- Worker logs: `docker compose logs -f worker`

---

## Ollama Integration & Tool Calling

The worker implements **native Ollama tool calling** via the `/api/chat` endpoint.

- **Tool definition:** `record_sentiment(ticker, score, catalyst, confidence)`
- **Tool execution:** The worker parses `message.tool_calls` from the Ollama response and invokes the local `database.record_sentiment(...)` function.
- **Model selection:** The active model is stored in the Postgres `config` table under key `selected_model`. The worker queries this table at the start of each run. The Streamlit dashboard writes to it when the user selects a different model from the dropdown.
- **Dashboard model polling:** `dashboard.py` calls `$OLLAMA_HOST/api/tags` to populate the model selector.

When modifying Ollama prompts or tool schemas, always keep `record_sentiment` as the single tool. Do not change the JSON schema without updating the parsing logic in `worker.py`.

---

## Database Schema (`database.py`)

### `sentiments`
- `id` (PK)
- `ticker` (String, indexed)
- `sentiment_score` (Float, -1.0 to 1.0)
- `delta_24h` (Float, default 0.0. Computed as `current_score - AVG(score over last 24h)`)
- `catalyst` (Text)
- `timestamp` (DateTime, UTC)

### `config`
- `key` (String, PK)
- `value` (Text)

Used for dynamic model selection. Do not add heavy generic config here; prefer `.env` for static values.

---

## Environment Variables

All values must be set in `.env`. **Never commit `.env`**.

| Variable | Required? | Description |
|----------|-----------|-------------|
| `POSTGRES_USER` | Yes | |
| `POSTGRES_PASSWORD` | Yes | |
| `POSTGRES_DB` | Yes | |
| `POSTGRES_HOST` | Yes | Usually `db` inside Docker network |
| `POSTGRES_PORT` | Yes | Usually `5432` |
| `NEWS_API_KEY` | Yes | |
| `OLLAMA_HOST` | Yes | e.g. `http://192.168.1.100:11434` |
| `INITIAL_MODEL` | No | Fallback model if `config` table has no selection |
| `WATCHLIST` | No | e.g. `AAPL,MSFT,NVDA` |

---

## Dockerfile & Multi-Stage Notes

- **Builder stage** installs `gcc`, `musl-dev`, `postgresql-dev`, `libffi-dev`, then creates **two separate venvs** (`/opt/venv-worker`, `/opt/venv-dashboard`).
- **Worker stage** copies only the worker venv + `libpq`.
- **Dashboard stage** copies the dashboard venv (includes Streamlit + Plotly) + `libpq`.
- Both final stages are **Alpine-based**. Do not add heavy Debian packages to keep image size small.

If you add a Python dependency that requires a C compiler, add the necessary Alpine `apk` package in the `builder` stage only.

---

## Worker Scheduling

APScheduler runs `run_analysis()` on an **interval of 4 hours**. An initial run fires immediately on container start. Do not lower the interval below NewsAPI rate limits unnecessarily.

---

## Dashboard Features

1. **Searchable ticker table** with sortable `delta_24h`.
2. **LEAPS Alert**: Highlights rows where `Score > 0.6` AND `Delta > 0.3`.
3. **Trend Chart**: 7-day Plotly line chart for multi-ticker comparison.
4. **Model Selector**: Sidebar dropdown polling Ollama `/api/tags`. Changing the model updates the `config` DB row. Worker picks it up on its next run.

---

## Common Agent Tasks

- **Add a new data source:** Modify `worker.py` → new `fetch_*` function → append texts to `all_texts` in `run_analysis()`.
- **Change schedule:** Edit `scheduler.add_job(run_analysis, "interval", hours=4)` in `worker.py`.
- **Add DB columns:** Update `database.py` model → rebuild containers (`docker compose up --build`). For migrations, add Alembic if needed; currently the schema is auto-created by `init_db()`.
- **Add dashboard pages:** Modify `dashboard.py`. Keep layout wide, use `st.set_page_config(layout="wide")`.
- **Update requirements:** Add to `requirements.txt` (or `requirements-dashboard.txt`), then rebuild.

---

## Important Conventions

- **Keep `.env` out of Git.** It is already in `.gitignore`.
- **Do not hardcode credentials** in Python files.
- **Maintain Ollama Tool Calling compatibility.** If Ollama changes its `/api/chat` response format, `worker.py` must be updated to handle `message.tool_calls`.
- **Use UTC for all timestamps.** The SQLAlchemy models default to `datetime.utcnow`.
- **Alpine constraints:** Prefer `apk` packages in builder stage. Final stages only need runtime libs (e.g., `libpq`).
