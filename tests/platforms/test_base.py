"""Shared URL validation requirements for supported platforms."""

import pytest

from platforms.instagram import InstagramPlatform
from platforms.youtube import YouTubePlatform


@pytest.mark.parametrize(('platform', 'url'), [
    (YouTubePlatform(), 'https://youtube.com/watch?v=test'),
    (InstagramPlatform(), 'https://instagram.com/reel/test'),
])
@pytest.mark.parametrize('suffix', [' ', '\n', '\t', '\x00', '\x1f', '\x7f', '\\extra'])
def test_rejects_whitespace_controls_and_backslashes(platform, url, suffix):
    assert not platform.is_valid_url(url + suffix)
