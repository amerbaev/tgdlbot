# Проверка зависимостей — 2 ноября 2026

Подготовлено на `valut101` в ветке `chore/deps-2026-11-02` от локального
`master` (`27880a078f237beda5766f57c91be693c07f8545`). Worktree:
`C:\Users\amerb\Documents\Codex\2026-11-02\task\tgdlbot`.
Исходный checkout и четыре существовавших worktree были чистыми. Прочитаны
`AGENTS.md`, инструкции тестирования, Dockerfile и предыдущий отчёт.
Native worktree API вернул `Cloud worktrees are unavailable`, поэтому новый
worktree создан через Git в каталоге этой задачи.

Изменены manifest, lockfile и production-слой Dockerfile. Код бота и завершённые
исправления YouTube/Deno/EJS сохранены. Слияние, push, деплой и запуск бота
с настоящим токеном не выполнялись. Основные `.venv`, `.env`, cookies,
глобальные инструменты и настройки безопасности не менялись.

## Обновления

Проверены все 25 сторонних пакетов lockfile, включая dev-зависимости, через
официальный JSON API `https://pypi.org/pypi/<package>/json` и changelog проектов.
Выбраны стабильные, не отозванные релизы. Все 25 зафиксированных версий совпали
с последними релизами в полученном снимке PyPI; изменились ровно 10 пакетов,
добавлений и удалений нет.

