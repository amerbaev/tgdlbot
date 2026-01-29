"""Tests for Telegram Video Downloader Bot."""

import os
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from telegram import Update

import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from bot import (
    start_command,
    help_command,
    handle_message,
    is_youtube_url,
    is_instagram_url,
    detect_platform,
    download_video_sync,
    split_video,
    DownloadTask,
    format_size,
    cleanup_download,
)
from config import MAX_FILE_SIZE, DOWNLOAD_DIR


@pytest.fixture
def mock_update():
    """Mock Update object."""
    update = Mock(spec=Update)
    update.message = Mock()
    update.message.reply_text = AsyncMock()
    update.message.edit_text = AsyncMock()
    update.message.delete = AsyncMock()
    update.message.reply_video = AsyncMock()
    update.message.text = ''
    update.message.chat_id = 123456
    update.message.message_id = 1
    update.effective_user = Mock()
    update.effective_user.id = 123
    return update


@pytest.fixture
def mock_context():
    """Mock Context object."""
    context = Mock()
    return context


@pytest.fixture
def clean_active_downloads():
    """Clear active downloads before/after each test."""
    from bot import active_downloads
    active_downloads.clear()
    yield
    active_downloads.clear()


class TestFormatSize:
    """Tests for format_size function."""

    def test_format_mb(self):
        """Test formatting bytes to MB."""
        assert format_size(1024 * 1024) == '1.0MB'
        assert format_size(50 * 1024 * 1024) == '50.0MB'
        assert format_size(25 * 1024 * 1024) == '25.0MB'


class TestURLValidation:
    """Tests for URL validation functions in bot.py."""

    def test_is_youtube_url(self):
        """Test YouTube URL validation."""
        valid_urls = [
            'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
            'https://youtu.be/dQw4w9WgXcQ',
            'https://www.youtube.com/shorts/dQw4w9WgXcQ',
        ]

        for url in valid_urls:
            assert is_youtube_url(url), f'{url} should be valid'

    def test_is_instagram_url(self):
        """Test Instagram URL validation."""
        valid_urls = [
            'https://www.instagram.com/p/ABC123/',
            'https://instagram.com/reel/ABC123/',
        ]

        for url in valid_urls:
            assert is_instagram_url(url), f'{url} should be valid'

    def test_detect_platform(self):
        """Test platform detection."""
        assert detect_platform('https://www.youtube.com/watch?v=test') == 'youtube'
        assert detect_platform('https://instagram.com/p/ABC/') == 'instagram'
        assert detect_platform('https://google.com') is None


class TestDownloadVideoSync:
    """Tests for video downloading."""

    @pytest.mark.asyncio
    @patch('bot.yt_dlp.YoutubeDL')
    @patch('os.path.exists')
    @patch('os.listdir')
    async def test_success(self, mock_listdir, mock_exists, mock_ydl_class):
        """Test successful download."""
        mock_ydl = MagicMock()
        mock_ydl_class.return_value.__enter__.return_value = mock_ydl

        mock_info = {
            'title': 'Test Video',
            'formats': [{'format_id': '137', 'height': 1080, 'ext': 'mp4', 'vcodec': 'avc1'}],
        }
        mock_ydl.extract_info.return_value = mock_info
        mock_ydl.prepare_filename.return_value = 'downloads/test_video.mp4'
        mock_ydl.download.return_value = None

        mock_exists.return_value = True
        mock_listdir.return_value = ['test_video.mp4']

        with patch('os.path.getsize', return_value=10 * 1024 * 1024):
            result = download_video_sync('https://www.youtube.com/watch?v=test')

        assert result is not None
        mock_ydl.download.assert_called()

    @pytest.mark.asyncio
    @patch('bot.yt_dlp.YoutubeDL')
    @patch('platforms.youtube.YouTubePlatform.get_format_options')
    async def test_no_formats(self, mock_get_formats, mock_ydl_class):
        """Test when no suitable format found."""
        mock_ydl = MagicMock()
        mock_ydl_class.return_value.__enter__.return_value = mock_ydl
        mock_ydl.extract_info.return_value = {'formats': []}
        mock_get_formats.return_value = []  # No formats available

        result = download_video_sync('https://www.youtube.com/watch?v=test')

        assert result is None


