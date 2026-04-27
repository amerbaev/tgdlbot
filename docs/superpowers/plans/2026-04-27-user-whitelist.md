# User Whitelist Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add user whitelist functionality to restrict bot access to authorized users only

**Architecture:** New `auth.py` module loads whitelist from file on startup, `bot.py` checks user access before processing messages

**Tech Stack:** Python, pytest, python-telegram-bot, python-dotenv

---

## File Structure

**New files:**
- `auth.py` - Whitelist loading and verification logic
- `tests/test_auth.py` - Unit tests for auth module
- `whitelist.txt.example` - Example whitelist file with documentation

**Modified files:**
- `bot.py` - Add whitelist loading on startup, check access in message handlers

---

## Task 1: Create auth.py module with load_whitelist()

**Files:**
- Create: `auth.py`

- [ ] **Step 1: Write failing test for load_whitelist()**

```python
# tests/test_auth.py
import pytest
from auth import load_whitelist

def test_load_valid_whitelist(tmp_path):
    """Load whitelist with valid user IDs."""
    whitelist_file = tmp_path / "whitelist.txt"
    whitelist_file.write_text("123456789\n987654321\n")
    result = load_whitelist(str(whitelist_file))
    assert result == {123456789, 987654321}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_auth.py::test_load_valid_whitelist -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'auth'"

- [ ] **Step 3: Create auth.py with minimal load_whitelist()**

```python
# auth.py
def load_whitelist(filepath: str = "whitelist.txt") -> set[int]:
    """Load user IDs from whitelist file.

    Args:
        filepath: Path to whitelist file

    Returns:
        Set of allowed user IDs

    Raises:
        FileNotFoundError: If whitelist file missing
        ValueError: If no valid user IDs found
    """
    user_ids = set()

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()

                # Skip empty lines and comments
                if not line or line.startswith('#'):
                    continue

                # Parse user ID
                try:
                    user_id = int(line)
                    user_ids.add(user_id)
                except ValueError:
                    import logging
                    logging.warning(f'Invalid user ID in whitelist: {line}')

    except FileNotFoundError:
        raise FileNotFoundError(f'whitelist.txt not found. Create it with allowed user IDs.')

    if not user_ids:
        raise ValueError('No valid user IDs found in whitelist.txt')

    return user_ids
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_auth.py::test_load_valid_whitelist -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add auth.py tests/test_auth.py
git commit -m "feat: add load_whitelist() function"
```

---

## Task 2: Add whitelist parsing features (comments, blank lines)

**Files:**
- Modify: `tests/test_auth.py`
- Test: `tests/test_auth.py`

- [ ] **Step 1: Write test for comments and blank lines**

```python
# tests/test_auth.py
def test_load_with_comments(tmp_path):
    """Parse file with comments correctly."""
    whitelist_file = tmp_path / "whitelist.txt"
    whitelist_file.write_text(
        "# Admin users\n"
        "123456789\n"
        "\n"
        "# Friends\n"
        "987654321\n"
    )
    result = load_whitelist(str(whitelist_file))
    assert result == {123456789, 987654321}
```

- [ ] **Step 2: Run test to verify it passes**

Run: `uv run pytest tests/test_auth.py::test_load_with_comments -v`
Expected: PASS (already implemented in Task 1)

- [ ] **Step 3: Commit**

```bash
git add tests/test_auth.py
git commit -m "test: add whitelist comment parsing test"
```

---

## Task 3: Handle invalid IDs gracefully

**Files:**
- Modify: `tests/test_auth.py`
- Test: `tests/test_auth.py`

- [ ] **Step 1: Write test for invalid IDs**

```python
# tests/test_auth.py
def test_load_invalid_ids(tmp_path, caplog):
    """Skip invalid IDs, log warning."""
    whitelist_file = tmp_path / "whitelist.txt"
    whitelist_file.write_text(
        "123456789\n"
        "invalid_id\n"
        "987654321\n"
    )
    result = load_whitelist(str(whitelist_file))
    assert result == {123456789, 987654321}
    assert "Invalid user ID in whitelist: invalid_id" in caplog.text
