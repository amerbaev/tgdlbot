# Проверка зависимостей — 9 ноября 2026

Работа выполнена в облачной среде `tgdlbot`, в отдельной ветке
`chore/deps-2026-11-09`, после чтения `AGENTS.md` и `git fetch origin --prune`.
База: `origin/master` — `29660ff0f4e84a0b7a87bb6002a747779b6514e3`.
Этот master уже содержит исправление кадров из PR #1; отдельная ветка
`fix/video-split-frame-loss` не менялась.

## Изменения

| Зависимость | Было → стало | Причина |
|---|---|---|
| coverage, транзитивная dev-зависимость pytest-cov | 7.17.0 → 7.17.2 | Исправления подсчёта покрытия и объединения SQLite-файлов; 7.17.1 также усиливает обработку поддельных SQLite journal-файлов. [Changelog](https://coverage.readthedocs.io/en/7.17.2/changes.html) |
| uv, Docker builder | 0.13.6 → 0.13.7 | Стабильный patch-релиз с исправлениями управления workspace, запуска инструментов и конфигурации. [Release](https://github.com/astral-sh/uv/releases/tag/0.13.7) |
| zlib1g, production Debian | 1:1.3.dfsg+really1.3.1-1+b1 → 1:1.3.dfsg+really1.3.1-1+deb13u1 | Исправления CVE-2026-27171, CVE-2026-76844, CVE-2026-85091. [DSA-6613-1](https://lists.debian.org/debian-security-announce/2026/msg00532.html) |

В Dockerfile `zlib1g` явно включён в `apt-get install`: даже свежий
`python:3.14-slim` ещё содержит старую версию, а установка только ffmpeg и
ca-certificates не заставляет APT обновить уже удовлетворённую зависимость.
Финальная сборка получает security-версию из штатных репозиториев Debian.
После неё `apt-get update && apt-get -s upgrade` сообщает **0 обновлений**.

`uv.lock` пересоздан командой `uv lock --upgrade` с uv 0.13.7 и Python 3.14.10.
Изменился только coverage; пакеты не добавлялись и не удалялись, остальные
25 package records (включая проект) идентичны исходным. Revision остаётся 5.
Все **197 SHA-256** артефактов сверены с version-specific JSON API PyPI;
отозванных артефактов нет. Manifest `pyproject.toml` не требует изменения.

## Полный состав lockfile

Для всех 25 сторонних пакетов проверены текущие стабильные версии через
`https://pypi.org/pypi/<name>/json`, требования Python, metadata выбранной версии
и известные уязвимости. На дату проверки итоговый lockfile совпадает с последними
стабильными релизами в полученном снимке PyPI.

| Пакет | Итоговая версия |
|---|---|
| anyio | 4.16.0 |
| certifi | 2026.10.23 |
| cffi | 2.1.1 |
| colorama | 0.4.6 |
| coverage | 7.17.2 |
| curl-cffi | 0.17.0 |
| deno | 2.9.8 |
| h11 | 0.16.0 |
| httpcore | 1.0.9 |
| httpx | 0.28.1 |
| idna | 3.20 |
| iniconfig | 2.3.1 |
| packaging | 26.3 |
| pluggy | 1.7.0 |
| pycparser | 3.12 |
| pygments | 2.21.0 |
| pytest | 9.2.0 |
| pytest-asyncio | 1.4.1.post1 |
| pytest-cov | 7.1.0 |
| pytest-mock | 3.17.0 |
| python-dotenv | 1.2.4 |
| python-telegram-bot | 22.8 |
| typing-extensions | 4.16.0 |
| yt-dlp | 2026.10.26 |
| yt-dlp-ejs | 0.8.0 |

Связка yt-dlp/EJS/Deno сохранена: metadata yt-dlp требует EJS ==0.8.0,
Deno >=2.9.8 и curl-cffi <0.18. Реальный Deno provider и соответствие версии
EJS проверяются офлайн-тестами проекта.

## Образ и аудит безопасности

Сборка использует официальный `python:3.14-slim`, полученный с `--pull`:

- Base digest: `sha256:9aaa474097d094040649f2162a627c0049b408f52138d980916788d80f04802f`.
- Python 3.14.10, Debian 13.7, ffmpeg `7:7.1.5-0+deb13u1`.
- ca-certificates `20250419+deb13u1`, openssl `3.5.7-1~deb13u3`.
- libxml2 `2.12.7+dfsg+really2.9.14-2.1+deb13u3`.
- Production image ID: `sha256:3d1ad3ecab39b3fc1e587c5b3fe8ce4843f616c054696f02e58bee659a2a049d`.

**Python:** pip-audit 2.10.1 проверил все 25 пакетов до и после обновления,
включая dev и Windows-only colorama: **0 известных уязвимостей**. Для этого
использованы полностью закреплённые списки из lockfile без platform markers,
`--no-deps --disable-pip`; зависимости заново не разрешались.
Обычный экспорт uv с хешами также сохранён.

**Контейнер:** Trivy 0.76.2, база от `2026-11-09T06:57:06Z`, просканировал
локальные `docker save` архивы. Бинарник Trivy скачан из официального релиза,
SHA-256 архива проверен по опубликованному checksums-файлу.

| Срез | До обновления zlib | Финальный production |
|---|---:|---:|
| Debian-пакеты | 292 | 292 |
| Пары пакет–advisory | 809 | 806 |
| Уникальные advisory ID | 285 | 282 |
| Находки с доступной исправленной версией | 3 | 0 |
| Runtime Python-пакеты / находки | 15 / 0 | 15 / 0 |

Три устранённые находки относятся к zlib из DSA-6613-1.
**Аудит ОС остаётся нечистым:** 1 critical, 225 high, 359 medium, 201 low,
20 unknown. Эти числа — совпадения пакет–advisory, а не количество разных CVE
и не доказательство достижимости всех уязвимостей через бота. Нулевой exit code
Trivy означает завершение сканирования; находки не подавлялись.

Старые замечания перепроверены по свежей базе и Debian Security Tracker:

- [CVE-2026-120210](https://security-tracker.debian.org/tracker/CVE-2026-120210)
  и [CVE-2026-107697](https://security-tracker.debian.org/tracker/CVE-2026-107697)
  остаются в ffmpeg 7.1.5 для trixie; исправления помечены postponed до
  исправления ветки upstream 7.1.x.
- [CVE-2026-6653](https://security-tracker.debian.org/tracker/CVE-2026-6653)
  остаётся в libxml2. Trivy присваивает critical; Debian отмечает minor/no-dsa.
  Разница оценок не скрывает саму находку.

Обновление на другой дистрибутив или новую major-версию FFmpeg в этот PR
не включено. Остаточные OS findings требуют отдельного решения; этот PR
не делает образ свободным от известных уязвимостей.

## Проверки

| Проверка | Результат |
|---|---|
| Baseline, Python 3.14.10 и системный ffmpeg 7.1.5 | 239 passed, 17 subtests passed |
| `uv sync --locked --extra dev`, `uv lock --check --offline`, `uv pip check` | Успешно |
| Обновлённый полный pytest с pytest-cov | 239 passed, 17 subtests passed; exit 0; покрытие 93%, 585/629 statements |
| Проверка metadata и SHA-256 lockfile | 25 пакетов, 197 хешей, 0 отозванных артефактов |
| pip-audit baseline / итоговый lockfile | 25 / 25 пакетов, 0 / 0 находок |
| Docker production и test build | Успешно с временным CA mount для облачного прокси |
| `docker build --check` итогового Dockerfile | Успешно, предупреждений нет |
| Compose config на копии YAML с `.env.example` | Успешно |
| Штатный test target, `--network none` | 228 passed, 11 skipped (в target нет ffmpeg) |
| Финальный production + dev-зависимости, UID 1000, `--network none` | 239 passed, 17 subtests passed; exit 0 |
| Финальный production smoke, UID 1000, `--network none` | Импорты, writable downloads, Deno provider, отсутствие токена/pip/ensurepip/uv — успешно |
| Финальный APT upgrade simulation | 0 обновлений |
| Trivy финального production | Выполнен; 0 Python findings, 806 OS matches без доступных fixes |

В pytest остаются прежние 3 DeprecationWarning от python-telegram-bot и
предупреждение pytest-asyncio о неявном scope async fixtures.

Первичные неуспешные проверки и их ограничения:

- Запись кэшей uv/pip-audit/buildx в read-only home не удалась; кэши перенесены
  в каталог задачи, глобальные настройки не менялись.
- Обычная Docker-сборка остановилась на `UnknownIssuer` при загрузке wheels.
  В локальной копии Dockerfile добавлен BuildKit secret mount системного CA
  bundle и `SSL_CERT_FILE` только к двум `uv sync`. TLS-проверка включена;
  сертификат не попадает в слои. Репозиторный Dockerfile не содержит
  специфических для облака сертификатов или настроек.
- Первая команда обновлённых тестов вернула код 1 при отчёте 239 passed без
  traceback. Повтор той же проверки через `subprocess.run` подтвердил код 0;
  оба лога сохранены. Изменений кода для этого не потребовалось.
- Проверка Compose напрямую не прошла из-за отсутствующего приватного `.env`,
  даже с `--no-env-resolution`. Структура проверена на точной копии YAML с
  примером окружения; настоящий токен не использовался.
- Первый вспомогательный verify image не смог прочитать root-owned
  `pyproject.toml`. В его локальном Dockerfile исправлен только владелец
  копируемых test-файлов и dev-venv (`--chown=appuser:appuser`).

Не запускались: живые скачивания YouTube/Instagram, Telegram-запросы с реальным
токеном, Windows/ARM/Python 3.15, деплой и слияние в master. Приложение и тесты
репозитория не менялись.

## Артефакты и воспроизведение

Логи и metadata сохранены в `/workspace/dependency-audit-2026-11-09/evidence`:
`pypi-summary.json`, `pypi-locked-*.json`, `lock-validation.json`,
`dependency-diff.json`, `baseline-tests.log`, `updated-tests-verified.log`,
`updated-tests-exit.json`, `coverage.xml`, `baseline-pip-audit.json`,
`updated-pip-audit.json`, `docker-production-final-build.log`, `docker-test.log`,
`docker-verify-tests.log`, `production-final-smoke.log`,
`container-final-packages.txt`, `apt-final-upgradable.log`,
`trivy-production-final.json`, `trivy-final-summary.json` и архивы образов.
Вспомогательные Dockerfile и smoke script лежат рядом в `tooling`.
Они не включены в runtime или git.

Основные команды из checkout (uv 0.13.7, Python 3.14, ffmpeg в PATH):

```sh
uv sync --locked --extra dev --python 3.14
uv lock --check --offline
uv pip check
uv run --locked pytest tests/ -v --cov=bot --cov=config --cov=media --cov=platforms
uv export --locked --extra dev --no-emit-project -o requirements.txt
docker build --pull --target production -t tgdlbot:deps-2026-11-09-production .
docker build --target test -t tgdlbot:deps-2026-11-09-test .
docker build --check .
docker run --rm --network none tgdlbot:deps-2026-11-09-test
```

В этой облачной среде Docker build использует
`-f /workspace/dependency-audit-2026-11-09/tooling/Dockerfile.cloud`
и `--secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt`.
Для доступа к writable кэшам задавались `UV_CACHE_DIR`, `UV_TOOL_DIR`
и `BUILDX_CONFIG` внутри каталога задачи.
