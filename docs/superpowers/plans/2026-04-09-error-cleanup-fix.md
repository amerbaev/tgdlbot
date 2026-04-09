# Error Cleanup Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix bug where users remain stuck in `active_downloads` after failed downloads, preventing them from starting new downloads.

**Architecture:** Refactor `process_download()` to use try-finally structure, ensuring `cleanup_download()` is called in all scenarios (success, failure, cancellation, exception). Move cleanup from individual paths to a single `finally` block.

**Tech Stack:** Python 3.13, asyncio, python-telegram-bot, pytest

---

## Task 1: Add test for failed download cleanup

**Files:**
- Test: `tests/test_bot.py:270-295`

- [ ] **Step 1: Write the failing test**

Add this test after the existing `test_group_with_reply_to_bot` test (around line 433):

```python
async def test_download_failure_cleans_active_downloads(self, mock_update, mock_context, clean_active_downloads):
    """Test that failed download removes user from active_downloads."""
    from bot import active_downloads, process_download, DownloadTask

    # Setup mock update and context
    user_id = 123
    chat_id = 123456
    url = 'https://youtube.com/watch?v=test123'

    mock_update.effective_user.id = user_id
    mock_update.message.chat_id = chat_id
    mock_update.message.message_id = 1
    mock_update.message.text = url
    mock_update.effective_user.username = 'testuser'

    # Create mock status message
    status_message = await mock_update.message.reply_text('⏳ Добавлено в очередь...')
    status_message.edit_text = AsyncMock()

    # Create task
    task = DownloadTask(
        user_id=user_id,
        chat_id=chat_id,
        message_id=1,
        url=url,
        status_message=status_message,
        user_name='@testuser',
        download_id='test123',
    )

    # Add user to active_downloads (simulating download started)
    active_downloads[user_id] = {
        'chat_id': chat_id,
        'message_id': 1,
        'status': 'downloading',
        'url': url,
        'download_id': 'test123',
    }

    # Process download (will fail because URL is invalid)
    await process_download(task)

    # Verify user is removed from active_downloads
    assert user_id not in active_downloads
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_bot.py::TestBot::test_download_failure_cleans_active_downloads -v`

Expected: FAIL - User remains in `active_downloads` after failed download

- [ ] **Step 3: Commit test**

```bash
git add tests/test_bot.py
git commit -m "test: add failing test for download cleanup bug

Test verifies that users are removed from active_downloads after
failed downloads. Currently fails due to missing cleanup call.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 2: Refactor process_download() to use try-finally

**Files:**
- Modify: `bot.py:682-739`

- [ ] **Step 1: Read the current process_download() function**

Run: `sed -n '682,739p' bot.py`

This shows the current implementation to understand the structure.

- [ ] **Step 2: Replace process_download() with try-finally version**

Replace the entire `process_download()` function (lines 682-739) with:

```python
async def process_download(task: DownloadTask) -> None:
    """Асинхронная обработка скачивания видео.

    Args:
        task: Задача с информацией о пользователе и URL
    """
    user_id = task.user_id
    url = task.url
    video_path: Optional[str] = None
    user_mention = task.user_name

    try:
        # Проверяем отмену
        if user_id in cancelled_downloads:
            logger.info(f'[User {user_id}] Загрузка отменена до начала')
            return

        # Создаём клавиатуру с кнопкой отмены
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ Отмена", callback_data=f'cancel_{user_id}')
        ]])

        await task.status_message.edit_text(
            f'⏳ Скачиваю видео...\n\n'
            f'👤 {user_mention}\n'
            f'📎 {url[:50]}...',
            reply_markup=keyboard
        )

        logger.info(f'[User {user_id}] Запуск скачивания: {url}')
        video_path = await asyncio.to_thread(download_video_sync, url)

        # Проверяем отмену после скачивания
        if user_id in cancelled_downloads:
            try:
                await task.status_message.edit_text('❌ Загрузка отменена')
            except Exception:
                pass
            return

        if not video_path or not os.path.exists(video_path):
            await _send_download_error(task.status_message)
            return

        await _process_download_success(task, video_path)

    except Exception as e:
        logger.error(f'[User {user_id}] Ошибка обработки: {e}')
        try:
            await task.status_message.edit_text(f'❌ Ошибка: {e}')
        except Exception as msg_error:
            logger.warning(f'[User {user_id}] Не удалось обновить статус: {msg_error}')

    finally:
        cleanup_download(user_id, video_path)
```

Key changes:
- Initialize `video_path = None` before try block
- Wrap entire body in `try:` block
- Add `finally:` block that calls `cleanup_download(user_id, video_path)`
- Removed explicit cleanup calls from cancellation path (handled by finally)
- Pass `video_path` to `_process_download_success()` (changed in Task 3)

- [ ] **Step 3: Verify syntax**

Run: `python -m py_compile bot.py`

Expected: No syntax errors

- [ ] **Step 4: Run the failing test**

Run: `uv run pytest tests/test_bot.py::TestBot::test_download_failure_cleans_active_downloads -v`

Expected: Still fails (we haven't updated `_process_download_success` yet)

- [ ] **Step 5: Commit the refactoring**

```bash
git add bot.py
git commit -m "refactor: add try-finally to process_download for guaranteed cleanup

