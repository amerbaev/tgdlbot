# Проверка builder и runtime — 16 ноября 2026

Задача обновления: [#4](https://github.com/amerbaev/tgdlbot/issues/4).
Остаточные security findings: [#6](https://github.com/amerbaev/tgdlbot/issues/6).
База: `ec5f7efab390195183bc91d1aa53732300bdfacd`, актуальный master с PR #2.
Ветка `chore/uv-2026-11-16` независима от
[PR #5](https://github.com/amerbaev/tgdlbot/pull/5) с dev-зависимостями.

## Изменение

Docker builder: **uv 0.13.7 → 0.13.8**; единственное изменение исполняемой
конфигурации — tag в `COPY --from`. [Официальный релиз 12 ноября](https://github.com/astral-sh/uv/releases/tag/0.13.8)
исправляет права Unix credential-файлов и разрешение constraints/extras.
Релиз также обновляет managed Python builds, но проект сохраняет
`UV_PYTHON_DOWNLOADS=0` и использует Python из официального базового образа.
Lockfile, manifest, runtime-зависимости, приложение и тесты этой ветки
идентичны master. uv остаётся только в builder и не попадает в production.

## Подтверждённые версии

| Компонент | Версия |
|---|---|
| Python | 3.14.10 |
| Debian | 13.7 / trixie |
| uv builder | 0.13.8 |
| ffmpeg | 7:7.1.5-0+deb13u1 |
| zlib1g | 1:1.3.dfsg+really1.3.1-1+deb13u1 |
| openssl | 3.5.7-1~deb13u3 |
| ca-certificates | 20250419+deb13u1 |
| libxml2 | 2.12.7+dfsg+really2.9.14-2.1+deb13u3 |
| libdbus-1-3 | 1.16.2-2 |
| libexpat1 | 2.9.0-1~deb13u1 |
| python-telegram-bot | 22.8 |
| yt-dlp / yt-dlp-ejs / Deno | 2026.10.26 / 0.8.0 / 2.9.8 |
| curl-cffi / certifi / python-dotenv | 0.17.0 / 2026.10.23 / 1.2.4 |

Python 3.14.10 остаётся последним patch-релизом ветки 3.14 по
[python.org](https://www.python.org/downloads/). Доступность 3.15.2
не является основанием менять minor-ветку в этом совместимом обновлении.
Все 25 сторонних Python-пакетов проверены по PyPI; обновления нужны только
coverage и pytest-asyncio, подготовленным отдельно в PR #5.

Образы проверены с `--pull`:

- `python:3.14-slim`: `sha256:9aaa474097d094040649f2162a627c0049b408f52138d980916788d80f04802f`.
- `ghcr.io/astral-sh/uv:0.13.8`: `sha256:5cc1805e2426484abca4ad46ea783bab281fdb225fd82d8ce6d66a81254bac85`.
- Собранный production: `sha256:abf4c62897ff02f4a43e25de1f5d03e3c99751201468e3d0fd84250307243dae`.
- Контрольный свежий master production: `sha256:88ded1655502211b4ab9367b81418d843f16ea772b92ab36cbd2e524cc998375`.

## Security audit

**Python:** pip-audit 2.10.1, все 25 пакетов lockfile, включая dev и
Windows-only colorama: **0 известных уязвимостей**. Trivy проверил
15 установленных runtime Python-пакетов: **0 findings**.

**OS:** Trivy 0.76.2, свежая DB `2026-11-16T07:10:39Z`.
Бинарник из официального GitHub release проверен по опубликованному SHA-256
`bc0fc726e017b8927a62b2d3531d7a84ee01769daf5c99ed866dced54089fdbf`.
Сканировались локальные `docker save` архивы, без ignore-правил.

| Срез | Свежий master | uv 0.13.8 |
|---|---:|---:|
| OS packages | 292 | 292 |
| Package–advisory matches | 1556 | 1556 |
| Unique advisory IDs | 386 | 386 |
| Findings с FixedVersion | 0 | 0 |
| Runtime Python packages / findings | 15 / 0 | 15 / 0 |

Сравнение подтвердило полное равенство 307 package/version entries и
1556 кортежей package/version/advisory/fix/severity между двумя образами.
Обновление uv не добавляет runtime findings. В обоих образах остаются
**1 critical, 344 high, 439 medium, 203 low, 569 unknown** совпадений.
Нулевой exit code сканера означает успешное сканирование, не чистый аудит.
`apt-get update && apt-get -s upgrade`: **0 обновлений**.

Прошлый отчёт содержал 806 matches / 282 ID. Исторический полный per-ID
snapshot в восстановленной среде отсутствует, поэтому разность счётчиков
не объявляется количеством новых уязвимостей. В свежих данных у 97 ID
PublishedDate позже публикации PR #2: 72 относятся к source package FFmpeg,
11 — krb5, 5 — OpenSSL, 3 — D-Bus, 2 — glibc, по 1 — dpkg, gcc/libstdc++,
Expat и libva. Severity: 17 high, 14 medium, 1 low, 65 unknown.
Пакетное совпадение не доказывает достижимость через приложение.

Официальный Debian Security Tracker подтверждает свежие примеры:

- [CVE-2026-125262](https://security-tracker.debian.org/tracker/CVE-2026-125262), FFmpeg LCEVC, high: trixie vulnerable/postponed, фикс 7.1.x ещё не доступен. Отдельный LCEVC decoder отсутствует в списке установленной сборки; это не доказательство отсутствия всей уязвимой логики.
- [CVE-2026-125264](https://security-tracker.debian.org/tracker/CVE-2026-125264), FFmpeg JPEG XL parser: trixie vulnerable/postponed; libjxl decoder присутствует.
- [CVE-2026-95691](https://security-tracker.debian.org/tracker/CVE-2026-95691), OpenSSL QUIC: security-пакет 3.5.7-1~deb13u3 affected, FixedVersion отсутствует.
- [CVE-2026-128987](https://security-tracker.debian.org/tracker/CVE-2026-128987), D-Bus: trixie vulnerable/no-dsa; sid содержит исправление 1.16.4-1. Бот не запускает D-Bus service; достижимость не установлена.

Ранее известные [CVE-2026-120210](https://security-tracker.debian.org/tracker/CVE-2026-120210),
[CVE-2026-107697](https://security-tracker.debian.org/tracker/CVE-2026-107697)
и [CVE-2026-6653](https://security-tracker.debian.org/tracker/CVE-2026-6653)
перепроверены: для trixie исправлений по-прежнему нет. Они не считаются новыми.
zlib сохраняет security-обновление PR #2. Остаточные findings и дальнейшая
проверка достижимости вынесены в #6; менять дистрибутив или major FFmpeg
в этом PR не предлагается.

## Проверки

| Проверка | Результат |
|---|---|
| Production / test builds с uv 0.13.8 | Успешно |
| Контрольная свежая production-сборка master с uv 0.13.7 | Успешно |
| Dockerfile build check | Успешно, предупреждений нет |
| Compose structure check с `.env.example` | Успешно |
| Штатный Docker test target, без сети | 228 passed, 11 skipped: нет FFmpeg в test target |
| Production + dev-venv из test target этой ветки, UID 1000, без сети | 239 passed, 17 subtests passed, exit 0 |
| Production + dev-venv из PR #5, UID 1000, без сети | 239 passed, 17 subtests passed, exit 0 |
| Production smoke, UID 1000, без сети | Импорты, Deno provider, ffmpeg/ffprobe, запись downloads; нет pip/ensurepip/uv/pytest и Telegram token |
| APT update + simulated upgrade | 0 доступных обновлений |
| Свежий Trivy master / изменённый production | Одинаковые findings; Python 0, OS 1556 без fixes |

Полные прогоны включают 11 тестов с реальным FFmpeg, в том числе сохранение
кадров и дробные границы нарезки из PR #1. Дополнительные verify-образы
содержат dev-venv и тесты; они не являются production и не публиковались.
Три DeprecationWarning python-telegram-bot и предупреждение pytest-asyncio
о неявном fixture scope остаются.

Облачные сборки используют временные Dockerfile с CA bundle как BuildKit
secret только при uv sync. TLS-проверка включена; CA не сохраняется в слоях.
Прямой GitHub API из shell недоступен (proxy 403): чтение GitHub и публикация
PR выполняются через подключённый GitHub tool. Зеркало Trivy `mirror.gcr.io`
недоступно; DB получена из официального `ghcr.io/aquasecurity/trivy-db:2`.
Эти ограничения удалось обойти штатными поддерживаемыми источниками.

Не выполнялись Telegram/video-service calls, миграция Python 3.15,
проверки Windows/ARM, merge, auto-merge или deploy.
Логи и JSON-доказательства сохранены в
`/workspace/dependency-audit-2026-11-16/evidence`:
`builder-production-build.log`, `builder-test-build.log`, `builder-test.log`,
`builder-full-tests.log`, `combined-full-tests.log`, `production-smoke.log`,
`production-packages.txt`, `apt-upgradable.log`, `trivy-production.json`,
`trivy-master-production.json`, `trivy-comparison.json`, `trivy-summary.json`.
Временные Dockerfile и smoke script находятся в соседнем `tooling`.
