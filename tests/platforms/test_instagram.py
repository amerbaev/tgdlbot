"""Tests for Instagram platform handler."""

import pytest
from platforms.instagram import InstagramPlatform


class TestInstagramPlatform:
    """Tests for InstagramPlatform class."""

    def test_name(self):
        """Test platform name."""
        platform = InstagramPlatform()
        assert platform.name == 'instagram'

    def test_url_validation(self):
        """Test URL validation."""
        platform = InstagramPlatform()

        valid_urls = [
            'https://www.instagram.com/p/ABC123/',
            'http://instagram.com/p/ABC123/',
            'https://instagram.com/reel/ABC123/',
            'http://www.instagram.com/reel/ABC123/',
            'instagram.com/p/ABC123/',
            'instagram.com/reel/ABC123/',
            'https://www.instagram.com/p/ABC123?utm_source=share',
        ]

        for url in valid_urls:
            assert platform.is_valid_url(url), f'{url} should be valid'

        invalid_urls = [
            'https://www.youtube.com/watch?v=123',
            'not a url',
            'https://vimeo.com/123456789',
            '',
            'https://facebook.com/watch?v=123',
            'https://instagram.com/stories/username/123/',  # Stories not supported
            'https://instagram.com/',  # Just domain
        ]

        for url in invalid_urls:
            assert not platform.is_valid_url(url), f'{url} should be invalid'

    @pytest.mark.parametrize('url', [
        'https://instagram.com/p/?utm_source=share',
        'https://instagram.com/reel/?utm_source=share',
        'https://instagram.com/p/ABC123/extra',
        'https://instagram.com/reel/ABC123/extra',
        'https://instagram.com/p/ABC%2F123',
        'https://instagram.com.evil.example/p/ABC123',
        'https://instagram.com@evil.example/p/ABC123',
        'https://user@instagram.com/p/ABC123',
    ])
    def test_rejects_invalid_post_urls(self, url):
        assert not InstagramPlatform().is_valid_url(url)

    def test_get_format_options(self):
        """Test format options for Instagram."""
        platform = InstagramPlatform()
        info = {'formats': []}

        result = platform.get_format_options(info)

        assert isinstance(result, list)
        assert len(result) == 1
        format_selector, extractor_args = result[0]
        assert 'best' in format_selector
        assert extractor_args is None
