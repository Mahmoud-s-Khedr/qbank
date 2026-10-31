FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS build
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN uv sync --frozen --no-dev

FROM python:3.12-slim-bookworm
# T22 will add Pandoc.
RUN useradd --create-home --uid 10001 qbank
WORKDIR /app
COPY --from=build --chown=qbank:qbank /app /app
ENV PATH="/app/.venv/bin:$PATH" \
    PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright
# Chromium (headless shell only) and its runtime libraries for PDF export; the browser is
# installed system-wide so the non-root user can run it, and apt caches are dropped to keep the
# image small. Fonts are vendored in the package, so no system fonts are needed.
RUN playwright install --with-deps --only-shell chromium \
    && rm -rf /var/lib/apt/lists/* /root/.cache
USER qbank
CMD ["uvicorn", "qbank.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
