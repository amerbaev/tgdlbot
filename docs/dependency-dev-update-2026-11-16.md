# Проверка dev-зависимостей — 16 ноября 2026

Задача: [#3](https://github.com/amerbaev/tgdlbot/issues/3).
База: `ec5f7efab390195183bc91d1aa53732300bdfacd` (актуальный master,
включая влитый PR #2). Исходный checkout чистый; открытых issues/PR до
начала работы не было. Прочитаны AGENTS.md, CLAUDE.md и инструкции облака;
`.agents/skills` в репозитории, workspace и home отсутствуют.

## Обновления и совместимость

| Пакет | Было | Стало | Основание |
|---|---|---|---|
| coverage | 7.17.2 | 7.17.3 | [Changelog](https://coverage.readthedocs.io/en/7.17.3/changes.html): исправления fork/subprocess, объединения данных и JSON-отчётов |
| pytest-asyncio | 1.4.1.post1 | 1.5.0 | [Changelog](https://pytest-asyncio.readthedocs.io/en/stable/reference/changelog.html): новый opt-in fixture-scope и диагностика неверных asyncio markers |

Обновлены только две записи пакетов в uv.lock, командой
`uv lock --upgrade-package coverage --upgrade-package pytest-asyncio`
(uv 0.13.8, Python 3.14.10). Manifest уже допускает новые версии;
`asyncio_mode=auto` и текущая семантика loop scope сохранены.
pytest-asyncio требует Python >=3.10 и pytest >=8.4; coverage — Python >=3.11.
В проекте Python 3.14.10 и pytest 9.2.0. Настройки покрытия приложения
и тесты не менялись; для изменения границ совместимости оснований нет.

Все 25 сторонних пакетов сверены с текущими PyPI JSON API. Остальные 23
пакета уже соответствуют последним стабильным версиям в полученном снимке,
включая python-telegram-bot 22.8, yt-dlp 2026.10.26, yt-dlp-ejs 0.8.0,
Deno 2.9.8, curl-cffi 0.17.0, certifi 2026.10.23, python-dotenv 1.2.4.
Metadata yt-dlp сохраняет EJS ==0.8.0 и curl-cffi <0.18.
Все **197 SHA-256** артефактов lockfile совпадают с version-specific PyPI
metadata, отозванных артефактов нет. Runtime records идентичны master.

## Проверки

| Проверка | Результат |
|---|---|
| Baseline полный pytest, Python 3.14.10, FFmpeg 7.1.5 | 239 passed, 17 subtests passed, exit 0 |
| Обновлённый полный pytest с покрытием | 239 passed, 17 subtests passed, exit 0; 93%, 585/629 statements |
| Locked sync, offline lock check, uv pip check | Успешно |
| pip-audit 2.10.1 до/после, все 25 пакетов включая Windows-only colorama | 0/0 известных уязвимостей |
| Docker test target build, `--pull` | Успешно; uv 0.13.7 из неизменённого Dockerfile |
| Docker test target, `--network none` | 228 passed, 11 skipped, exit 0; target не содержит FFmpeg |
| Dockerfile build check | Успешно, предупреждений нет |
| `git diff --check`; сравнение package records | Успешно; изменены только coverage и pytest-asyncio |

11 тестов с реальным FFmpeg выполняются в полном локальном прогоне,
в том числе проверки сохранения кадров после PR #1. Сохраняются три прежних
DeprecationWarning в python-telegram-bot и предупреждение о неявном fixture
loop scope; это не новые падения.

Облачная Docker-сборка использовала временную копию Dockerfile с BuildKit
secret mount системного CA только на шагах uv sync. TLS-проверка включена,
CA не записан в образ или git. Аудитор установлен отдельно от проекта.
Списки для pip-audit полностью закреплены, без platform markers;
`--no-deps --disable-pip` исключает повторное разрешение зависимостей.

Обновление builder uv и полный свежий аудит runtime/ОС ведутся независимо
в [задаче #4](https://github.com/amerbaev/tgdlbot/issues/4). Этот отчёт не
заявляет отсутствие уязвимостей Debian. Python 3.14.10 остаётся последним
patch-релизом ветки 3.14 по [python.org](https://www.python.org/downloads/);
переход на 3.15 — отдельная миграция.

Живые запросы к Telegram/YouTube/Instagram, merge, auto-merge и deploy
не выполнялись. Полные логи, metadata, export с хешами и отчёты аудиторов:
`/workspace/dependency-audit-2026-11-16/evidence`.
Ключевые файлы: `pypi-summary.json`, `lock-validation.json`,
`baseline-tests.log`, `dev-tests.log`, `coverage.xml`,
`baseline-pip-audit.json`, `dev-pip-audit.json`, `dev-docker-build.log`,
`dev-docker-tests.log`.
