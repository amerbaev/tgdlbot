"""Regressions at file, Telegram and downloader boundaries; no live services."""

import asyncio
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import yt_dlp

import bot


URL = 'https://youtube.com/watch?v=test'


@pytest.fixture(autouse=True)
def isolated_downloads(tmp_path, monkeypatch):
    monkeypatch.setattr(bot, 'DOWNLOAD_DIR', str(tmp_path))
    bot.active_downloads.clear()
    bot.cancelled_downloads.clear()
    yield tmp_path
    bot.active_downloads.clear()
    bot.cancelled_downloads.clear()


def make_update(user_id=123):
    message = SimpleNamespace(
        text=URL, chat=SimpleNamespace(type='private'), chat_id=456,
        message_id=1, reply_text=AsyncMock(),
    )
    return SimpleNamespace(
        message=message,
        effective_user=SimpleNamespace(id=user_id, username='tester', first_name='Test'),
    )


def make_task():
    return bot.DownloadTask(123, 456, 1, URL, AsyncMock(), '@tester', download_id='job123')


@pytest.mark.asyncio
async def test_reserves_slot_before_reply_and_rejects_duplicate(monkeypatch):
    entered, release = asyncio.Event(), asyncio.Event()
    first, second = make_update(), make_update()

    async def reply(*args, **kwargs):
        entered.set()
        await release.wait()
        return AsyncMock()

    first.message.reply_text.side_effect = reply
    process = AsyncMock()
    monkeypatch.setattr(bot, 'process_download', process)
    first_request = asyncio.create_task(bot.handle_message(first, SimpleNamespace()))
    await entered.wait()
    await bot.handle_message(second, SimpleNamespace())
    release.set()
    await first_request
    await asyncio.gather(*list(bot.background_tasks))
    assert 'уже скачиваете' in second.message.reply_text.call_args.args[0]
    assert process.await_count == 1


@pytest.mark.asyncio
async def test_fourth_download_is_rejected_without_starting_worker(monkeypatch):
    bot.active_downloads.update({i: {'download_id': str(i)} for i in range(3)})
    process = AsyncMock()
    monkeypatch.setattr(bot, 'process_download', process)
    update = make_update()
    await bot.handle_message(update, SimpleNamespace())
    await asyncio.gather(*list(bot.background_tasks))
    assert 123 not in bot.active_downloads
    assert process.await_count == 0
    assert 'занят' in update.message.reply_text.call_args.args[0].lower()


@pytest.mark.asyncio
async def test_failed_status_reply_releases_reservation():
    update = make_update()
    update.message.reply_text.side_effect = RuntimeError('offline')
    with pytest.raises(RuntimeError):
        await bot.handle_message(update, SimpleNamespace())
    assert 123 not in bot.active_downloads


@pytest.mark.asyncio
@pytest.mark.parametrize('data,actor', [('cancel_123_oldjob', 123), ('cancel_123_current', 999)])
async def test_stale_or_foreign_cancel_does_not_change_active_download(data, actor):
    bot.active_downloads[123] = {'download_id': 'current'}
    query = SimpleNamespace(
        data=data, from_user=SimpleNamespace(id=actor),
        answer=AsyncMock(), edit_message_text=AsyncMock(),
    )
    await bot.cancel_button(SimpleNamespace(callback_query=query), SimpleNamespace())
    assert 123 not in bot.cancelled_downloads
    query.edit_message_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_parts_are_removed_when_upload_fails(isolated_downloads):
    paths = [isolated_downloads / f'job_part{i}.mp4' for i in range(3)]
    for path in paths:
        path.write_bytes(b'video')
    status = AsyncMock()
    status.reply_video.side_effect = RuntimeError('upload failed')
    with pytest.raises(RuntimeError):
        await bot._send_video_parts(status, list(map(str, paths)))
    assert not any(path.exists() for path in paths)


@pytest.mark.asyncio
async def test_internal_exception_is_not_sent_to_user(monkeypatch):
    task = make_task()
    secret = 'private-path-or-credential'
    monkeypatch.setattr(bot, 'download_video_sync', lambda *args: (_ for _ in ()).throw(RuntimeError(secret)))
    await bot.process_download(task)
    assert secret not in task.status_message.edit_text.call_args.args[0]
    assert task.user_id not in bot.active_downloads


def test_success_does_not_fetch_metadata_again(isolated_downloads, monkeypatch):
    calls = []

    def extract(ydl, url, download=True, **kwargs):
        calls.append(download)
        if len(calls) > 2:
            raise yt_dlp.utils.DownloadError('metadata expired after successful download')
        info = {'id': 'test', 'title': 'video', 'ext': 'mp4', 'formats': []}
        if download:
            Path(ydl.prepare_filename(info)).write_bytes(b'video')
        return info

    monkeypatch.setattr(yt_dlp.YoutubeDL, 'extract_info', extract)
    result = bot.download_video_sync(URL)
    assert result is not None
    assert Path(result).read_bytes() == b'video'
    assert calls == [False, True]


