# syntax=docker/dockerfile:1
ARG PYTHON_VERSION=3.12

FROM python:${PYTHON_VERSION}-alpine AS builder
WORKDIR /app
RUN apk add --no-cache gcc musl-dev postgresql-dev

# Create worker venv and install dependencies
RUN python -m venv /opt/venv-worker
COPY requirements.txt /tmp/requirements.txt
RUN /opt/venv-worker/bin/pip install --no-cache-dir -r /tmp/requirements.txt

# Create dashboard venv and install dependencies
RUN python -m venv /opt/venv-dashboard
COPY requirements.txt /tmp/requirements_worker.txt
COPY requirements-dashboard.txt /tmp/requirements_dashboard.txt
RUN /opt/venv-dashboard/bin/pip install --no-cache-dir -r /tmp/requirements_worker.txt
RUN /opt/venv-dashboard/bin/pip install --no-cache-dir -r /tmp/requirements_dashboard.txt

# --- Worker target ---
FROM python:${PYTHON_VERSION}-alpine AS worker
WORKDIR /app
RUN apk add --no-cache libpq
COPY --from=builder /opt/venv-worker /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY database.py worker.py ./
CMD ["python", "worker.py"]

# --- Dashboard target ---
FROM python:${PYTHON_VERSION}-alpine AS dashboard
WORKDIR /app
RUN apk add --no-cache libpq
COPY --from=builder /opt/venv-dashboard /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY database.py dashboard.py ./
EXPOSE 8501
CMD ["streamlit", "run", "dashboard.py", "--server.port=8501", "--server.address=0.0.0.0"]