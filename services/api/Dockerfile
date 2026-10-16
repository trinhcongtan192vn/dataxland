# services/api – FastAPI và worker nền (spec 05 §1). Build từ thư mục gốc của repo.
FROM python:3.12.8-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /bin/uv
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /repo
COPY pyproject.toml uv.lock ./
COPY libs/dx_common libs/dx_common
COPY services services
COPY pipelines/pyproject.toml pipelines/pyproject.toml
RUN mkdir -p pipelines/dx_pipelines pipelines/connectors && touch pipelines/dx_pipelines/__init__.py pipelines/connectors/__init__.py
RUN uv sync --frozen --no-dev --package dx-api
COPY semantic/dist semantic/dist
COPY knowledge knowledge
COPY tenants tenants
ENV PATH="/repo/.venv/bin:$PATH" DX_REPO_ROOT=/repo
WORKDIR /repo/services/api
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
