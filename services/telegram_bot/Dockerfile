# services/telegram_bot (spec 08 §1). Build từ thư mục gốc của repo.
FROM python:3.12.8-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /bin/uv
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /repo
COPY pyproject.toml uv.lock ./
COPY libs/dx_common libs/dx_common
COPY services services
COPY pipelines/pyproject.toml pipelines/pyproject.toml
RUN mkdir -p pipelines/dx_pipelines pipelines/connectors && touch pipelines/dx_pipelines/__init__.py pipelines/connectors/__init__.py
RUN uv sync --frozen --no-dev --package dx-telegram-bot
ENV PATH="/repo/.venv/bin:$PATH"
WORKDIR /repo/services/telegram_bot
EXPOSE 8100
CMD ["python", "-m", "bot.main"]
