# User Whitelist Feature Design

**Date:** 2026-04-27
**Status:** Approved

## Overview

Add user whitelist functionality to restrict bot access to authorized users only. Bot will silently ignore messages from non-whitelisted users.

## Requirements

- Bot must only respond to whitelisted users
- Whitelist configured via text file in project root
- Bot must fail to start if whitelist is missing or empty
- Non-whitelisted users are silently ignored (no response)

## Architecture

### New Module: `auth.py`

Handles whitelist loading and user verification:

- `load_whitelist() → set[int]`: Load and parse whitelist file
- `is_user_allowed(user_id: int) → bool`: Check if user has access

### Integration Points

**In `bot.py`:**
- Import `is_user_allowed` from `auth.py`
- Add check at start of `handle_message()` before processing
- Add check at start of `download_command()` before processing
- Call `load_whitelist()` in `main()` before starting bot

### Data Flow

1. Bot startup → Load `whitelist.txt` → Validate IDs
2. User sends URL → Check `is_user_allowed(user_id)`
3. If allowed → Normal processing flow
4. If not allowed → Silent return (no response)
5. If whitelist invalid → Critical error, exit

## Components

### `auth.py` Module

```python
def load_whitelist(filepath: str = "whitelist.txt") -> set[int]:
    """Load user IDs from whitelist file.

    Raises:
        FileNotFoundError: If whitelist file missing
        ValueError: If no valid user IDs found

    Returns:
        Set of allowed user IDs
    """

def is_user_allowed(user_id: int, whitelist: set[int]) -> bool:
    """Check if user is allowed to use bot.

    Args:
        user_id: Telegram user ID
        whitelist: Set of allowed user IDs

    Returns:
        True if user allowed, False otherwise
    """
```

### `whitelist.txt` Format

Located in project root. Format:
```
# Admin users
123456789
987654321

# Friends
111222333
```

Rules:
- `#` starts comment (until end of line)
- One user ID per line
- Blank lines ignored
- Leading/trailing whitespace trimmed
- Invalid format → warning logged, line skipped

### `bot.py` Changes

**In `main()`:**
```python
# Load whitelist before starting bot
whitelist = load_whitelist()
logger.info(f'Loaded {len(whitelist)} whitelisted users')
```

**In `handle_message()`:**
```python
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    # Check whitelist
    if not is_user_allowed(user_id, whitelist):
        return  # Silent ignore

    # Rest of function...
```

**In `download_command()`:**
```python
async def download_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    # Check whitelist
    if not is_user_allowed(user_id, whitelist):
        return  # Silent ignore

    # Rest of function...
```

**Global variable:**
```python
# Global whitelist loaded at startup
whitelist: set[int] = set()
```

## Error Handling

### Startup Failures

Bot will fail to start and exit with error if:

| Condition | Error Message | Action |
|-----------|---------------|--------|
| File missing | `ERROR: whitelist.txt not found. Create it with allowed user IDs.` | Exit |
| File empty | `ERROR: whitelist.txt is empty. Add at least one user ID.` | Exit |
| No valid IDs | `ERROR: No valid user IDs found in whitelist.txt` | Exit |

### Runtime Errors

| Condition | Action |
|-----------|--------|
| Invalid line format | Log warning, skip line |
| Duplicate IDs | Use set (automatically deduplicated) |
| File exists but unreadable | Log error, exit |

## Testing

### Unit Tests (`tests/test_auth.py`)

- `test_load_valid_whitelist`: Load file with valid IDs
- `test_load_with_comments`: Parse file with comments correctly
- `test_load_with_blank_lines`: Ignore blank lines
- `test_load_invalid_ids`: Skip invalid IDs, log warning
- `test_empty_file_raises_error`: Empty file → ValueError
- `test_missing_file_raises_error`: Missing file → FileNotFoundError
- `test_is_user_allowed_true`: Whitelisted user returns True
- `test_is_user_allowed_false`: Non-whitelisted user returns False

### Integration Tests

- `test_non_whitelisted_user_ignored`: Message from non-whitelisted user → no response
- `test_whitelisted_user_allowed`: Whitelisted user → normal processing

## Implementation Order

1. Create `auth.py` with `load_whitelist()` and `is_user_allowed()`
2. Add whitelist check in `handle_message()` and `download_command()`
3. Update `main()` to load whitelist before starting bot
4. Create `tests/test_auth.py` with unit tests
5. Create `whitelist.txt.example` with documentation
6. Update README with whitelist setup instructions

## Files to Create

- `auth.py` - Whitelist loading and verification logic
- `tests/test_auth.py` - Unit tests for auth module
- `whitelist.txt.example` - Example whitelist file

## Files to Modify

- `bot.py` - Add whitelist checks and loading
- `README.md` - Add whitelist setup documentation

## Backward Compatibility

Breaking change: Bot will not start without whitelist file. Migration:
1. Create `whitelist.txt` with desired user IDs
2. Restart bot