```

- [ ] **Step 2: Run test to verify it passes**

Run: `uv run pytest tests/test_auth.py::test_load_invalid_ids -v`
Expected: PASS (already implemented in Task 1)

- [ ] **Step 3: Commit**

```bash
git add tests/test_auth.py
git commit -m "test: add invalid ID handling test"
```

---

## Task 4: Error handling for empty file

**Files:**
- Modify: `tests/test_auth.py`
- Test: `tests/test_auth.py`

- [ ] **Step 1: Write test for empty file**

```python
# tests/test_auth.py
def test_empty_file_raises_error(tmp_path):
    """Empty file raises ValueError."""
    whitelist_file = tmp_path / "whitelist.txt"
    whitelist_file.write_text("")
    with pytest.raises(ValueError, match="No valid user IDs found"):
        load_whitelist(str(whitelist_file))
```

- [ ] **Step 2: Run test to verify it passes**

Run: `uv run pytest tests/test_auth.py::test_empty_file_raises_error -v`
Expected: PASS (already implemented in Task 1)

- [ ] **Step 3: Commit**

```bash
git add tests/test_auth.py
git commit -m "test: add empty file error test"
```

---

## Task 5: Error handling for missing file

**Files:**
- Modify: `tests/test_auth.py`
- Test: `tests/test_auth.py`

- [ ] **Step 1: Write test for missing file**

```python
# tests/test_auth.py
def test_missing_file_raises_error(tmp_path):
    """Missing file raises FileNotFoundError."""
    whitelist_file = tmp_path / "nonexistent.txt"
    with pytest.raises(FileNotFoundError, match="whitelist.txt not found"):
        load_whitelist(str(whitelist_file))
```

- [ ] **Step 2: Run test to verify it passes**

Run: `uv run pytest tests/test_auth.py::test_missing_file_raises_error -v`
Expected: PASS (already implemented in Task 1)

- [ ] **Step 3: Commit**

```bash
git add tests/test_auth.py
git commit -m "test: add missing file error test"
```

---

## Task 6: Add is_user_allowed() function

**Files:**
- Modify: `auth.py`
- Test: `tests/test_auth.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_auth.py
from auth import is_user_allowed

def test_is_user_allowed_true():
    """Whitelisted user returns True."""
    whitelist = {123456789, 987654321}
    assert is_user_allowed(123456789, whitelist) is True

def test_is_user_allowed_false():
    """Non-whitelisted user returns False."""
    whitelist = {123456789, 987654321}
    assert is_user_allowed(111222333, whitelist) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_auth.py::test_is_user_allowed_true -v`
Expected: FAIL with "cannot import 'is_user_allowed' from 'auth'"

- [ ] **Step 3: Add is_user_allowed() to auth.py**

```python
# auth.py - add after load_whitelist()

def is_user_allowed(user_id: int, whitelist: set[int]) -> bool:
    """Check if user is allowed to use bot.

    Args:
        user_id: Telegram user ID
        whitelist: Set of allowed user IDs

    Returns:
        True if user allowed, False otherwise
    """
    return user_id in whitelist
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_auth.py -k "is_user_allowed" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add auth.py tests/test_auth.py
git commit -m "feat: add is_user_allowed() function"
```

---

## Task 7: Integrate whitelist loading in bot.py

**Files:**
- Modify: `bot.py`
- Modify: `bot.py`

- [ ] **Step 1: Add import and global variable**

```python
# bot.py - add after existing imports
from auth import load_whitelist, is_user_allowed

# After global variables section (line 56)
whitelist: set[int] = set()
```

- [ ] **Step 2: Load whitelist in main() before starting bot**

```python
# bot.py - in main() function, after logger setup (around line 980)
def main() -> None:
    """Запуск бота."""
    if not BOT_TOKEN:
        raise ValueError(
            'TELEGRAM_BOT_TOKEN не найден в переменных окружения. '
            'Создайте .env файл с токеном бота.'
        )

    # Load whitelist
    try:
        whitelist = load_whitelist()
        logger.info(f'Loaded {len(whitelist)} whitelisted users')
    except (FileNotFoundError, ValueError) as e:
        logger.error(f'Failed to load whitelist: {e}')
        raise

    logger.info('Запуск бота...')
    logger.info('Макс. одновременных скачиваний: 3')
```

- [ ] **Step 3: Create example whitelist file**

```bash
# whitelist.txt.example
# Admin users
123456789
987654321

