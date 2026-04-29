# syntax=docker/dockerfile:1
ARG PYTHON_VERSION=3.12

FROM python:${PYTHON_VERSION}-alpine AS builder
WORKDIR /app
RUN apk add --no-cache gcc musl-dev postgresql-dev

# Single venv with all deps
RUN python -m venv /opt/venv
COPY requirements.txt .
COPY requirements-dashboard.txt .
RUN /opt/venv/bin/pip install --no-cache-dir -r requirements.txt
RUN /opt/venv/bin/pip install --no-cache-dir -r requirements-dashboard.txt

# --- Worker target ---
FROM python:${PYTHON_VERSION}-alpine AS worker
WORKDIR /app
RUN apk add --no-cache libpq
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY database.py worker.py ./
CMD ["python", "worker.py"]

# --- Dashboard target ---
FROM python:${PYTHON_VERSION}-alpine AS dashboard
WORKDIR /app
RUN apk add --no-cache libpq
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY database.py dashboard.py ./
EXPOSE 8501
CMD ["streamlit", "run", "dashboard.py", "--server.port=8501", "--server.address=0.0.0.0"]