Initialize video_path=None, wrap body in try-finally, and ensure
cleanup_download() is always called regardless of success/failure.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 3: Update _process_download_success() signature and remove cleanup

**Files:**
- Modify: `bot.py:663-679`

- [ ] **Step 1: Read current _process_download_success() function**

Run: `sed -n '663,679p' bot.py`

- [ ] **Step 2: Update function to accept video_path and remove cleanup**

Replace the entire `_process_download_success()` function with:

```python
async def _process_download_success(task: DownloadTask, video_path: str) -> None:
    """Обрабатывает успешное скачивание.

    Args:
        task: Задача скачивания
        video_path: Путь к скачанному видео
    """
    file_size = os.path.getsize(video_path)

    if file_size > MAX_FILE_SIZE:
        success = await _send_large_video(task, video_path)
        if not success:
            return
    else:
        await _send_single_video(task, video_path)
```

Key changes:
- Add `video_path: str` parameter
- Remove `cleanup_download(task.user_id)` call from line 679
- Pass `video_path` to `_send_large_video()` (already correct in current code)
- Pass `video_path` to `_send_single_video()` (already correct in current code)

- [ ] **Step 3: Verify syntax**

Run: `python -m py_compile bot.py`

Expected: No syntax errors

- [ ] **Step 4: Run the test**

Run: `uv run pytest tests/test_bot.py::TestBot::test_download_failure_cleans_active_downloads -v`

Expected: PASS - User is now removed from `active_downloads` after failed download

- [ ] **Step 5: Commit the change**

```bash
git add bot.py
git commit -m "refactor: remove cleanup call from _process_download_success

Cleanup is now handled by the finally block in process_download().
Updated signature to accept video_path parameter for consistency.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 4: Run all tests to verify no regressions

**Files:**
- Test: `tests/test_bot.py`

- [ ] **Step 1: Run all existing tests**

Run: `uv run pytest tests/test_bot.py -v`

Expected: All tests pass

- [ ] **Step 2: Run specific tests that check cleanup behavior**

Run: `uv run pytest tests/test_bot.py::TestBot::test_duplicate_blocked -v`

Expected: PASS - Users still blocked during active downloads

- [ ] **Step 3: Run success path tests**

Run: `uv run pytest tests/test_bot.py -k "success or download" -v`

Expected: All download/success tests pass

- [ ] **Step 4: Commit test results**

```bash
git add tests/test_bot.py
git commit -m "test: verify all tests pass after cleanup refactoring

No regressions in existing tests. New test for failure cleanup passes.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 5: Add additional tests for edge cases

**Files:**
- Test: `tests/test_bot.py`

- [ ] **Step 1: Add test for cancellation cleanup**

Add this test after the previous new test:

```python
async def test_download_cancellation_cleans_active_downloads(self, mock_update, mock_context, clean_active_downloads):
    """Test that cancelled download triggers cleanup in finally block."""
    from bot import active_downloads, cancelled_downloads, process_download, DownloadTask

    user_id = 123
    chat_id = 123456
    url = 'https://youtube.com/watch?v=test123'

    mock_update.effective_user.id = user_id
    mock_update.message.chat_id = chat_id
    mock_update.message.message_id = 1
    mock_update.message.text = url
    mock_update.effective_user.username = 'testuser'

    status_message = await mock_update.message.reply_text('⏳ Добавлено в очередь...')
    status_message.edit_text = AsyncMock()

    task = DownloadTask(
        user_id=user_id,
        chat_id=chat_id,
        message_id=1,
        url=url,
        status_message=status_message,
        user_name='@testuser',
        download_id='test123',
    )

    # Add user to active_downloads and mark as cancelled
    active_downloads[user_id] = {
        'chat_id': chat_id,
        'message_id': 1,
        'status': 'downloading',
        'url': url,
        'download_id': 'test123',
    }
    cancelled_downloads.add(user_id)

    # Process download (will be cancelled)
    await process_download(task)

    # Verify user is removed from active_downloads by finally block
    assert user_id not in active_downloads

    # Clean up
    cancelled_downloads.discard(user_id)
```

- [ ] **Step 2: Add test for exception handling cleanup**