| Пакет | Было → стало | Причина / первичный источник |
|---|---|---|
| python-dotenv | 1.2.3 → 1.2.4 | Исправление пустых значений с inline-комментарием и CLI precedence: [changelog](https://github.com/theskumar/python-dotenv/blob/main/CHANGELOG.md#124---2026-10-01) |
| pytest | 9.1.1 → 9.2.0 | Плановый стабильный релиз, исправления диагностики и тестового запуска: [changelog](https://docs.pytest.org/en/stable/changelog.html#pytest-9-2-0-2026-10-27) |
| pytest-asyncio | 1.4.0 → 1.4.1.post1 | Исправления типов async fixtures; post1 снимает верхнюю границу pytest: [changelog](https://pytest-asyncio.readthedocs.io/en/stable/reference/changelog.html) |
| pytest-mock | 3.15.1 → 3.17.0 | Исправления reset/stop spies и диагностики mock assertions: [changelog](https://pytest-mock.readthedocs.io/en/latest/changelog.html) |
| anyio | 4.15.1 → 4.16.0 | Исправления отмены задач и закрытия/отправки сокетов, существенные для httpx: [version history](https://anyio.readthedocs.io/en/stable/versionhistory.html) |
| coverage | 7.16.1 → 7.17.0 | Исправления учёта ветвей, XML и объединения данных: [changes](https://coverage.readthedocs.io/en/7.17.0/changes.html) |
| idna | 3.19 → 3.20 | Unicode 18 и контроль длины домена в incremental codec: [history](https://github.com/kjd/idna/blob/master/HISTORY.md) |
| iniconfig | 2.3.0 → 2.3.1 | Устранены квадратичный разбор continuation lines и ошибка UTF-8 BOM: [changelog](https://github.com/pytest-dev/iniconfig/blob/main/CHANGELOG) |
| pluggy | 1.6.0 → 1.7.0 | Исправление регистрации hooks с forward annotations на Python 3.14+: [changelog](https://pluggy.readthedocs.io/en/stable/changelog.html) |
| pycparser | 3.0 → 3.12 | Исправления C parser / C11; совместимость с cffi проверена: [releases](https://github.com/eliben/pycparser/releases) |

В `pyproject.toml` повышены минимумы четырёх прямых зависимостей. Транзитивные
версии закреплены в `uv.lock`; существующие security constraints сохранены.
Lockfile создан `uv 0.13.6` командой `uv lock --upgrade --python 3.14`;
его revision изменился с 3 на 5. Все **197 SHA-256** артефактов сверены с PyPI; хеши
вручную не редактировались. SHA-256 файла до Git-нормализации строк:
`18a41d3ff97fad355d09e96ce50ddf3a16c9ba357f510bbfc044a7dd3df38126`.

Требования новых пакетов допускают Python 3.14. Проверены Windows CPython
3.14.7 и Linux CPython 3.14.10. Сочетание pytest 9.2.0, pytest-asyncio
1.4.1.post1, pytest-mock 3.17.0 и pytest-cov 7.1.0 прошло полный набор тестов.
Переход Python на 3.15 в эту проверку не включён.

Оставлены актуальные python-telegram-bot 22.8, yt-dlp 2026.10.26,
yt-dlp-ejs 0.8.0, Deno 2.9.8, curl-cffi 0.17.0, certifi 2026.10.23 и
pytest-cov 7.1.0. В metadata yt-dlp по-прежнему указаны EJS ==0.8.0,
Deno >=2.9.8 и curl-cffi <0.18. Существующая граница бота с реальным
yt-dlp/Deno проверена офлайн-тестами.

## Образ и безопасность

[uv 0.13.6](https://github.com/astral-sh/uv/releases/tag/0.13.6) остаётся
актуальным. Локально использован отдельный бинарник в каталоге задачи;
SHA-256 ранее скачанного архива совпал с checksum-файлом. Глобальный uv 0.9.28
не обновлялся. Docker client/server 29.9.2 соответствует последнему релизу
ветки 29 в [официальных release notes](https://docs.docker.com/engine/release-notes/29/).

Сборка `--pull` использует [официальный python:3.14-slim](https://hub.docker.com/_/python):
Python 3.14.10, Debian 13.7, ffmpeg `7:7.1.5-0+deb13u1`.
Базовый digest: `sha256:930e1abba7c4e8f96ed93e8012c35d174d7732752731bbd5e8e757d7ec6f3966`.
APT update/install действительно выполнен заново в финальной сборке.

`pip-audit 2.10.1` по полному экспорту lockfile с dev-зависимостями:
**25 пакетов, известных уязвимостей не найдено**, до и после обновления.

Первый аудит образа Trivy нашёл ещё **8 advisory matches** в msgpack 1.1.2,
setuptools 70.3.0 и urllib3 2.7.0 внутри системного pip 26.2.2. Они отсутствуют
в окружении бота, но входят в базовый образ; версии подтверждены реальным
`pip/_vendor/vendor.txt` и [официальным файлом pip](https://github.com/pypa/pip/blob/26.2.2/src/pip/_vendor/vendor.txt).
Обновление pip не решает проблему: 26.2.2 уже последний релиз на дату проверки.

В production удалены pip и bundled wheel из ensurepip вместе с модулем
bootstrap. Установка зависимостей остаётся в builder через uv; builder и test
сохраняют инструменты установки. Установить новые пакеты через pip/ensurepip
в готовом production-контейнере теперь нельзя — следует пересобирать образ.
Отсутствие pip/ensurepip проверено, затем повторены сборка, тесты и аудит.
В финальном образе Trivy видит **15 runtime Python-пакетов, 0 находок**.

**Аудит ОС не чистый.** Trivy 0.76.1 с базой от
`2026-11-02T07:17:05Z` обнаружил 809 пар «пакет–advisory» для 292 Debian-пакетов:
282 уникальных ID; 1 critical, 208 high, 319 medium, 195 low, 86 unknown.
Для этих записей сканер не сообщает доступной исправленной версии в Debian 13.
Это не 809 разных CVE и не доказательство достижимости каждого дефекта ботом.
Итоговый JSON сохранён без подавления findings.

- Для ffmpeg остаются, например, [CVE-2026-120210](https://security-tracker.debian.org/tracker/CVE-2026-120210)
  и [CVE-2026-107697](https://security-tracker.debian.org/tracker/CVE-2026-107697).
  Debian отмечает исправления trixie как postponed до исправления upstream 7.1.x.
- Единственная critical-метка относится к libxml2
  [CVE-2026-6653](https://security-tracker.debian.org/tracker/CVE-2026-6653).
  Debian подтверждает affected-версию, но оценивает проблему как minor/no-dsa;
  оценки severity источников различаются. Находка не скрыта.
- Миграция дистрибутива или самостоятельная сборка новой major-версии ffmpeg
  здесь не выполнялась. Открытые OS findings остаются существенным ограничением
  безопасности образа и требуют отдельного решения перед эксплуатацией.

Для [GHSA-6q48-6c7w-9gw2](https://github.com/advisories/GHSA-6q48-6c7w-9gw2)
проверено отсутствие `emSign ECC Root CA - G3` в фактически загруженных
certifi и системном SSL store. Deno 2.9.8 уже содержит исправление доверия CA
в [официальном релизе](https://github.com/denoland/deno/releases/tag/v2.9.8).

## Фактически выполненные проверки

| Проверка | Результат |
|---|---|
| Исходный полный pytest, Windows Python 3.14.7, ffmpeg 8.1 | 234 passed, 9 subtests passed |
| Обновлённый полный pytest + pytest-cov, Windows | 234 passed, 9 subtests passed; покрытие 93% (585/629 statements) |
| `uv sync --locked --extra dev --python 3.14` | Успешно, отдельная `.venv` |
| `uv lock --check --offline`, `uv pip check` | Успешно, зависимости согласованы |
| Сравнение lockfile с исходным и metadata PyPI | 10 обновлений, 0 добавлений/удалений, 197 хешей совпали |
| pip-audit полного lockfile | 0 известных уязвимостей, 25 пакетов |
| Docker production и test build | Успешно |
| Штатный Docker test target, `--network none` | 228 passed, 6 skipped: target не содержит ffmpeg |
| Финальный production-derived verify image с dev-окружением и ffmpeg | 234 passed, 9 subtests passed; UID 1000, `--network none` |
| `docker build --check`, Compose config с `--no-env-resolution` | Успешно; Dockerfile без предупреждений |
| Production smoke после удаления pip | Импорты, UID, writable downloads, отсутствие токена/pip/ensurepip/uv, Deno provider, CA — успешно |
| Runtime dependency smoke, Windows и Linux | Реальные loopback HTTP запросы httpx/AnyIO, параллельные запросы, curl impersonation, cffi/pycparser, IDNA, dotenv parsing/precedence — успешно |
| Реальная нарезка в финальном production | 8 секунд → 4 части, каждая ≤250762 байт, audio/video сохранены, cleanup успешен |
| Trivy финального образа | Сканирование выполнено; Python 0 findings, OS findings остаются (см. выше) |
| Независимое read-only ревью diff | Регрессий и обязательных исправлений не найдено |

Во всех полных pytest-запусках остаются 3 одинаковых DeprecationWarning из
python-telegram-bot об `asyncio.iscoroutinefunction`; они присутствовали в baseline.
Первый локальный запуск без ffmpeg в PATH дал 228 passed / 6 skipped; после
добавления существующего ffmpeg **только в PATH процесса** выполнен полный baseline.
Проверка отсутствия pip до исправления ожидаемо упала; финальный smoke прошёл.

Docker Scout 1.27.0 завершился с кодом 1: требуется Docker login, отчёт не создан.
Вход и смена глобальных настроек не выполнялись. Вместо него применён официальный
[Trivy 0.76.1](https://github.com/aquasecurity/trivy/releases/tag/v0.76.1), скачанный
в каталог задачи с проверкой опубликованного SHA-256:
`1051f49cb22d5284f43425f72aad9cda63ca12ceb92e7caa06903490c82dc9bf`.
Trivy сканировал локальный `docker save` архив, без доступа к Docker socket.
Его exit code 0 означает завершение сканирования, а не отсутствие CVE.

Живые скачивания YouTube/Instagram, отправка Telegram, Python 3.15 и другие
архитектуры не проверялись. Версия загрузчика и его конфигурация не менялись;
проверки не требуют пользовательских cookies или токена.

## Воспроизведение и артефакты

Из worktree, используя uv 0.13.6 и Python 3.14 (для полного локального pytest
в PATH должны быть ffmpeg и ffprobe):

```sh
uv sync --locked --extra dev --python 3.14
uv lock --check --offline
uv pip check
uv run --locked pytest tests/ -v --cov=bot --cov=config --cov=media --cov=platforms
uv export --locked --extra dev --no-emit-project -o ../evidence/requirements.txt
uv tool run pip-audit==2.10.1 -r ../evidence/requirements.txt --no-deps --disable-pip
docker build --pull --target production -t tgdlbot:deps-2026-11-02-production .
docker build --target test -t tgdlbot:deps-2026-11-02-test .
docker build --check .
docker compose --env-file .env.example config --no-env-resolution --quiet
docker run --rm --network none tgdlbot:deps-2026-11-02-test
```

Чтобы прогнать все тесты с production ffmpeg, использован отдельный
`../tooling/Dockerfile.verify` (основной test target не менялся):

```dockerfile
FROM tgdlbot:deps-2026-11-02-production
COPY --from=tgdlbot:deps-2026-11-02-test /app/.venv /app/.venv
COPY --from=tgdlbot:deps-2026-11-02-test /app/tests /app/tests
COPY --from=tgdlbot:deps-2026-11-02-test /app/pyproject.toml /app/pyproject.toml
CMD ["python", "-m", "pytest", "tests/", "-v", "-p", "no:cacheprovider"]
```

Из родительского каталога задачи:

```sh
docker build -f tooling/Dockerfile.verify -t tgdlbot:deps-2026-11-02-verify tooling
docker run --rm --network none tgdlbot:deps-2026-11-02-verify
docker save -o evidence/tgdlbot-production-final.tar tgdlbot:deps-2026-11-02-production
tooling/trivy/trivy.exe image --input evidence/tgdlbot-production-final.tar --cache-dir tooling/trivy-cache --scanners vuln --format json --output evidence/trivy-production-final.json --timeout 8m --no-progress
```

Проверенный production digest:
`sha256:756048d492b5f895aa5209adcc86af5d0e3d05e60f099dd9f1c10ebce783ba2f`.
Образы production/test/verify сохранены локально с тегами `deps-2026-11-02-*`.
Контейнеры запускались одноразово, без пользовательских mounts.

Логи и JSON/XML находятся в
`C:\Users\amerb\Documents\Codex\2026-11-02\task\evidence`:
`baseline-full.log`, `updated-tests.log`, `coverage.xml`, `updated-audit.json`,
`pypi-releases.json`, `lock-validation.json`, `docker-final-tests.log`,
`production-final-smoke.log`, `media-final-smoke.log`,
`trivy-production-final.json`, `trivy-summary.json`.
Вспомогательные проверочные скрипты находятся рядом, в `tooling`.
Изменения доступны для построчного ревью через сравнение ветки с `master`.
