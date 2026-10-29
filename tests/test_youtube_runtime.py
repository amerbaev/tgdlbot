"""Check the bot's real yt-dlp/runtime boundary without contacting a video site."""

import importlib.util
from importlib.metadata import requires, version

import pytest
import yt_dlp
from packaging.requirements import Requirement
from yt_dlp.extractor.youtube import YoutubeIE

import bot


@pytest.mark.parametrize('url', [
    'https://www.youtube.com/watch?v=test',
    'https://www.instagram.com/reel/test/',
])
def test_extractor_warnings_are_visible(url, capsys, monkeypatch):
    monkeypatch.setattr(bot, 'INSTAGRAM_COOKIES_FILE', '')
    with yt_dlp.YoutubeDL(bot._get_ytdlp_options(url)) as ydl:
        ydl.report_warning('extractor diagnostic probe')
    assert 'extractor diagnostic probe' in capsys.readouterr().err


def test_youtube_can_use_the_installed_deno_runtime():
    with yt_dlp.YoutubeDL(bot._get_ytdlp_options('https://www.youtube.com/watch?v=test')) as ydl:
        extractor = YoutubeIE(ydl)
        extractor.initialize()
        deno = extractor._jsc_director.providers['Deno']
        assert deno.is_available(), 'The project environment must include a usable Deno runtime'


def test_installed_ejs_matches_the_downloader_requirement():
    assert importlib.util.find_spec('yt_dlp_ejs'), 'YouTube challenge solver is missing'
    requirement = next(Requirement(r) for r in requires('yt-dlp') if r.startswith('yt-dlp-ejs'))
    assert version('yt-dlp-ejs') in requirement.specifier
