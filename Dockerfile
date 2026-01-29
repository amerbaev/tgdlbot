# ==========================================
# Stage 1: Builder (установка зависимостей)
# ==========================================
FROM python:3.13-slim AS builder

WORKDIR /app

# Копирование файлов проекта
COPY pyproject.toml uv.lock ./

# Установка uv
RUN pip install --no-cache-dir uv

# Установка ТОЛЬКО production зависимостей
RUN uv sync --frozen --no-dev


# ==========================================
# Stage 2: Production
# ==========================================
FROM python:3.13-slim AS production

LABEL maintainer="tgdlbot"
LABEL description="Telegram YouTube Downloader Bot"

# Минимальная установка ffmpeg
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

WORKDIR /app

# Установка uv (нужен для запуска)
RUN pip install --no-cache-dir uv

# Копирование virtualenv из builder
COPY --from=builder /app/.venv /app/.venv

ENV PYTHONUNBUFFERED=1

# Копирование кода приложения
COPY bot.py config.py ./
COPY platforms ./platforms/

# Создание директории для загрузок
RUN mkdir -p downloads

# Неглавный пользователь
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app
USER appuser

CMD ["uv", "run", "python", "bot.py"]


# ==========================================
# Stage 3: Test
# ==========================================
FROM python:3.13-slim AS test

WORKDIR /app

# Установка uv
RUN pip install --no-cache-dir uv

# Копирование .venv из builder
COPY --from=builder /app/.venv /app/.venv

# Копирование кода и тестов
COPY pyproject.toml uv.lock ./
COPY bot.py config.py ./
COPY platforms ./platforms/
COPY tests ./tests/

# Доустановка dev зависимостей
RUN uv sync --extra dev

CMD ["uv", "run", "pytest", "tests/", "-v"]