```python
async def test_exception_in_download_triggers_cleanup(self, mock_update, mock_context, clean_active_downloads):
    """Test that exceptions during download still trigger cleanup."""
    from bot import active_downloads, process_download, DownloadTask
    from unittest.mock import patch

    user_id = 123
    chat_id = 123456
    url = 'https://youtube.com/watch?v=test123'

    mock_update.effective_user.id = user_id
    mock_update.message.chat_id = chat_id
    mock_update.message.message_id = 1
    mock_update.message.text = url
    mock_update.effective_user.username = 'testuser'

    status_message = await mock_update.message.reply_text('⏳ Добавлено в очередь...')
    status_message.edit_text = AsyncMock()

    task = DownloadTask(
        user_id=user_id,
        chat_id=chat_id,
        message_id=1,
        url=url,
        status_message=status_message,
        user_name='@testuser',
        download_id='test123',
    )

    # Add user to active_downloads
    active_downloads[user_id] = {
        'chat_id': chat_id,
        'message_id': 1,
        'status': 'downloading',
        'url': url,
        'download_id': 'test123',
    }

    # Mock asyncio.to_thread to raise exception
    with patch('bot.asyncio.to_thread', side_effect=Exception('Test error')):
        await process_download(task)

    # Verify user is removed from active_downloads by finally block
    assert user_id not in active_downloads
```

- [ ] **Step 3: Run new tests**

Run: `uv run pytest tests/test_bot.py::TestBot::test_download_cancellation_cleans_active_downloads tests/test_bot.py::TestBot::test_exception_in_download_triggers_cleanup -v`

Expected: Both tests PASS

- [ ] **Step 4: Run all tests**

Run: `uv run pytest tests/test_bot.py -v`

Expected: All 27 tests pass (24 existing + 3 new)

- [ ] **Step 5: Commit new tests**

```bash
git add tests/test_bot.py
git commit -m "test: add edge case tests for cleanup behavior

Tests verify that cleanup happens correctly in:
- Cancellation scenarios
- Exception scenarios

All edge cases now properly handled by try-finally structure.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 6: Manual testing verification

**Files:**
- None (manual testing)

- [ ] **Step 1: Start bot locally**

Run: `uv run python bot.py`

- [ ] **Step 2: Test failed download flow**

1. Send an invalid/unsupported URL to the bot
2. Verify you receive an error message
3. Immediately send another URL (valid or invalid)
4. Verify you do NOT get "Вы уже скачиваете видео" message
5. Expected: Second URL is processed normally

- [ ] **Step 3: Test successful download flow**

1. Send a valid YouTube URL
2. Verify download completes successfully
3. Send another URL immediately
4. Verify it's processed normally
5. Expected: Both downloads work sequentially

- [ ] **Step 4: Test cancellation flow**

1. Send a valid YouTube URL
2. Click the cancel button immediately
3. Send another URL immediately
4. Verify it's processed normally
5. Expected: No "already downloading" message after cancellation

- [ ] **Step 5: Document manual test results**

Create a brief note in the project README or test documentation:

```bash
echo "
## Manual Testing - Error Cleanup Fix (2026-04-09)

### Test Results
- ✅ Failed download allows immediate retry
- ✅ Successful download allows immediate retry
- ✅ Cancellation allows immediate retry
- ✅ No 'already downloading' message after errors

### Tested By
- Date: $(date +%Y-%m-%d)
- Bot Version: $(git describe --tags --always)
" >> MANUAL_TESTING.md
```

- [ ] **Step 6: Commit manual testing documentation**

```bash
git add MANUAL_TESTING.md
git commit -m "docs: add manual testing results for error cleanup fix

Verified that users can retry downloads immediately after:
- Download failures
- Successful downloads
- Cancellations

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 7: Final verification and cleanup

**Files:**
- All modified files

- [ ] **Step 1: Verify git log shows clean commits**

Run: `git log --oneline -10`

Expected: Series of focused commits implementing the fix

- [ ] **Step 2: Run full test suite one more time**

Run: `uv run pytest tests/ -v`

Expected: All tests pass

- [ ] **Step 3: Check for any TODO or FIXME comments**

Run: `grep -r "TODO\|FIXME" bot.py tests/test_bot.py`

Expected: No new TODOs or FIXMEs related to this change

- [ ] **Step 4: Verify the design spec requirements are met**

Check each requirement from `docs/superpowers/specs/2026-04-09-error-cleanup-fix-design.md`:
- [ ] Users can immediately download after failure
- [ ] `active_downloads` cleaned in all scenarios
- [ ] All existing tests pass
- [ ] New tests cover bug fix
- [ ] No regressions in success/cancellation/exception paths

- [ ] **Step 5: Create final summary commit**

```bash
git add docs/superpowers/specs/2026-04-09-error-cleanup-fix-design.md docs/superpowers/plans/2026-04-09-error-cleanup-fix.md
git commit -m "docs: add design spec and implementation plan for error cleanup

Complete documentation of the bug fix and implementation approach.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

- [ ] **Step 6: Verify implementation matches plan**

Run: `git diff HEAD~7 bot.py tests/test_bot.py | head -100`

Expected: Changes align with implementation plan

---

## Summary

This plan fixes the bug where users get stuck in `active_downloads` after failed downloads by:

1. Adding tests to verify the bug exists
2. Refactoring `process_download()` to use try-finally for guaranteed cleanup
3. Removing duplicate cleanup calls from individual paths
4. Adding comprehensive tests for all edge cases
5. Manual verification of the fix

**Total estimated time:** 30-45 minutes
**Number of commits:** 7-8 focused commits
**Test coverage:** +3 new tests, all 27 tests passing
