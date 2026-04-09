# Error Cleanup Fix Design

**Date:** 2026-04-09
**Status:** Approved
**Author:** Claude Code

## Problem

When a video download fails, the user remains in `active_downloads` and receives the message "⚠️ Вы уже скачиваете видео! Дождитесь окончания текущей загрузки." when trying to download again, even though the previous download failed.

**Root Cause:** In `process_download()` function, when `download_video_sync()` returns `None` (failure), the error message is sent but `cleanup_download()` is never called, leaving the user stuck in `active_downloads`.

## Solution

Refactor `process_download()` to use a try-finally structure, ensuring cleanup happens in ALL cases (success, failure, cancellation, exception).

## Architecture

### Current State (Bug)

```
process_download():
  try:
    video_path = download_video_sync()
    if not video_path:
      _send_download_error()
      return  # ❌ NO CLEANUP - user stuck in active_downloads
    _process_download_success()  # calls cleanup here
  except Exception:
    cleanup_download()  # ✅ cleanup happens
```

### New State (Fixed)

```
process_download():
  video_path = None
  try:
    # cancellation check
    video_path = download_video_sync()
    if not video_path:
      _send_download_error()
      return  # ✅ finally block will cleanup
    _process_download_success()  # cleanup REMOVED from here
  except Exception:
    logger.error()
    # ✅ No explicit cleanup needed - finally block handles it
  finally:
    cleanup_download(user_id, video_path)  # ✅ ALWAYS runs
```

## Components

### Changes Required

1. **`process_download()` function** (bot.py, lines 682-739)
   - Initialize `video_path = None` at the start
   - Wrap entire function body in `try:` block
   - Add `finally:` block that calls `cleanup_download(user_id, video_path)`
   - Remove cleanup calls from cancellation path (lines 721, 723)

2. **`_process_download_success()` function** (bot.py, line 663-679)
   - Remove `cleanup_download(task.user_id)` call from line 679

### No Changes To

- `cleanup_download()` function - works correctly with `video_path=None`
- `handle_message()` - no changes needed
- `download_command()` - no changes needed
- All other functions

## Data Flow

### Failure Flow (Bug Fix)
```
User sends URL
  → Add to active_downloads
  → process_download() starts
  → download_video_sync() returns None
  → _send_download_error()
  → return
  → finally: cleanup_download(user_id, None)
      → Remove from active_downloads ✅
      → No file to delete (video_path is None)
```

### Success Flow (No Behavior Change)
```
User sends URL
  → Add to active_downloads
  → process_download() starts
  → download_video_sync() returns path
  → _process_download_success()
      → Send video to user
  → return
  → finally: cleanup_download(user_id, video_path)
      → Remove from active_downloads ✅
      → Delete video file ✅
```

### Cancellation Flow (No Behavior Change)
```
User clicks cancel
  → cancelled_downloads.add(user_id)
  → process_download() checks cancelled
  → return
  → finally: cleanup_download(user_id, video_path)
      → Remove from active_downloads ✅
      → Delete file if download started ✅
```

## Error Handling

### Exception Handling (Preserved)
```python
except Exception as e:
    logger.error(f'[User {user_id}] Ошибка обработки: {e}')
    try:
        await task.status_message.edit_text(f'❌ Ошибка: {e}')
    except Exception:
        pass
    # No explicit cleanup needed - finally block handles it
```

### Edge Cases Handled
- **User cancels before download starts** → `video_path=None`, finally removes from `active_downloads`
- **Download fails** → `video_path=None`, finally removes from `active_downloads`, no file deletion
- **Download succeeds but sending fails** → `video_path` exists, finally removes from `active_downloads` and deletes file
- **Exception during processing** → finally ensures cleanup regardless of exception type

### Safety
- `cleanup_download()` safely handles `video_path=None` - only attempts file deletion if path exists
- `is_safe_path()` check prevents deletion of files outside `DOWNLOAD_DIR`
- No changes to safety checks needed

## Testing

### New Tests Required

1. **`test_download_failure_cleans_active_downloads`**
   - Mock `download_video_sync()` to return `None`
   - Call `process_download()`
   - Assert `user_id not in active_downloads`

2. **`test_download_failure_deletes_partial_files`**
   - Mock `download_video_sync()` to create a partial file then return `None`
   - Call `process_download()`
   - Assert partial file is deleted

3. **`test_download_cancellation_cleans_active_downloads`**
   - Add user to `cancelled_downloads` before processing
   - Call `process_download()`
   - Assert `user_id not in active_downloads` after finally block

4. **`test_exception_in_download_triggers_cleanup`**
   - Mock `download_video_sync()` to raise exception
   - Call `process_download()`
   - Assert `user_id not in active_downloads` and video_path deleted

### Existing Tests to Verify
- `test_duplicate_blocked` - Should still pass
- All success path tests - Should still pass
- `test_cancel_command` - Should still pass

### Manual Testing Checklist
- [ ] Send invalid URL → get error → send another URL immediately → should work
- [ ] Start download → cancel → send new URL → should work
- [ ] Send valid URL → download succeeds → send another URL → should work

## Implementation Notes

- `video_path` must be initialized to `None` at the start of `process_download()` before the `try` block
- The `finally` block executes after `return` statements, ensuring cleanup
- `cleanup_download()` is idempotent - safe to call multiple times
- No changes to error messages or user-facing behavior

## Success Criteria

- [ ] Users can immediately download again after a failed download
- [ ] `active_downloads` is properly cleaned in all scenarios
- [ ] All existing tests pass
- [ ] New tests cover the bug fix
- [ ] No regression in success, cancellation, or exception paths
