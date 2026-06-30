# Local Bot API with 2GB Limit - Design Spec

**Date:** 2026-06-30
**Status:** Approved

## Overview

Add local Telegram Bot API server to enable 2GB file uploads instead of 50MB limit.

## Requirements

- **Size limit:** 2GB (2000 MB)
- **Mode:** Local Bot API (`--local` flag)
- **Connection:** Local-only (no fallback)
- **Files > 2GB:** Split into 1.8GB parts
- **Image:** `aiogram/telegram-bot-api:latest`

## Architecture

```
┌─────────────────┐     ┌──────────────────────┐
│   tgdlbot       │────▶│  telegram-bot-api    │
│  (your bot)     │     │  (local server)      │
└─────────────────┘     └──────────────────────┘
                              │
                              ▼
                      (Telegram cloud)
```

Two containers on `bot-network`:
1. `telegram-bot-api` - Local Bot API server
2. `tgdlbot` - Application bot

## Changes

### 1. docker-compose.yml

Add `telegram-bot-api` service:

```yaml
services:
  telegram-bot-api:
    image: aiogram/telegram-bot-api:latest
    container_name: telegram-bot-api
    restart: unless-stopped
    command: ["--local"]
    environment:
      - TELEGRAM_API_ID=${TELEGRAM_API_ID}
      - TELEGRAM_API_HASH=${TELEGRAM_API_HASH}
    volumes:
      - ./telegram-data:/var/lib/telegram-bot-api
    networks:
      - bot-network

  tgdlbot:
    # ... existing config ...
    environment:
      - BOT_API_URL=http://telegram-bot-api:8081/bot
    depends_on:
      - telegram-bot-api
    networks:
      - bot-network

networks:
  bot-network:
```

### 2. config.py

```python
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2GB
```

### 3. bot.py

Constants:
```python
TARGET_SIZE_MB = 1800  # 90% of 2GB
```

Application builder:
```python
base_url = os.getenv('BOT_API_URL', 'https://api.telegram.org/bot')
application = Application.builder().token(BOT_TOKEN).base_url(base_url).request(request).build()
```

Update /start and /help messages: 50MB → 2GB.

### 4. .env

Add:
```
TELEGRAM_API_ID=<your_id>
TELEGRAM_API_HASH=<your_hash>
```

Get credentials from: https://my.telegram.org

## Error Handling

- telegram-bot-api down: bot fails to start (depends_on)
- Missing API_ID/HASH: compose error with clear message
- File > 2GB: split_video() creates 1.8GB parts (existing logic)

## Testing

1. Start: `docker-compose up`
2. Send YouTube link
3. Verify:
   - Files ≤ 2GB sent whole
   - Files > 2GB split into parts
4. Check logs for errors

## Implementation Order

1. Add credentials to .env
2. Update docker-compose.yml
3. Update config.py
4. Update bot.py (constants + base_url + messages)
5. Test locally
6. Deploy

## Notes

- `aiogram/telegram-bot-api` is unofficial but widely used
- `--local` flag is critical for 2GB support
- Data stored in `./telegram-data` directory