# syntax=docker/dockerfile:1

FROM python:3.14-slim AS base

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"


# Зависимости кешируются отдельно от исходного кода.
FROM base AS builder

COPY --from=ghcr.io/astral-sh/uv:0.12.15 /uv /usr/local/bin/uv

ENV UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

COPY pyproject.toml uv.lock ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project


# Тестовые зависимости дополняют готовое production-окружение.
FROM builder AS test-builder

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --extra dev --no-install-project


FROM base AS production

LABEL maintainer="tgdlbot"
LABEL description="Telegram YouTube Downloader Bot"

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean \
    && useradd -m -u 1000 appuser \
    && install -d -o appuser -g appuser /app /app/downloads

# Владельца задаём при копировании, не дублируя .venv слоем chown -R.
COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv
COPY --chown=appuser:appuser bot.py config.py ./
COPY --chown=appuser:appuser platforms ./platforms/

USER appuser

CMD ["python", "bot.py"]


FROM base AS test

COPY --from=test-builder /app/.venv /app/.venv
# pyproject.toml содержит настройки pytest, включая asyncio_mode.
COPY pyproject.toml ./
COPY bot.py config.py ./
COPY platforms ./platforms/
COPY tests ./tests/

CMD ["python", "-m", "pytest", "tests/", "-v"]