# Add your Telegram user ID here
# Get your ID by messaging @userinfobot on Telegram
```

- [ ] **Step 4: Run bot to verify startup fails without whitelist**

Run: `uv run python bot.py`
Expected: ERROR with "whitelist.txt not found"

- [ ] **Step 5: Create actual whitelist file and verify startup**

```bash
# Replace 123456789 with your actual Telegram user ID
echo "123456789" > whitelist.txt
```

Run: `uv run python bot.py`
Expected: Bot starts, log shows "Loaded 1 whitelisted users"

- [ ] **Step 6: Commit**

```bash
git add bot.py whitelist.txt.example
git commit -m "feat: integrate whitelist loading on bot startup"
```

---

## Task 8: Add whitelist check to handle_message()

**Files:**
- Modify: `bot.py`

- [ ] **Step 1: Add whitelist check at start of handle_message()**

```python
# bot.py - in handle_message() function, after getting user_id (around line 884)
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик текстовых сообщений (ссылки на YouTube/Instagram)."""
    url = update.message.text.strip()
    user_id = update.effective_user.id
    chat_type = update.message.chat.type

    # Check whitelist
    if not is_user_allowed(user_id, whitelist):
        logger.info(f'[User {user_id}] Access denied: not in whitelist')
        return  # Silent ignore

    # Rest of function continues...
```

- [ ] **Step 2: Run bot and test with non-whitelisted user**

Send message from non-whitelisted account
Expected: No response (silent ignore)

- [ ] **Step 3: Run bot and test with whitelisted user**

Send message from whitelisted account
Expected: Normal bot response

- [ ] **Step 4: Commit**

```bash
git add bot.py
git commit -m "feat: add whitelist check to handle_message"
```

---

## Task 9: Add whitelist check to download_command()

**Files:**
- Modify: `bot.py`

- [ ] **Step 1: Add whitelist check at start of download_command()**

```python
# bot.py - in download_command() function, after getting user_id (around line 815)
async def download_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /download для групповых чатов."""
    # Проверяем, есть ли аргументы (URL после команды)
    if not context.args or len(context.args) == 0:
        await update.message.reply_text(
            '❌ Укажите ссылку после команды.\n\n'
            'Пример: /download https://youtube.com/watch?v=...'
        )
        return

    # Получаем URL из аргументов команды
    url = ' '.join(context.args)
    user_id = update.effective_user.id
    chat_type = update.message.chat.type

    # Check whitelist
    if not is_user_allowed(user_id, whitelist):
        logger.info(f'[User {user_id}] Access denied: not in whitelist')
        return  # Silent ignore

    # Rest of function continues...
```

- [ ] **Step 2: Test /download command with non-whitelisted user**

Send: `/download https://youtube.com/watch?v=test` from non-whitelisted account
Expected: No response

- [ ] **Step 3: Test /download command with whitelisted user**

Send: `/download https://youtube.com/watch?v=test` from whitelisted account
Expected: Normal bot processing (or URL validation error)

- [ ] **Step 4: Commit**

```bash
git add bot.py
git commit -m "feat: add whitelist check to download_command"
```

---

## Task 10: Add integration tests

**Files:**
- Create: `tests/test_whitelist_integration.py`

- [ ] **Step 1: Write integration test for non-whitelisted user**

```python
# tests/test_whitelist_integration.py
import pytest
from unittest.mock import AsyncMock, Mock
from bot import handle_message
from telegram import Update, Message, User, Chat

@pytest.fixture
def whitelist():
    """Test whitelist."""
    return {123456789}

@pytest.mark.asyncio
async def test_non_whitelisted_user_ignored(whitelist):
    """Non-whitelisted user gets no response."""
    # Mock update from non-whitelisted user
    update = Mock(spec=Update)
    update.effective_user = Mock(spec=User)
    update.effective_user.id = 999999999
    update.message = Mock(spec=Message)
    update.message.text = "https://youtube.com/watch?v=test"
    update.message.chat = Mock(spec=Chat)
    update.message.chat.type = "private"
    update.message.reply_text = AsyncMock()

    context = Mock()
    context.bot = Mock()
    context.bot.username = "testbot"

    # Import and patch whitelist
    import bot
    original_whitelist = bot.whitelist
    bot.whitelist = whitelist

    try:
        await handle_message(update, context)

        # Verify no response sent
        update.message.reply_text.assert_not_awaited()
    finally:
        bot.whitelist = original_whitelist
```

