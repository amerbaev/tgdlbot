"""Instagram authentication through the real yt-dlp cookie boundary."""

import logging
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import yt_dlp

import bot


REEL_URL = 'https://www.instagram.com/reel/DdRPqmyM-cS/'


@pytest.fixture
def cookie_file(tmp_path, monkeypatch):
    path = tmp_path / 'instagram.txt'
    path.write_text(
        '# Netscape HTTP Cookie File\n'
        '.instagram.com\tTRUE\t/\tTRUE\t2147483647\tsessionid\ttest-session\n',
        encoding='utf-8',
    )
    monkeypatch.setattr(bot, 'INSTAGRAM_COOKIES_FILE', str(path), raising=False)
    return path


@pytest.mark.parametrize('require_auth_during', ['analysis', 'download'])
def test_instagram_cookies_reach_analysis_and_download(
    cookie_file, tmp_path, monkeypatch, require_auth_during,
):
    """Removing cookies from either stage must break an authenticated download."""
    original = cookie_file.read_bytes()
    monkeypatch.setattr(bot, 'DOWNLOAD_DIR', str(tmp_path))
    stages = []

    def extract_info(ydl, url, download=True, **kwargs):
        stage = 'download' if download else 'analysis'
        stages.append(stage)
        cookies = ydl.cookiejar.get_cookie_header(REEL_URL) or ''
        if stage == require_auth_during and 'sessionid=test-session' not in cookies:
            raise yt_dlp.utils.DownloadError('Instagram sent an empty media response')
        info = {'id': 'test', 'title': 'reel', 'ext': 'mp4'}
        if download:
            Path(ydl.prepare_filename(info)).write_bytes(b'video')
        return info

    # Keep YoutubeDL construction, cookie loading/saving and download orchestration real.
    monkeypatch.setattr(yt_dlp.YoutubeDL, 'extract_info', extract_info)

    result = bot.download_video_sync(REEL_URL)

    assert result is not None
    assert Path(result).read_bytes() == b'video'
    assert {'analysis', 'download'} <= set(stages)
    # A read-only Docker mount must work; concurrent jobs must not rewrite this file.
    assert cookie_file.read_bytes() == original


@pytest.mark.parametrize('url', [REEL_URL, 'https://www.youtube.com/watch?v=test'])
def test_anonymous_downloads_do_not_require_instagram_cookies(tmp_path, monkeypatch, url):
    monkeypatch.setattr(bot, 'DOWNLOAD_DIR', str(tmp_path))
    # YouTube must not even open an Instagram cookie file.
    cookie_path = '' if 'instagram.com' in url else str(tmp_path / 'missing.txt')
    monkeypatch.setattr(bot, 'INSTAGRAM_COOKIES_FILE', cookie_path, raising=False)

    def extract_info(ydl, url, download=True, **kwargs):
        assert not ydl.cookiejar.get_cookie_header(REEL_URL)
        info = {'id': 'test', 'title': 'public', 'ext': 'mp4', 'formats': []}
        if download:
            Path(ydl.prepare_filename(info)).write_bytes(b'public video')
        return info

    monkeypatch.setattr(yt_dlp.YoutubeDL, 'extract_info', extract_info)
    assert bot.download_video_sync(url) is not None


def test_missing_instagram_cookie_file_fails_before_network(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(
        bot, 'INSTAGRAM_COOKIES_FILE', str(tmp_path / 'missing.txt'), raising=False,
    )
    requests = []

    def extract_info(*args, **kwargs):
        requests.append(True)
        raise yt_dlp.utils.DownloadError('unexpected anonymous request')

    monkeypatch.setattr(yt_dlp.YoutubeDL, 'extract_info', extract_info)
    with caplog.at_level(logging.ERROR, logger='bot'):
        assert bot.download_video_sync(REEL_URL) is None
    assert requests == []
    assert 'missing.txt' in caplog.text


@pytest.mark.asyncio
async def test_instagram_failure_explains_access_and_cleans_up(monkeypatch):
    status = AsyncMock()
    task = bot.DownloadTask(98765, 123, 1, REEL_URL, status, '@tester')
    bot.active_downloads[task.user_id] = {'url': REEL_URL}
    monkeypatch.setattr(bot, 'download_video_sync', lambda url: None)

    await bot.process_download(task)

    message = status.edit_text.call_args.args[0]
    assert 'Instagram' in message
    assert 'вход' in message.lower()
    assert 'YouTube' not in message
    assert task.user_id not in bot.active_downloads