def test_failed_download_removes_partial_files(isolated_downloads, monkeypatch):
    def extract(ydl, url, download=True, **kwargs):
        info = {'id': 'test', 'title': 'video', 'ext': 'mp4', 'formats': []}
        if download:
            Path(ydl.prepare_filename(info) + '.part').write_bytes(b'partial')
            raise yt_dlp.utils.DownloadError('connection failed')
        return info

    monkeypatch.setattr(yt_dlp.YoutubeDL, 'extract_info', extract)
    assert bot.download_video_sync(URL) is None
    assert list(isolated_downloads.iterdir()) == []


def test_live_stream_is_rejected_before_download(monkeypatch):
    calls = []

    def extract(ydl, url, download=True, **kwargs):
        calls.append(download)
        return {'id': 'test', 'title': 'live', 'ext': 'mp4', 'is_live': True, 'formats': []}

    monkeypatch.setattr(yt_dlp.YoutubeDL, 'extract_info', extract)
    assert bot.download_video_sync(URL) is None
    assert calls == [False]


@pytest.mark.asyncio
async def test_current_cancel_stops_its_download():
    bot.active_downloads[123] = {'download_id': 'current'}
    query = SimpleNamespace(
        data='cancel_123_current', from_user=SimpleNamespace(id=123),
        answer=AsyncMock(), edit_message_text=AsyncMock(),
    )
    await bot.cancel_button(SimpleNamespace(callback_query=query), SimpleNamespace())
    assert 123 in bot.cancelled_downloads
    bot.cleanup_download(123)
    assert 123 not in bot.cancelled_downloads


@pytest.mark.parametrize('reason', ['cancel', 'size'])
def test_progress_abort_cleans_partial_file(isolated_downloads, monkeypatch, reason):
    stopped = False
    calls = []
    monkeypatch.setattr(bot, 'MAX_DOWNLOAD_SIZE', 10)

    def extract(ydl, url, download=True, **kwargs):
        nonlocal stopped
        calls.append(download)
        info = {'id': 'test', 'title': 'video', 'ext': 'mp4', 'formats': []}
        if download:
            Path(ydl.prepare_filename(info) + '.part').write_bytes(b'partial')
            stopped = reason == 'cancel'
            for hook in ydl.params['progress_hooks']:
                hook({'downloaded_bytes': 11 if reason == 'size' else 1})
        return info

    monkeypatch.setattr(yt_dlp.YoutubeDL, 'extract_info', extract)
    assert bot.download_video_sync(URL, cancelled=lambda: stopped) is None
    assert list(isolated_downloads.iterdir()) == []
    assert calls == [False, True]


@pytest.mark.asyncio
async def test_async_cancellation_waits_for_download_cleanup(isolated_downloads, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    task = make_task()
    path = isolated_downloads / 'job123_1.mp4'
    bot.active_downloads[task.user_id] = {'download_id': task.download_id}

    def download(*args):
        entered.set()
        assert release.wait(3)
        path.write_bytes(b'late download')
        return str(path)

    monkeypatch.setattr(bot, 'download_video_sync', download)
    pending = asyncio.create_task(bot.process_download(task))
    try:
        assert await asyncio.to_thread(entered.wait, 3)
        pending.cancel()
        await asyncio.sleep(0)
        assert task.user_id in bot.active_downloads
    finally:
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await pending
    assert task.user_id not in bot.active_downloads
    assert not path.exists()


@pytest.mark.asyncio
async def test_async_cancellation_waits_for_split_cleanup(isolated_downloads, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    task = make_task()
    source = isolated_downloads / 'job123_1.mp4'
    source.write_bytes(b'source')
    part = isolated_downloads / 'job123_1_part1.mp4'

    def split(*args):
        entered.set()
        assert release.wait(3)
        part.write_bytes(b'late part')
        return [str(part)]

    monkeypatch.setattr(bot, 'split_video', split)
    pending = asyncio.create_task(bot._send_large_video(task, str(source)))
    try:
        assert await asyncio.to_thread(entered.wait, 3)
        pending.cancel()
        await asyncio.sleep(0)
        assert not pending.done(), 'cleanup must wait for the writing thread'
    finally:
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await pending
    assert not part.exists()


@pytest.mark.asyncio
async def test_status_failure_after_split_cleans_parts(isolated_downloads, monkeypatch):
    task = make_task()
    source = isolated_downloads / 'job123_1.mp4'
    source.write_bytes(b'source')
    part = isolated_downloads / 'job123_1_part1.mp4'
    part.write_bytes(b'part')
    monkeypatch.setattr(bot, 'split_video', lambda *args: [str(part)])
    task.status_message.edit_text.side_effect = [None, RuntimeError('offline')]
    with pytest.raises(RuntimeError):
        await bot._send_large_video(task, str(source))
    assert not part.exists()
