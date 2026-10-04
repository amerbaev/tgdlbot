# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Telegram bot for downloading YouTube and Instagram videos in best quality (1080p → 720p → 480p → 360p), automatically splitting files larger than 50MB into parts. Uses yt-dlp with mediaconnect client for high-quality downloads and ffmpeg for video splitting.

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
- Admission is limited to 3 active jobs; the user slot is reserved before awaiting Telegram
- Background tasks are retained in `background_tasks` and awaited by the application post-stop hook

### Download Flow
1. User sends YouTube URL → `handle_message()` validates and creates `DownloadTask`
2. `asyncio.create_task(process_download())` starts background processing
3. `download_video_sync()` tries formats from `FORMAT_CANDIDATES` (1080p → 720p → 480p → 360p)
   - Uses mediaconnect client for 1080p/720p to bypass 403 errors
   - Uses the same full UUID for admission, cancellation, download filenames, and cleanup
   - Reads the successful extraction result without fetching metadata again
   - Restricts input to individual supported video URLs; rejects live streams and playlists
4. If file > 50MB: `media.split_video()` divides into parts with retry mechanism
   - Target size = 45MB (90% of limit)
   - On oversize: retry with 80% duration (max 2 attempts)
   - Validates each part ≤ 50MB before adding to list
   - Advances by the accepted duration after a retry so no interval is skipped
   - Bounds ffprobe/ffmpeg execution and cleans partial outputs on failure
5. `cleanup_download()` releases the user slot and deletes only that job's files, including partial attempts

### Smart Format Selection
- `estimate_format_size()`: Checks `filesize` in metadata for target height
- `select_best_format()`: Skips 1080p/720p if estimated size is unknown or > 75MB (50MB × 1.5)
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
- `MAX_FILE_SIZE = 50 * 1024 * 1024` - Telegram upload limit per part
- `MAX_DOWNLOAD_SIZE = 500 * 1024 * 1024` - source file limit
- `MAX_CONCURRENT_DOWNLOADS = 3` - active job limit
- `DOWNLOAD_DIR = 'downloads'` - Temporary file location (gitignored)

### Testing
- Tests cover URL validation, format selection, cancellation, cleanup, splitting, commands, and network recovery
- External services are replaced at their boundaries; tests run offline and use isolated temporary files
- Run with `pytest` - uses asyncio auto mode
