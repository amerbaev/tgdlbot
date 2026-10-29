"""Exercise portrait quality limits through yt-dlp's real format selection offline."""

from copy import deepcopy

import pytest
import yt_dlp

from platforms.youtube import estimate_format_size, select_best_format


@pytest.fixture
def shorts_info():
    formats = [{
        'format_id': 'audio', 'url': 'https://example.invalid/audio.m4a',
        'ext': 'm4a', 'vcodec': 'none', 'acodec': 'mp4a', 'filesize': 1024 * 1024,
    }]
    for width, height in [(360, 640), (480, 854), (720, 1280), (1080, 1920), (1440, 2560)]:
        formats.append({
            'format_id': str(width), 'url': f'https://example.invalid/{width}.mp4',
            'ext': 'mp4', 'width': width, 'height': height,
            'vcodec': 'avc1', 'acodec': 'none', 'filesize': 10 * 1024 * 1024,
        })
    return {'id': 'short', 'title': 'Short', 'extractor': 'youtube', 'formats': formats}


def selected_video(info, selector):
    with yt_dlp.YoutubeDL({'quiet': True, 'format': selector}) as ydl:
        result = ydl.process_ie_result(deepcopy(info), download=False)
    assert result['requested_formats'][1]['format_id'] == 'audio'
    return result['requested_formats'][0]


@pytest.mark.parametrize('quality', [1080, 720, 480, 360])
def test_estimates_portrait_size_by_shorter_side(shorts_info, quality):
    assert estimate_format_size(shorts_info, quality) == 11 * 1024 * 1024


@pytest.mark.parametrize('portrait', [True, False])
@pytest.mark.parametrize(('attempt', 'expected'), [(0, '1080'), (1, '720'), (2, '480')])
def test_quality_limits_select_matching_video_and_audio(shorts_info, portrait, attempt, expected):
    if not portrait:
        for fmt in shorts_info['formats'][1:]:
            fmt['width'], fmt['height'] = fmt['height'], fmt['width']

    options = select_best_format(shorts_info)
    assert len(options) == 4
    selector, _ = options[attempt]
    video = selected_video(shorts_info, selector)

    assert video['format_id'] == expected


@pytest.mark.parametrize('filesize', [None, 80 * 1024 * 1024])
def test_unknown_or_oversized_portrait_formats_fall_back_to_480(shorts_info, filesize):
    for fmt in shorts_info['formats'][1:]:
        if fmt['width'] >= 720:
            fmt['filesize'] = filesize

    selector, _ = select_best_format(shorts_info)[0]

    assert selected_video(shorts_info, selector)['format_id'] == '480'


def test_portrait_360_fallback_does_not_require_format_18(shorts_info):
    shorts_info['formats'] = shorts_info['formats'][:2]
    selector, _ = select_best_format(shorts_info)[-1]

    assert selected_video(shorts_info, selector)['format_id'] == '360'
