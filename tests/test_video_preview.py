"""Preview generation and Telegram upload regressions, without network access."""

import asyncio
import subprocess
import threading
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import yt_dlp

import bot
import media


JPEG = b'\xff\xd8\xff\xe0preview\xff\xd9'


@pytest.fixture
def video(tmp_path, monkeypatch):
    monkeypatch.setattr(media, 'DOWNLOAD_DIR', str(tmp_path))
    monkeypatch.setattr(bot, 'DOWNLOAD_DIR', str(tmp_path))
    path = tmp_path / 'job_video.mp4'
    path.write_bytes(b'video')
    return path


def test_preview_returns_jpeg_without_creating_files(video, monkeypatch):
    def run(command, **kwargs):
        assert command[0] == 'ffmpeg'
        assert command[command.index('-i') + 1] == str(video)
        assert command[-1] == 'pipe:1'
        assert 0 < kwargs['timeout'] <= 30
        assert kwargs['check'] is True
        return subprocess.CompletedProcess(command, 0, JPEG, b'')

    monkeypatch.setattr(media.subprocess, 'run', run)
    assert media.create_video_preview(str(video)) == JPEG
    assert list(video.parent.iterdir()) == [video]


@pytest.mark.parametrize('output', [b'', b'not a jpeg', JPEG + bytes(200 * 1024) + b'\xff\xd9'],
                         ids=['empty', 'invalid', 'oversized'])
def test_preview_rejects_empty_invalid_or_oversized_output(video, monkeypatch, output):
    monkeypatch.setattr(media.subprocess, 'run', lambda *a, **kw:
                        subprocess.CompletedProcess(a[0], 0, output, b''))
    assert media.create_video_preview(str(video)) is None


@pytest.mark.parametrize('failure', [FileNotFoundError(), subprocess.TimeoutExpired('ffmpeg', 30),
                                   subprocess.CalledProcessError(1, 'ffmpeg')])
def test_preview_failure_is_optional(video, monkeypatch, failure):
    def run(*args, **kwargs):
        raise failure

    monkeypatch.setattr(media.subprocess, 'run', run)
    assert media.create_video_preview(str(video)) is None


@pytest.mark.asyncio
@pytest.mark.parametrize('parts', [False, True])
async def test_upload_includes_explicit_cover_and_thumbnail(video, monkeypatch, parts):
    generated = []
    main_thread = threading.get_ident()

    def preview(path):
        assert threading.get_ident() != main_thread
        generated.append(path)
        return JPEG + path.encode()

    # raising=False lets the regression fail at the missing upload attachment.
    monkeypatch.setattr(bot, 'create_video_preview', preview, raising=False)
    status = AsyncMock()
    received = []

    async def send(**kwargs):
        assert kwargs['video'].read() == b'video'
        expected = JPEG + kwargs['video'].name.encode()
        for field in ('thumbnail', 'cover'):
            assert kwargs[field].input_file_content == expected
            assert kwargs[field].mimetype == 'image/jpeg'
        assert kwargs['thumbnail'] is not kwargs['cover']
        received.append(kwargs['video'])

    status.reply_video.side_effect = send
    paths = [str(video)]
    if parts:
        second = video.with_name('job_video_part2.mp4')
        second.write_bytes(b'video')
        paths.append(str(second))
        await bot._send_video_parts(status, paths)
        assert not video.exists() and not second.exists()
    else:
        task = bot.DownloadTask(1, 2, 3, 'url', status, 'user')
        await bot._send_single_video(task, str(video))
        assert video.exists()
    assert generated == paths
    assert all(stream.closed for stream in received)


@pytest.mark.asyncio
async def test_upload_continues_without_preview(video, monkeypatch):
    monkeypatch.setattr(bot, 'create_video_preview', lambda path: None, raising=False)
    status = AsyncMock()
    await bot._send_single_video(bot.DownloadTask(1, 2, 3, 'url', status, 'user'), str(video))
    assert set(status.reply_video.call_args.kwargs) == {'video'}


@pytest.mark.asyncio
async def test_cancellation_waits_for_preview_before_cleaning_parts(video, monkeypatch):
    entered, release = threading.Event(), threading.Event()

    def preview(path):
        entered.set()
        assert release.wait(3)
        assert video.exists(), 'source must remain available to ffmpeg'
        return JPEG

    monkeypatch.setattr(bot, 'create_video_preview', preview, raising=False)
    status = AsyncMock()
    pending = asyncio.create_task(bot._send_video_parts(status, [str(video)]))
    try:
        assert await asyncio.to_thread(entered.wait, 3)
        pending.cancel()
        await asyncio.sleep(0)
        assert not pending.done()
    finally:
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await pending
    status.reply_video.assert_not_awaited()
    assert not video.exists()


@pytest.mark.parametrize('url', ['https://youtu.be/test', 'https://www.instagram.com/reel/test/'])
def test_download_keeps_source_cover_until_job_cleanup(video, monkeypatch, url):
    calls = []
    monkeypatch.setattr(bot, 'INSTAGRAM_COOKIES_FILE', '')

    def extract(ydl, url, download=True, **kwargs):
        calls.append(download)
        info = {'id': 'test', 'title': 'video', 'ext': 'mp4', 'formats': []}
        if download:
            path = Path(ydl.prepare_filename(info))
            path.write_bytes(b'video')
            if ydl.params.get('writethumbnail'):
                cover = path.with_suffix('.webp')
                cover.write_bytes(b'original cover')
                info['thumbnails'] = [{'filepath': str(cover)}]
        return info

    monkeypatch.setattr(yt_dlp.YoutubeDL, 'extract_info', extract)
    path = bot.download_video_sync(url, 'sourcejob')
    assert path is not None
    cover = Path(path + '.cover')
    assert cover.read_bytes() == b'original cover'
    assert calls == [False, True], 'do not fetch metadata again for a cover'
    bot.cleanup_download(1, path, 'sourcejob')
    assert not cover.exists() and not Path(path).exists()
    assert video.exists(), 'cleanup must preserve unrelated jobs'
