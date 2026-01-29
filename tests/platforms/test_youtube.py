"""Tests for YouTube platform handler."""

import pytest
from platforms.youtube import (
    YouTubePlatform,
    select_best_format,
    estimate_format_size,
    should_skip_format,
)


class TestYouTubePlatform:
    """Tests for YouTubePlatform class."""

    def test_name(self):
        """Test platform name."""
        platform = YouTubePlatform()
        assert platform.name == 'youtube'

    def test_url_validation(self):
        """Test URL validation."""
        platform = YouTubePlatform()

        valid_urls = [
            'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
            'http://youtube.com/watch?v=dQw4w9WgXcQ',
            'https://youtu.be/dQw4w9WgXcQ',
            'http://youtu.be/dQw4w9WgXcQ',
            'https://www.youtube.com/watch?v=dQw4w9WgXcQ&feature=share',
            'https://www.youtube.com/shorts/dQw4w9WgXcQ',
            'youtube.com/watch?v=dQw4w9WgXcQ',
            'youtu.be/dQw4w9WgXcQ',
        ]

        for url in valid_urls:
            assert platform.is_valid_url(url), f'{url} should be valid'

        invalid_urls = [
            'https://www.google.com',
            'not a url',
            'https://vimeo.com/123456789',
            '',
            'https://facebook.com/watch?v=123',
            'https://instagram.com/p/ABC123/',
        ]

        for url in invalid_urls:
            assert not platform.is_valid_url(url), f'{url} should be invalid'


class TestEstimateFormatSize:
    """Tests for format size estimation."""

    def test_known_filesize(self):
        """Test estimation when filesize is known."""
        info = {
            'formats': [
                {'format_id': '137', 'height': 1080, 'filesize': 100 * 1024 * 1024, 'vcodec': 'avc1'},
            ]
        }

        result = estimate_format_size(info, 1080)
        assert result == 100 * 1024 * 1024

    def test_unknown_size(self):
        """Test when size is unknown."""
        info = {
            'formats': [
                {'format_id': '137', 'height': 1080, 'vcodec': 'avc1'},
            ]
        }

        result = estimate_format_size(info, 1080)
        assert result is None

    def test_finds_closest_height(self):
        """Test finding closest resolution."""
        info = {
            'formats': [
                {'format_id': '136', 'height': 720, 'filesize': 50 * 1024 * 1024, 'vcodec': 'avc1'},
            ]
        }

        result = estimate_format_size(info, 715)  # Close to 720
        assert result == 50 * 1024 * 1024


class TestSelectBestFormat:
    """Tests for format selection."""

    def test_returns_list(self):
        """Test that select_best_format returns a list."""
        info = {'formats': []}

        result = select_best_format(info)

        assert isinstance(result, list)
        assert len(result) > 0
        assert all(isinstance(item, tuple) and len(item) == 2 for item in result)

    def test_uses_mediaconnect(self):
        """Test that mediaconnect client is used."""
        info = {'formats': []}

        result = select_best_format(info)

        format_selector, extractor_args = result[0]
        assert 'mediaconnect' in extractor_args.get('youtube', {}).get('player_client', '')

    def test_skips_oversized_1080p(self):
        """Test that 1080p is skipped if too large."""
        info = {
            'formats': [
                {'format_id': '137', 'height': 1080, 'filesize': 80 * 1024 * 1024, 'vcodec': 'avc1'},
                {'format_id': '136', 'height': 720, 'filesize': 30 * 1024 * 1024, 'vcodec': 'avc1'},
            ]
        }

        result = select_best_format(info)

        # Should start with 720p, not 1080p
        first_selector = result[0][0]
        assert 'height<=720' in first_selector or 'height<=1080' not in first_selector

    def test_includes_all_if_small(self):
        """Test that all formats are included if small enough."""
        info = {
            'formats': [
                {'format_id': '137', 'height': 1080, 'filesize': 20 * 1024 * 1024, 'vcodec': 'avc1'},
                {'format_id': '136', 'height': 720, 'filesize': 15 * 1024 * 1024, 'vcodec': 'avc1'},
            ]
        }

        result = select_best_format(info)

        # Should include 1080p
        assert len(result) >= 3
        first_selector = result[0][0]
        assert 'height<=1080' in first_selector
