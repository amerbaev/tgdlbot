# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Telegram bot for downloading YouTube videos in best quality (1080p → 720p → 480p → 360p), automatically splitting files larger than 50MB into parts. Uses yt-dlp with mediaconnect client for high-quality downloads and ffmpeg for video splitting.

## Development Commands

```bash
# Install dependencies
uv sync --extra dev

# Run bot locally
uv run python bot.py
make dev

# Run tests
uv run pytest tests/ -v
uv run pytest tests/ -v -k test_name  # Single test
make test

# Docker
make build      # Build production image
make up         # Start bot
make logs       # View logs
make down       # Stop services

# Cleanup
make clean      # Remove temporary files
```

## Architecture

### Async Threading Model
- Bot uses `asyncio` for Telegram handlers (non-blocking)
- Blocking operations (yt-dlp, ffmpeg) run in threads via `asyncio.to_thread()`
- Up to 3 concurrent downloads via implicit thread pool
- Background tasks stored in `background_tasks` set to prevent garbage collection

### Download Flow
1. User sends YouTube URL → `handle_message()` validates and creates `DownloadTask`
2. `asyncio.create_task(process_download())` starts background processing
3. `download_video_sync()` tries formats from `FORMAT_CANDIDATES` (1080p → 720p → 480p → 360p)
   - Uses mediaconnect client for 1080p/720p to bypass 403 errors
   - Generates unique `download_id` (8-char UUID) to prevent race conditions
   - Finds downloaded file by prefix + newest mtime
4. If file > 50MB: `split_video()` divides into parts with retry mechanism
   - Target size = 45MB (90% of limit)
   - On oversize: retry with 80% duration (max 2 attempts)
   - Validates each part ≤ 50MB before adding to list
5. `cleanup_download(user_id, video_path)` removes from `active_downloads` and deletes files

### Smart Format Selection
- `estimate_format_size()`: Checks `filesize` in metadata for target height
- `should_skip_format()`: Skips 1080p/720p if estimated > 75MB (50MB × 1.5)
- `select_best_format()`: Returns list of (format_selector, extractor_args) tuples
- Falls through formats until one succeeds

### Key Components
- `active_downloads: dict[int, dict]` - Tracks per-user download state (prevents duplicates)
- `DownloadTask` dataclass - Carries user_id, chat_id, url, status_message, video_path
- `format_size()` - Utility for MB conversion
- `cleanup_download()` - Centralized resource cleanup

### Dependencies
- `python-telegram-bot` - Telegram Bot API wrapper (async)
- `yt-dlp` - YouTube downloader with mediaconnect support
- `ffmpeg` (system) - Video splitting (installed in Docker, not bundled)

### Configuration
- `BOT_TOKEN` - From .env file (TELEGRAM_BOT_TOKEN)
- `MAX_FILE_SIZE = 50 * 1024 * 1024` - Telegram bot API limit
- `DOWNLOAD_DIR = 'downloads'` - Temporary file location (gitignored)

### Testing
- 24 tests cover URL validation, format selection, download, splitting, commands
- Mock-heavy due to external dependencies (yt-dlp, Telegram, subprocess)
- Run with `pytest` - uses asyncio auto mode