- [ ] **Step 2: Write integration test for whitelisted user**

```python
# tests/test_whitelist_integration.py

@pytest.mark.asyncio
async def test_whitelisted_user_allowed(whitelist):
    """Whitelisted user gets normal response."""
    # Mock update from whitelisted user
    update = Mock(spec=Update)
    update.effective_user = Mock(spec=User)
    update.effective_user.id = 123456789
    update.message = Mock(spec=Message)
    update.message.text = "invalid_url"  # Will fail URL validation, but proves access
    update.message.chat = Mock(spec=Chat)
    update.message.chat.type = "private"
    update.message.reply_text = AsyncMock()

    context = Mock()
    context.bot = Mock()
    context.bot.username = "testbot"

    # Import and patch whitelist
    import bot
    original_whitelist = bot.whitelist
    bot.whitelist = whitelist

    try:
        await handle_message(update, context)

        # Verify response sent (URL validation error)
        update.message.reply_text.assert_awaited_once()
        assert "Неверная ссылка" in update.message.reply_text.call_args[0][0]
    finally:
        bot.whitelist = original_whitelist
```

- [ ] **Step 3: Run integration tests**

Run: `uv run pytest tests/test_whitelist_integration.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_whitelist_integration.py
git commit -m "test: add whitelist integration tests"
```

---

## Task 11: Update README documentation

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add whitelist setup section to README**

```markdown
# README.md - add after installation section

## Whitelist Setup

This bot requires a user whitelist to restrict access. Only whitelisted users can use the bot.

1. **Get your Telegram User ID:**
   - Message @userinfobot on Telegram
   - Or use @getidsbot

2. **Create `whitelist.txt`:**
   ```bash
   # Add your user ID (one per line)
   123456789
   ```

3. **Start the bot:**
   ```bash
   uv run python bot.py
   ```

The bot will not start without a valid `whitelist.txt` file.

**Example `whitelist.txt`:**
```
# Admin users
123456789
987654321

# Friends
111222333
```

**Notes:**
- One user ID per line
- Lines starting with `#` are comments
- Empty lines are ignored
- Bot must be restarted to add new users
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add whitelist setup instructions"
```

---

## Task 12: Update .gitignore for whitelist file

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Add whitelist.txt to .gitignore**

```bash
# .gitignore - add to end
# Whitelist file (contains user IDs)
whitelist.txt
```

- [ ] **Step 2: Commit**

```bash
git add .gitignore
git commit -m "chore: add whitelist.txt to gitignore"
```

---

## Task 13: Final verification

**Files:**
- Test: Manual testing

- [ ] **Step 1: Verify bot fails without whitelist**

```bash
rm -f whitelist.txt
uv run python bot.py
```

Expected: ERROR with "whitelist.txt not found"

- [ ] **Step 2: Create whitelist and verify startup**

```bash
echo "123456789" > whitelist.txt
uv run python bot.py
```

Expected: Bot starts, shows "Loaded 1 whitelisted users"

- [ ] **Step 3: Test all tests pass**

Run: `uv run pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat: complete user whitelist feature

- Add auth module for whitelist loading and verification
- Integrate whitelist checks in message handlers
- Bot fails to start without valid whitelist
- Non-whitelisted users are silently ignored
- Add comprehensive unit and integration tests
- Update documentation with setup instructions"
```

---

## Verification Checklist

After implementation:

- [ ] Bot fails to start without `whitelist.txt`
- [ ] Bot fails to start with empty `whitelist.txt`
- [ ] Bot starts with valid `whitelist.txt` containing at least one user ID
- [ ] Non-whitelisted users receive no response (silent ignore)
- [ ] Whitelisted users can use all bot features
- [ ] Comments and blank lines in whitelist file are parsed correctly
- [ ] Invalid user IDs in whitelist are logged and skipped
- [ ] All tests pass: `uv run pytest tests/ -v`
- [ ] `whitelist.txt` is in `.gitignore`
- [ ] `whitelist.txt.example` exists with documentation
- [ ] README.md includes whitelist setup instructions
