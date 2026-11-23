# Download Flow Readability Refactor

> **For agentic workers:** Execute inline with `superpowers:executing-plans` and review the complete branch before opening one PR.

**Goal:** Remove redundant download state, forwarding, and cleanup while preserving observable behavior.

**Architecture:** Keep Telegram orchestration in `bot.py`, media operations in `media.py`, and format selection in `platforms/youtube.py`. The large-video sender owns its parts from creation through upload and cleanup. Keep thread cancellation explicit: file cleanup must wait for each writer to exit.

**Tech Stack:** Python 3.14, asyncio, python-telegram-bot, yt-dlp, pytest, FFmpeg.

**Spec:** User request: readable code, behavior preserved, separate refactor branch, one PR for review, no merge or deployment. README and dependency updates are separate tasks.

## Global Constraints

- Preserve URL validation, admission, cancellation, messages, upload options, quality order, and limits.
- Preserve the `(selector, extractor_args)` platform interface and yt-dlp default clients.
- Keep dependencies, README, deployment, and CI configuration unchanged.
- Use characterization tests before refactoring existing behavior; do not invent a behavior change just to obtain a failing test.

## Review Focus

- A file exactly at the upload limit is sent whole; one byte above is split.
- Split cancellation waits for the writer before deleting its outputs.
- Upload or status failure removes every part and releases the user's slot.
- Preview generation finishes before cancellation can remove its source.
- Portrait fallback keeps separate video/audio selection and the format 18 fallback.

## Task 1: Simplify delivery and ownership

**Files:** `bot.py`, `tests/test_bot.py`, `tests/test_download_lifecycle.py`, `tests/test_video_preview.py`, `tests/test_video_dimensions.py`, `tests/test_instagram_download.py`, `AGENTS.md`, `CLAUDE.md`.

- [x] Add boundary-level characterization for whole/split uploads, split failure, upload failure, and cancellation after splitting; run against unchanged code.
- [x] Remove unused `DownloadTask` fields and use keyword arguments at construction sites.
- [x] Put part upload and cleanup in `_send_large_video`; remove the extra part-sender helper and success-forwarding wrapper.
- [x] Adapt existing preview/cancellation tests to call the owning sender, retaining their filesystem and Telegram assertions.
- [x] Run focused lifecycle, bot, and preview tests.

## Task 2: Make YouTube format selection direct

**Files:** `platforms/youtube.py`, `tests/platforms/test_youtube_shorts.py`, `AGENTS.md`.

- [x] Add real yt-dlp selection cases at the high-quality size threshold and for portrait progressive fallback; run before the refactor.
- [x] Remove unused format candidate entries and extract the repeated video-plus-audio selector construction.
- [x] Run platform and downloader runtime tests, then the full suite.

## Final verification

- [x] Review the full diff for behavior changes and accidental scope expansion.
- [x] Run `uv run --no-sync pytest tests/ -q` and `git diff --check`.
- [ ] Commit, push only the refactor branch, open one PR, and inspect its checks.

## Verification record

- Baseline at `c81b85c`: 239 tests and 17 subtests passed.
- New characterization cases passed before implementation.
- Final local suite: 244 tests and 17 subtests passed, including real FFmpeg tests.
- Independent review compared all selector outputs for 32 input combinations with the base revision; all matched.
- Full-suite failures exposed five stale test callers after helper/field removal; all callers were migrated and the full suite rerun successfully.
- Review observation: status-edit failure is tested at the part-owner boundary; slot release is covered separately through the complete process on upload failure.
