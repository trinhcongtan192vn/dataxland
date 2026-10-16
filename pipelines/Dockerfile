# pipelines – Dagster webserver và daemon, dlt, dbt (spec 04 §3). Build từ thư mục gốc của repo.
FROM python:3.12.8-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /bin/uv
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /repo
COPY pyproject.toml uv.lock ./
COPY libs/dx_common libs/dx_common
COPY services services
COPY pipelines pipelines
RUN uv sync --frozen --no-dev --package dx-pipelines --extra gcp
COPY transform transform
COPY tenants tenants
COPY ops ops
COPY semantic semantic
ENV PATH="/repo/.venv/bin:$PATH" DX_REPO_ROOT=/repo DAGSTER_HOME=/opt/dagster/home
RUN cd transform && dbt deps --profiles-dir . || true
RUN mkdir -p /opt/dagster/home
COPY pipelines/dagster.yaml /opt/dagster/home/dagster.yaml
COPY pipelines/workspace.yaml /opt/dagster/workspace.yaml
WORKDIR /repo/pipelines
EXPOSE 3001