class TestSplitVideo:
    """Tests for video splitting."""

    @patch('subprocess.run')
    @patch('os.path.getsize')
    @patch('os.remove')
    @patch('os.path.exists')
    def test_success(self, mock_exists, mock_remove, mock_getsize, mock_subprocess):
        """Test successful split with size check."""
        def getsize_side_effect(path):
            if '_part' in path:
                return 45 * 1024 * 1024
            return 100 * 1024 * 1024

        mock_getsize.side_effect = getsize_side_effect
        mock_exists.return_value = True

        mock_duration_result = MagicMock()
        mock_duration_result.returncode = 0
        mock_duration_result.stdout.strip.return_value = '300.0'

        mock_split_result = MagicMock()
        mock_split_result.returncode = 0

        def side_effect(cmd, *args, **kwargs):
            if 'ffprobe' in str(cmd):
                return mock_duration_result
            return mock_split_result

        mock_subprocess.side_effect = side_effect

        test_file = 'downloads/test_video.mp4'
        parts = split_video(test_file)

        assert isinstance(parts, list)
        assert len(parts) == 3

    @patch('subprocess.run')
    @patch('os.path.getsize')
    @patch('os.remove')
    @patch('os.path.exists')
    def test_retry_on_oversize(self, mock_exists, mock_remove, mock_getsize, mock_subprocess):
        """Test retry mechanism when part exceeds limit."""
        call_count = [0]

        def getsize_side_effect(path):
            if '_part' in path:
                call_count[0] += 1
                if call_count[0] <= 2:
                    return 55 * 1024 * 1024
                return 40 * 1024 * 1024
            return 100 * 1024 * 1024

        mock_getsize.side_effect = getsize_side_effect
        mock_exists.return_value = True
        mock_remove.return_value = None

        mock_duration_result = MagicMock()
        mock_duration_result.returncode = 0
        mock_duration_result.stdout.strip.return_value = '300.0'

        mock_split_result = MagicMock()
        mock_split_result.returncode = 0

        def side_effect(cmd, *args, **kwargs):
            if 'ffprobe' in str(cmd):
                return mock_duration_result
            return mock_split_result

        mock_subprocess.side_effect = side_effect

        test_file = 'downloads/test_video.mp4'
        parts = split_video(test_file)

        assert isinstance(parts, list)


class TestCleanupDownload:
    """Tests for cleanup function."""

    @patch('os.remove')
    @patch('os.path.exists')
    def test_cleanup_with_file(self, mock_exists, mock_remove):
        """Test cleanup with video file."""
        from bot import active_downloads
        active_downloads[123] = {'status': 'downloading'}

        mock_exists.return_value = True

        cleanup_download(123, 'downloads/test.mp4')

        assert 123 not in active_downloads
        mock_remove.assert_called_once_with('downloads/test.mp4')

    @patch('os.remove')
    @patch('os.path.exists')
    def test_cleanup_without_file(self, mock_exists, mock_remove):
        """Test cleanup without video file."""
        from bot import active_downloads
        active_downloads[123] = {'status': 'downloading'}

        cleanup_download(123)

        assert 123 not in active_downloads
        mock_remove.assert_not_called()


class TestCommands:
    """Tests for bot commands."""

    @pytest.mark.asyncio
    async def test_start_command(self, mock_update, mock_context):
        """Test /start command."""
        await start_command(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()

        call_args = mock_update.message.reply_text.call_args
        message = call_args[0][0]

        assert 'Привет!' in message
        assert '/start' in message
        assert '/help' in message
        assert 'Instagram' in message

    @pytest.mark.asyncio
    async def test_help_command(self, mock_update, mock_context):
        """Test /help command."""
        await help_command(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()

        call_args = mock_update.message.reply_text.call_args
        message = call_args[0][0]

        assert 'Справка' in message
        assert 'youtube.com' in message
        assert 'instagram.com' in message


class TestHandleMessage:
    """Tests for message handling."""

    @pytest.mark.asyncio
    async def test_non_supported_url(self, mock_update, mock_context, clean_active_downloads):
        """Test handling invalid URL."""
        mock_update.message.text = 'https://www.google.com'

        await handle_message(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        message = call_args[0][0]

        assert 'Неверная ссылка' in message or 'не ссылка' in message

    @pytest.mark.asyncio
    async def test_empty_message(self, mock_update, mock_context, clean_active_downloads):
        """Test handling empty message."""
        mock_update.message.text = ''

        await handle_message(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_valid_youtube_url(self, mock_update, mock_context, clean_active_downloads):
        """Test handling valid YouTube URL."""
        mock_update.message.text = 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'

        await handle_message(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_valid_instagram_url(self, mock_update, mock_context, clean_active_downloads):
        """Test handling valid Instagram URL."""
        mock_update.message.text = 'https://www.instagram.com/p/ABC123/'

        await handle_message(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_duplicate_blocked(self, mock_update, mock_context, clean_active_downloads):
        """Test that duplicate downloads are blocked."""
        from bot import active_downloads

        mock_update.message.text = 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'
        mock_update.effective_user.id = 123

        active_downloads[123] = {'chat_id': 123456, 'status': 'downloading'}

        await handle_message(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        message = call_args[0][0]

        assert 'уже скачиваете' in message or 'Уже скачиваете' in message


class TestDownloadTask:
    """Tests for DownloadTask dataclass."""

    def test_creation(self):
        """Test DownloadTask creation."""
        test_url = 'https://example.com/watch?v=test'
        task = DownloadTask(
            user_id=123,
            chat_id=456,
            message_id=1,
            url=test_url,
            status_message=AsyncMock(),
        )

        assert task.user_id == 123
        assert task.chat_id == 456
        assert task.url == test_url
        assert task.video_path is None


class TestConfig:
    """Tests for configuration."""

    def test_values(self):
        """Test config values."""
        assert MAX_FILE_SIZE == 50 * 1024 * 1024
        assert DOWNLOAD_DIR == 'downloads'
