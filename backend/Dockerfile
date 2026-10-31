FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS build
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN uv sync --frozen --no-dev

FROM python:3.15-slim-bookworm
# T21 will add Pandoc and Chromium.
RUN useradd --create-home --uid 10001 qbank
WORKDIR /app
COPY --from=build --chown=qbank:qbank /app /app
ENV PATH="/app/.venv/bin:$PATH"
USER qbank
CMD ["uvicorn", "qbank.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
