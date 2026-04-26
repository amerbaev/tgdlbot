# tgdlbot - Telegram Video Downloader Bot

Telegram бот для скачивания видео с YouTube и Instagram.

## Особенности

- 🎬 Скачивание видео с **YouTube** и **Instagram**
- 🎯 Умный выбор качества (автоматически выбирает макс. качество в пределах 50MB)
- ✂️ Автоматическое разбиение больших видео на части по 50MB
- 📏 Проверка размера файла (лимит Telegram API)
- 📊 Прогресс загрузки с информативными сообщениями
- 🗑️ Автоматическое удаление временных файлов
- 🐳 Multi-stage Docker build
- 🔧 Модульная архитектура для лёгкого добавления новых платформ

## Требования

- Python 3.14+
- Docker (опционально)

## Быстрый старт

### Через Docker (рекомендуется)

1. **Клонируйте репозиторий**
   ```bash
   git clone <repository-url>
   cd tgdlbot
   ```

2. **Создайте файл `.env`**
   ```bash
   cp .env.example .env
   ```

3. **Получите токен бота**
   - Найдите [@BotFather](https://t.me/BotFather) в Telegram
   - Отправьте `/newbot`
   - Следуйте инструкциям
   - Скопируйте токен в `.env` файл:
     ```
     TELEGRAM_BOT_TOKEN=ваш_токен_здесь
     ```

4. **Запустите бота**
   ```bash
   docker-compose up -d
   ```

5. **Проверьте логи**
   ```bash
   docker-compose logs -f tgdlbot
   ```

6. **Остановка бота**
   ```bash
   docker-compose down
   ```

### Локальный запуск

1. **Установите зависимости**
   ```bash
   uv sync --extra dev
   ```

2. **Создайте `.env` файл** (см. выше)

3. **Запустите бота**
   ```bash
   uv run python bot.py
   ```

## Тестирование

Запустите тесты:

```bash
# Локально
uv run pytest tests/ -v

# В Docker
docker-compose run tgdlbot uv run pytest tests/ -v
```

## Использование

1. Отправьте `/start` для приветствия
2. Отправьте `/help` для справки
3. Отправьте ссылку на видео для скачивания

### Поддерживаемые платформы

#### YouTube
- `https://www.youtube.com/watch?v=...`
- `https://youtu.be/...`
- `https://www.youtube.com/shorts/...`

#### Instagram
- `https://www.instagram.com/p/...` (посты)
- `https://www.instagram.com/reel/...` (Reels)

## Структура проекта

```
tgdlbot/
├── bot.py              # Основной код бота
├── config.py           # Конфигурация
├── platforms/          # Модули платформ
│   ├── base.py         # Базовый класс
│   ├── youtube.py      # YouTube
│   └── instagram.py    # Instagram
├── tests/              # Тесты
│   ├── test_bot.py     # Тесты бота
│   └── platforms/      # Тесты платформ
├── downloads/          # Временные файлы (gitignore)
├── .env.example        # Пример переменных окружения
├── Dockerfile          # Docker образ
├── docker-compose.yml  # Docker Compose конфигурация
├── pyproject.toml      # Зависимости проекта
└── README.md           # Этот файл
```

## Ограничения

- Максимальный размер файла: 50MB (лимит Telegram API)
- Поддерживаются только публичные видео (Instagram)
- Требуется ffmpeg для разбиения больших файлов

## Качество видео

### YouTube
Бот автоматически выбирает лучшее качество с учетом ограничений:

1. **Приоритет**: 1080p → 720p → 480p → 360p
2. **Smart skip**: Пропускает 1080p/720p если размер > 75MB
3. **Разбиение**: Если видео > 50MB, автоматически разбивается на части

### Instagram
- Скачивается лучшее доступное качество
- Автоматическое разбиение если > 50MB

### Примеры:

| Исходное качество | Размер | Результат |
|-------------------|--------|-----------|
| 1080p (YouTube) | 30MB | ✅ Отправлено целиком (1080p) |
| 1080p (YouTube) | 80MB | ✅ Отправлено целиком (720p или ниже) |
| 720p (YouTube) | 60MB | ✅ Разбито на 2 части по ~45MB |
| Лучшее (Instagram) | 55MB | ✅ Разбито на 2 части |

## Разработка

### Архитектура платформ

Платформы реализованы через базовый класс `BasePlatform`:

```python
class BasePlatform(ABC):
    @property
    def name(self) -> str: ...

    @property
    def url_pattern(self) -> str: ...

    def is_valid_url(self, url: str) -> bool: ...

    def get_format_options(self, info: dict) -> List[Tuple[str, Optional[dict]]]: ...
```

### Добавление новой платформы

1. Создайте файл в `platforms/`
2. Наследуйтесь от `BasePlatform`
3. Реализуйте методы
4. Добавьте в `platforms/__init__.py` и `bot.py`

### Добавление зависимостей

```bash
uv add package_name
```

### Запуск с автоперезагрузкой

Для разработки с горячей перезагрузкой используйте:

```bash
uv pip install watchfiles
uv run watchfiles python bot.py
```

## Лицензия

MIT License
