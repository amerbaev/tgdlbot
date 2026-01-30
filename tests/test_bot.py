"""Tests for Telegram Video Downloader Bot."""

import os
from unittest.mock import AsyncMock, MagicMock, Mock, mock_open, patch

import pytest

from telegram import Update

import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from bot import (
    start_command,
    help_command,
    download_command,
    handle_message,
    is_youtube_url,
    is_instagram_url,
    detect_platform,
    download_video_sync,
    split_video,
    DownloadTask,
    format_size,
    cleanup_download,
    _get_platform_handler,
    _find_downloaded_file,
    _calculate_parts,
    _cleanup_parts,
    _get_video_duration,
    _send_download_error,
    _send_video_parts,
    _send_single_video,
    _send_large_video,
    _process_download_success,
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
    update.message.chat = Mock()
    update.message.chat.type = 'private'  # По умолчанию личный чат
    update.effective_user = Mock()
    update.effective_user.id = 123
    update.effective_user.username = 'testuser'
    update.effective_user.first_name = 'Test'
    return update


@pytest.fixture
def mock_context():
    """Mock Context object."""
    context = Mock()
    context.bot = Mock()
    context.bot.id = 1  # bot user ID
    context.bot.username = 'tgdlbot'
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

    @pytest.mark.asyncio
    async def test_download_command_no_args(self, mock_update, mock_context):
        """Test /download command without arguments."""
        mock_context.args = []

        await download_command(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        message = call_args[0][0]

        assert 'Укажите ссылку' in message

    @pytest.mark.asyncio
    async def test_download_command_with_url(self, mock_update, mock_context, clean_active_downloads):
        """Test /download command with URL."""
        mock_context.args = ['https://www.youtube.com/watch?v=dQw4w9WgXcQ']
        mock_update.message.reply_text = AsyncMock()  # Reset mock

        await download_command(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()


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

    @pytest.mark.asyncio
    async def test_group_ignores_without_mention(self, mock_update, mock_context, clean_active_downloads):
        """Test that group messages without bot mention are ignored."""
        mock_update.message.chat.type = 'supergroup'
        mock_update.message.text = 'https://www.youtube.com/watch?v=dQw4w9WggXcQ'
        mock_update.message.reply_to_message = None

        await handle_message(mock_update, mock_context)

        # Не должен отвечать на сообщения без упоминания в группах
        mock_update.message.reply_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_group_with_mention(self, mock_update, mock_context, clean_active_downloads):
        """Test that group messages with bot mention are processed."""
        mock_update.message.chat.type = 'supergroup'
        mock_update.message.text = '@tgdlbot https://www.youtube.com/watch?v=dQw4w9WgXcQ'
        mock_update.message.reply_to_message = None

        await handle_message(mock_update, mock_context)

        # Должен ответить на сообщение с упоминанием
        mock_update.message.reply_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_group_with_reply_to_bot(self, mock_update, mock_context, clean_active_downloads):
        """Test that replies to bot messages are processed."""
        mock_update.message.chat.type = 'supergroup'
        mock_update.message.text = 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'

        # Mock reply_to_message
        reply_msg = Mock()
        reply_msg.from_user.id = 1  # bot ID
        mock_update.message.reply_to_message = reply_msg

        await handle_message(mock_update, mock_context)

        # Должен ответить на reply
        mock_update.message.reply_text.assert_called_once()


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
            user_name='@testuser',
        )

        assert task.user_id == 123
        assert task.chat_id == 456
        assert task.url == test_url
        assert task.video_path is None
        assert task.user_name == '@testuser'
        assert task.download_id is None


class TestConfig:
    """Tests for configuration."""

    def test_values(self):
        """Test config values."""
        assert MAX_FILE_SIZE == 50 * 1024 * 1024
        assert DOWNLOAD_DIR == 'downloads'


class TestGetPlatformHandler:
    """Tests for _get_platform_handler function."""

    def test_youtube_platform(self):
        """Test YouTube platform detection."""
        handler = _get_platform_handler('https://www.youtube.com/watch?v=test')
        assert handler is not None
        assert handler.name == 'youtube'

    def test_instagram_platform(self):
        """Test Instagram platform detection."""
        handler = _get_platform_handler('https://instagram.com/p/ABC/')
        assert handler is not None
        assert handler.name == 'instagram'

    def test_unknown_platform(self):
        """Test unknown platform returns None."""
        handler = _get_platform_handler('https://google.com')
        assert handler is None


class TestFindDownloadedFile:
    """Tests for _find_downloaded_file function."""

    @patch('os.listdir')
    @patch('os.path.getmtime')
    def test_finds_newest_file(self, mock_getmtime, mock_listdir):
        """Test finding the newest downloaded file."""
        download_id = 'abc123'
        mock_listdir.return_value = [
            f'{download_id}_old.mp4',
            f'{download_id}_new.mp4',
            'other.mp4',
        ]

        # Mock different modification times
        mock_getmtime.side_effect = [1000, 2000]

        with patch('bot.os.path.join', side_effect=lambda *args: '/'.join(args)):
            result = _find_downloaded_file(download_id)

        assert result is not None
        assert 'new.mp4' in result

    @patch('os.listdir')
    def test_returns_none_when_no_match(self, mock_listdir):
        """Test returning None when no matching files."""
        mock_listdir.return_value = ['other.mp4', 'different.mp4']

        result = _find_downloaded_file('abc123')

        assert result is None


class TestCalculateParts:
    """Tests for _calculate_parts function."""

    def test_small_file(self):
        """Test calculation for small file."""
        # 10MB file, 100s duration
        num_parts, part_duration = _calculate_parts(10 * 1024 * 1024, 100)

        assert num_parts == 1
        assert part_duration == 100.0

    def test_large_file(self):
        """Test calculation for large file."""
        # 100MB file, 300s duration
        num_parts, part_duration = _calculate_parts(100 * 1024 * 1024, 300)

        # Target size is 45MB, so should be 3 parts
        assert num_parts == 3
        assert part_duration == 100.0

    def test_very_large_file(self):
        """Test calculation for very large file."""
        # 200MB file, 600s duration
        num_parts, part_duration = _calculate_parts(200 * 1024 * 1024, 600)

        # Should be 5 parts (200/45 + 1)
        assert num_parts == 5
        assert part_duration == 120.0


class TestCleanupParts:
    """Tests for _cleanup_parts function."""

    @patch('os.remove')
    @patch('os.path.exists')
    def test_removes_existing_parts(self, mock_exists, mock_remove):
        """Test removing existing parts."""
        mock_exists.return_value = True
        parts = ['downloads/part1.mp4', 'downloads/part2.mp4']

        _cleanup_parts(parts)

        assert mock_remove.call_count == 2

    @patch('os.remove')
    @patch('os.path.exists')
    def test_skips_missing_parts(self, mock_exists, mock_remove):
        """Test skipping missing parts."""
        mock_exists.return_value = False
        parts = ['downloads/part1.mp4', 'downloads/part2.mp4']

        _cleanup_parts(parts)

        mock_remove.assert_not_called()


class TestGetVideoDuration:
    """Tests for _get_video_duration function."""

    @patch('subprocess.run')
    def test_success(self, mock_run):
        """Test successful duration retrieval."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout.strip.return_value = '150.5'
        mock_run.return_value = mock_result

        duration = _get_video_duration('test.mp4')

        assert duration == 150.5

    @patch('subprocess.run')
    def test_ffprobe_error(self, mock_run):
        """Test ffprobe error handling."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = b'Error'
        mock_run.return_value = mock_result

        duration = _get_video_duration('test.mp4')

        assert duration is None

    @patch('subprocess.run')
    def test_parse_error(self, mock_run):
        """Test parsing error handling."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout.strip.return_value = 'invalid'
        mock_run.return_value = mock_result

        duration = _get_video_duration('test.mp4')

        assert duration is None


class TestSendDownloadError:
    """Tests for _send_download_error function."""

    @pytest.mark.asyncio
    async def test_sends_error_message(self):
        """Test sending error message to user."""
        mock_status = AsyncMock()

        await _send_download_error(mock_status)

        mock_status.edit_text.assert_called_once()
        call_args = mock_status.edit_text.call_args[0][0]
        assert 'Не удалось скачать видео' in call_args
        assert 'Возможные причины' in call_args


class TestSendVideoParts:
    """Tests for _send_video_parts function."""

    @pytest.mark.asyncio
    @patch('bot.os.remove')
    @patch('bot.os.path.getsize')
    @patch('builtins.open', new_callable=mock_open, read_data=b'fake video')
    async def test_sends_all_parts(self, mock_file_open, mock_getsize, mock_remove):
        """Test sending all video parts."""
        mock_status = AsyncMock()
        parts = ['downloads/part1.mp4', 'downloads/part2.mp4']
        mock_getsize.side_effect = [45 * 1024 * 1024, 45 * 1024 * 1024]

        await _send_video_parts(mock_status, parts)

        assert mock_status.reply_video.call_count == 2
        assert mock_remove.call_count == 2

    @pytest.mark.asyncio
    @patch('bot.os.remove')
    @patch('bot.os.path.getsize')
    @patch('builtins.open', new_callable=mock_open, read_data=b'fake video')
    async def test_sends_without_captions(self, mock_file_open, mock_getsize, mock_remove):
        """Test that parts are sent without captions."""
        mock_status = AsyncMock()
        parts = ['downloads/part1.mp4', 'downloads/part2.mp4']
        mock_getsize.side_effect = [45 * 1024 * 1024, 45 * 1024 * 1024]

        await _send_video_parts(mock_status, parts)

        # Check first call has no caption
        first_call = mock_status.reply_video.call_args_list[0]
        assert 'caption' not in first_call[1] or first_call[1].get('caption') is None


class TestSendSingleVideo:
    """Tests for _send_single_video function."""

    @pytest.mark.asyncio
    @patch('bot.os.remove')
    @patch('bot.os.path.getsize')
    @patch('builtins.open', new_callable=mock_open, read_data=b'fake video')
    async def test_sends_video(self, mock_file_open, mock_getsize, mock_remove):
        """Test sending single video."""
        mock_getsize.return_value = 10 * 1024 * 1024
        mock_status = AsyncMock()

        task = DownloadTask(
            user_id=123,
            chat_id=456,
            message_id=1,
            url='https://youtube.com/watch?v=test',
            status_message=mock_status,
            user_name='@testuser',
        )

        await _send_single_video(task, 'test.mp4')

        mock_status.edit_text.assert_called()
        mock_status.reply_video.assert_called_once()
        mock_status.delete.assert_called_once()
        mock_remove.assert_called_once_with('test.mp4')

    @pytest.mark.asyncio
    @patch('bot.os.remove')
    @patch('bot.os.path.getsize')
    @patch('builtins.open', new_callable=mock_open, read_data=b'fake video')
    async def test_sends_without_caption(self, mock_file_open, mock_getsize, mock_remove):
        """Test that video is sent without caption."""
        mock_getsize.return_value = 25 * 1024 * 1024
        mock_status = AsyncMock()

        task = DownloadTask(
            user_id=123,
            chat_id=456,
            message_id=1,
            url='https://youtube.com/watch?v=test',
            status_message=mock_status,
            user_name='@testuser',
        )

        await _send_single_video(task, 'test.mp4')

        call_args = mock_status.reply_video.call_args
        # Check that caption is not in kwargs
        assert 'caption' not in call_args[1] or call_args[1].get('caption') is None


class TestSendLargeVideo:
    """Tests for _send_large_video function."""

    @pytest.mark.asyncio
    @patch('bot.split_video')
    @patch('bot.os.remove')
    @patch('bot.os.path.getsize')
    async def test_success(self, mock_getsize, _mock_remove, mock_split):
        """Test successful large video sending."""
        mock_getsize.return_value = 100 * 1024 * 1024
        mock_split.return_value = ['downloads/part1.mp4', 'downloads/part2.mp4']
        mock_status = AsyncMock()

        task = DownloadTask(
            user_id=123,
            chat_id=456,
            message_id=1,
            url='https://youtube.com/watch?v=test',
            status_message=mock_status,
            user_name='@testuser',
        )

        with patch('bot._send_video_parts'):
            result = await _send_large_video(task, 'test.mp4')

        assert result is True
        mock_status.edit_text.assert_called()

    @pytest.mark.asyncio
    @patch('bot.split_video')
    @patch('bot.cleanup_download')
    @patch('bot.os.path.getsize')
    async def test_split_failure(self, mock_getsize, mock_cleanup, mock_split):
        """Test handling split failure."""
        mock_getsize.return_value = 100 * 1024 * 1024
        mock_split.return_value = []
        mock_status = AsyncMock()

        task = DownloadTask(
            user_id=123,
            chat_id=456,
            message_id=1,
            url='https://youtube.com/watch?v=test',
            status_message=mock_status,
            user_name='@testuser',
        )

        result = await _send_large_video(task, 'test.mp4')

        assert result is False
        mock_cleanup.assert_called_once()


class TestProcessDownloadSuccess:
    """Tests for _process_download_success function."""

    @pytest.mark.asyncio
    @patch('bot._send_single_video')
    @patch('bot.cleanup_download')
    @patch('os.path.getsize')
    async def test_small_video(self, mock_getsize, mock_cleanup, mock_send):
        """Test processing small video."""
        mock_getsize.return_value = 10 * 1024 * 1024
        mock_status = AsyncMock()

        task = DownloadTask(
            user_id=123,
            chat_id=456,
            message_id=1,
            url='https://youtube.com/watch?v=test',
            status_message=mock_status,
            user_name='@testuser',
        )

        await _process_download_success(task, 'test.mp4')

        mock_send.assert_called_once_with(task, 'test.mp4')
        mock_cleanup.assert_called_once_with(123)

    @pytest.mark.asyncio
    @patch('bot._send_large_video')
    @patch('bot.cleanup_download')
    @patch('os.path.getsize')
    async def test_large_video(self, mock_getsize, mock_cleanup, mock_send):
        """Test processing large video."""
        mock_getsize.return_value = 100 * 1024 * 1024
        mock_send.return_value = True
        mock_status = AsyncMock()

        task = DownloadTask(
            user_id=123,
            chat_id=456,
            message_id=1,
            url='https://youtube.com/watch?v=test',
            status_message=mock_status,
            user_name='@testuser',
        )

        await _process_download_success(task, 'test.mp4')

        mock_send.assert_called_once_with(task, 'test.mp4')
        mock_cleanup.assert_called_once_with(123)

    @pytest.mark.asyncio
    @patch('bot._send_large_video')
    @patch('os.path.getsize')
    async def test_large_video_failure(self, mock_getsize, mock_send):
        """Test handling large video send failure."""
        mock_getsize.return_value = 100 * 1024 * 1024
        mock_send.return_value = False
        mock_status = AsyncMock()

        task = DownloadTask(
            user_id=123,
            chat_id=456,
            message_id=1,
            url='https://youtube.com/watch?v=test',
            status_message=mock_status,
            user_name='@testuser',
        )

        await _process_download_success(task, 'test.mp4')

        # Should not cleanup on failure (cleanup happens inside _send_large_video)
        mock_send.assert_called_once()
