"""Display dimensions must reach Telegram before the client downloads the video."""

import asyncio
import json
import subprocess
import threading
from unittest.mock import AsyncMock

import pytest

import bot
import media


@pytest.fixture
def video(tmp_path, monkeypatch):
    monkeypatch.setattr(media, 'DOWNLOAD_DIR', str(tmp_path))
    monkeypatch.setattr(bot, 'DOWNLOAD_DIR', str(tmp_path))
    path = tmp_path / 'job_video.mp4'
    path.write_bytes(b'video')
    return path


@pytest.mark.parametrize('stream,expected', [
    ({'width': 1920, 'height': 1080}, {'width': 1920, 'height': 1080}),
    ({'width': 1080, 'height': 1920}, {'width': 1080, 'height': 1920}),
    ({'width': 720, 'height': 720}, {'width': 720, 'height': 720}),
    ({'width': 1920, 'height': 1080, 'side_data_list': [{'rotation': -90}]},
     {'width': 1080, 'height': 1920}),
    ({'width': 1920, 'height': 1080, 'tags': {'rotate': '270'}},
     {'width': 1080, 'height': 1920}),
    ({'width': 1920, 'height': 1080, 'side_data_list': [{'rotation': 180}]},
     {'width': 1920, 'height': 1080}),
    ({'width': 1920, 'height': 1080, 'side_data_list': [{'rotation': 0}],
      'tags': {'rotate': '90'}}, {'width': 1920, 'height': 1080}),
    ({'width': 720, 'height': 576, 'sample_aspect_ratio': '16:15'},
     {'width': 768, 'height': 576}),
    ({'width': 720, 'height': 576, 'sample_aspect_ratio': '16:15',
      'side_data_list': [{'rotation': 90}]}, {'width': 576, 'height': 768}),
    ({'width': 640, 'height': 360, 'sample_aspect_ratio': 'N/A', 'tags': {'rotate': 'N/A'}},
     {'width': 640, 'height': 360}),
])
def test_reads_display_dimensions(video, monkeypatch, stream, expected):
    def run(command, **kwargs):
        assert command[0] == 'ffprobe'
        assert command[command.index('-select_streams') + 1] == 'V:0'
        assert command[-1] == str(video)
        assert 0 < kwargs['timeout'] <= 30
        assert kwargs['check'] is True
        return subprocess.CompletedProcess(command, 0, json.dumps({'streams': [stream]}), '')

    monkeypatch.setattr(media.subprocess, 'run', run)
    assert media.get_video_dimensions(str(video)) == expected


@pytest.mark.parametrize('output', [
    'not json', '{}', '{"streams": []}', '{"streams": [{}]}',
    '{"streams": [{"width": 0, "height": 360}]}',
    '{"streams": [{"width": 640, "height": -1}]}',
    '{"streams": [{"width": "unknown", "height": 360}]}',
])
def test_invalid_dimensions_are_omitted(video, monkeypatch, output):
    monkeypatch.setattr(media.subprocess, 'run', lambda *a, **kw:
                        subprocess.CompletedProcess(a[0], 0, output, ''))
    assert media.get_video_dimensions(str(video)) == {}


@pytest.mark.parametrize('failure', [FileNotFoundError(), subprocess.TimeoutExpired('ffprobe', 30),
                                   subprocess.CalledProcessError(1, 'ffprobe')])
def test_probe_failure_is_optional(video, monkeypatch, failure):
    def run(*args, **kwargs):
        raise failure

    monkeypatch.setattr(media.subprocess, 'run', run)
    assert media.get_video_dimensions(str(video)) == {}


@pytest.mark.asyncio
@pytest.mark.parametrize('parts', [False, True])
async def test_upload_sends_each_videos_dimensions(video, monkeypatch, parts):
    expected = {str(video): {'width': 1080, 'height': 1920}}
    main_thread = threading.get_ident()
    probed = []

    def dimensions(path):
        assert threading.get_ident() != main_thread
        probed.append(path)
        return expected[path]

    monkeypatch.setattr(bot, 'get_video_dimensions', dimensions, raising=False)
    monkeypatch.setattr(bot, 'create_video_preview', lambda *args: b'jpeg cover')
    status = AsyncMock()

    async def send(**kwargs):
        assert {'width': kwargs['width'], 'height': kwargs['height']} == expected[kwargs['video'].name]
        assert 'cover' in kwargs and 'thumbnail' in kwargs

    status.reply_video.side_effect = send
    task = bot.DownloadTask(user_id=1, url='url', status_message=status, user_name='user')
    if parts:
        first = video.with_name('job_part1.mp4')
        second = video.with_name('job_part2.mp4')
        first.write_bytes(b'part')
        second.write_bytes(b'part')
        expected = {str(first): {'width': 1080, 'height': 1920}}
        expected[str(second)] = {'width': 1920, 'height': 1080}
        monkeypatch.setattr(bot, 'split_video', lambda *args: list(expected))
        await bot._send_large_video(task, str(video))
        assert not first.exists() and not second.exists()
    else:
        await bot._send_single_video(task, str(video))
    assert probed == list(expected)
    assert video.exists()


@pytest.mark.asyncio
async def test_upload_continues_without_dimensions(video, monkeypatch):
    monkeypatch.setattr(bot, 'get_video_dimensions', lambda *args: {}, raising=False)
    monkeypatch.setattr(bot, 'create_video_preview', lambda *args: None)
    status = AsyncMock()
    task = bot.DownloadTask(user_id=1, url='url', status_message=status, user_name='user')
    await bot._send_single_video(task, str(video))
    assert set(status.reply_video.call_args.kwargs) == {'video'}


@pytest.mark.asyncio
async def test_cancellation_waits_for_probe_before_cleanup(video, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    part = video.with_name('job_part1.mp4')
    part.write_bytes(b'part')

    def dimensions(path):
        entered.set()
        assert release.wait(3)
        assert part.exists(), 'source must remain available to ffprobe'
        return {'width': 1080, 'height': 1920}

    monkeypatch.setattr(bot, 'get_video_dimensions', dimensions, raising=False)
    monkeypatch.setattr(bot, 'create_video_preview', lambda *args: None)
    monkeypatch.setattr(bot, 'split_video', lambda *args: [str(part)])
    status = AsyncMock()
    task = bot.DownloadTask(user_id=1, url='url', status_message=status, user_name='user')
    pending = asyncio.create_task(bot._send_large_video(task, str(video)))
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
    assert not part.exists()
    assert video.exists()
