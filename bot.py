"""Telegram Video Downloader Bot.

Downloads videos from YouTube and Instagram in best quality
and sends them to Telegram, splitting large files into 50MB parts.
"""

import asyncio
import logging
import os
import uuid
from dataclasses import dataclass
from io import StringIO
from typing import Any, Callable, Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest, NetworkError
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from telegram.request import HTTPXRequest
import yt_dlp

from config import (
    BOT_TOKEN, DOWNLOAD_DIR, INSTAGRAM_COOKIES_FILE, MAX_FILE_SIZE,
    MAX_CONCURRENT_DOWNLOADS, MAX_DOWNLOAD_SIZE,
)
from media import format_size, is_safe_path, split_video, _cleanup_parts
from platforms import BasePlatform, YouTubePlatform, InstagramPlatform


# Platform handlers
youtube_platform = YouTubePlatform()
instagram_platform = InstagramPlatform()
PLATFORMS = [youtube_platform, instagram_platform]


# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
)
# HTTP request URLs contain the Telegram bot token.
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# Global state
active_downloads: dict[int, dict] = {}
background_tasks: set[asyncio.Task] = set()
cancelled_downloads: set[int] = set()  # IDs of cancelled downloads


@dataclass
class DownloadTask:
    """Информация о задаче на скачивание."""

    user_id: int
    chat_id: int
    message_id: int
    url: str
    status_message: Any
    user_name: str
    video_path: Optional[str] = None
    download_id: Optional[str] = None


def is_youtube_url(url: str) -> bool:
    """Проверка, является ли URL ссылкой на YouTube."""
    return youtube_platform.is_valid_url(url)


def is_instagram_url(url: str) -> bool:
    """Проверка, является ли URL ссылкой на Instagram."""
    return instagram_platform.is_valid_url(url)


def detect_platform(url: str) -> Optional[str]:
    handler = _get_platform_handler(url)
    return handler.name if handler else None


def _get_platform_handler(url: str) -> Optional[BasePlatform]:
    return next((platform for platform in PLATFORMS if platform.is_valid_url(url)), None)


def _check_download_progress(progress: dict, cancelled: Optional[Callable[[], bool]]) -> None:
    if cancelled and cancelled():
        raise yt_dlp.utils.DownloadCancelled('Загрузка отменена')
    if (progress.get('downloaded_bytes') or 0) > MAX_DOWNLOAD_SIZE:
        raise yt_dlp.utils.DownloadCancelled('Превышен лимит размера загрузки')


def _get_ytdlp_options(url: str, cancelled: Optional[Callable[[], bool]] = None) -> dict:
    """Общие настройки анализа и скачивания, включая сессию Instagram."""
    instagram = is_instagram_url(url)
    options = {
        'quiet': True, 'no_warnings': not instagram,
        'noplaylist': True, 'playlistend': 1,
        'socket_timeout': 30, 'retries': 3, 'fragment_retries': 3,
        'max_filesize': MAX_DOWNLOAD_SIZE,
        'progress_hooks': [lambda progress: _check_download_progress(progress, cancelled)],
    }
    if instagram and INSTAGRAM_COOKIES_FILE:
        # yt-dlp saves cookies on close. Give each instance a private in-memory
        # copy so read-only Docker mounts and parallel downloads are safe.
        with open(INSTAGRAM_COOKIES_FILE, encoding='utf-8') as cookie_file:
            options['cookiefile'] = StringIO(cookie_file.read())
    return options


def _get_video_info(url: str, platform_name: str, download_id: str) -> Optional[dict]:
    """Получает информацию о видео.

    Args:
        url: URL видео
        platform_name: Название платформы
        download_id: ID для логирования

    Returns:
        Информация о видео или None
    """
    try:
        info_opts = _get_ytdlp_options(url)
        with yt_dlp.YoutubeDL(info_opts) as ydl:
            logger.info(f'[Thread] [{download_id}] Анализ ({platform_name}): {url}')
            return ydl.extract_info(url, download=False)
    except Exception as e:
        logger.error(f'[Thread] [{download_id}] Ошибка получения информации: {e}')
        if platform_name == 'instagram' and 'empty media response' in str(e).lower():
            logger.warning(
                'Instagram не вернул данные видео. Проверьте доступность ролика '
                'в браузере и настройте или обновите INSTAGRAM_COOKIES_FILE.'
            )
        return None


def _cleanup_download_files(download_id: str, keep: Optional[str] = None) -> None:
    """Remove only files belonging to this job, including incomplete attempts."""
    try:
        paths = [
            os.path.join(DOWNLOAD_DIR, name)
            for name in os.listdir(DOWNLOAD_DIR)
            if name.startswith(f'{download_id}_')
        ]
        _cleanup_parts([path for path in paths if path != keep], base_dir=DOWNLOAD_DIR)
    except OSError as error:
        logger.warning('Не удалось очистить загрузку %s: %s', download_id, error)


def _try_download_format(
    url: str,
    download_id: str,
    format_selector: str,
    extractor_args: Optional[dict],
    attempt: int,
    total: int,
    cancelled: Optional[Callable[[], bool]] = None,
) -> Optional[str]:
    logger.info('[%s] Попытка %s/%s: %s', download_id, attempt, total, format_selector)
    try:
        options = _get_ytdlp_options(url, cancelled)
        options.update({
            'format': format_selector,
            # Neither remote titles nor IDs influence the local filename.
            'outtmpl': os.path.join(DOWNLOAD_DIR, f'{download_id}_{attempt}.%(ext)s'),
            'merge_output_format': 'mp4',
        })
        if extractor_args:
            options['extractor_args'] = extractor_args
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)
            if not info or info.get('_type') in ('playlist', 'multi_video'):
                return None
            filename = ydl.prepare_filename(info)
            # A merge may change the selected format's extension to mp4.
            for path in dict.fromkeys((os.path.splitext(filename)[0] + '.mp4', filename)):
                if is_safe_path(path, DOWNLOAD_DIR) and os.path.isfile(path):
                    size = os.path.getsize(path)
                    if 0 < size <= MAX_DOWNLOAD_SIZE:
                        return path
    except yt_dlp.utils.DownloadCancelled:
        raise
    except Exception as error:
        logger.warning('[%s] Формат %s не сработал: %s', download_id, format_selector, error)
    return None


def download_video_sync(
    url: str,
    download_id: Optional[str] = None,
    cancelled: Optional[Callable[[], bool]] = None,
) -> Optional[str]:
    """Download one video and remove artifacts from failed format attempts."""
    download_id = download_id or uuid.uuid4().hex
    platform = _get_platform_handler(url)
    if not platform:
        return None
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    result = None
    try:
        if cancelled and cancelled():
            return None
        info = _get_video_info(url, platform.name, download_id)
        if not info or info.get('is_live') or info.get('_type') in ('playlist', 'multi_video'):
            return None
        formats = platform.get_format_options(info)
        for attempt, (selector, extractor_args) in enumerate(formats, 1):
            if cancelled and cancelled():
                return None
            result = _try_download_format(
                url, download_id, selector, extractor_args, attempt, len(formats), cancelled,
            )
            if result:
                return result
            _cleanup_download_files(download_id)
        return None
    except yt_dlp.utils.DownloadCancelled:
        return None
    finally:
        _cleanup_download_files(download_id, keep=result)


def cleanup_download(
    user_id: int, video_path: Optional[str] = None, download_id: Optional[str] = None,
) -> None:
    """Release the user's slot and clean all files owned by the finished job."""
    state = active_downloads.pop(user_id, {})
    cancelled_downloads.discard(user_id)
    if video_path:
        _cleanup_parts([video_path], base_dir=DOWNLOAD_DIR)
    download_id = download_id or state.get('download_id')
    if download_id:
        _cleanup_download_files(download_id)


async def cancel_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    try:
        prefix, user, download_id = (query.data or '').split('_', 2)
        user_id = int(user)
    except (ValueError, AttributeError):
        await query.answer()
        return
    if prefix != 'cancel':
        await query.answer()
        return
    if query.from_user.id != user_id:
        await query.answer('Это не ваша загрузка!', show_alert=True)
        return
    state = active_downloads.get(user_id)
    if not state or state.get('download_id') != download_id:
        await query.answer('Эта загрузка уже завершена.')
        return
    cancelled_downloads.add(user_id)
    await query.answer()
    try:
        await query.edit_message_text('❌ Загрузка отменена')
    except Exception as error:
        logger.warning('Не удалось обновить сообщение отмены: %s', error)


async def _send_download_error(status_message: Any, platform_name: Optional[str] = None) -> None:
    """Отправляет сообщение об ошибке скачивания.

    Args:
        status_message: Статусное сообщение для редактирования
        platform_name: Платформа, на которой произошла ошибка
    """
    if platform_name == 'instagram':
        await status_message.edit_text(
            '❌ Не удалось скачать видео из Instagram.\n\n'
            'Возможные причины:\n'
            f'• Размер видео превышает {format_size(MAX_DOWNLOAD_SIZE)}\n'
            '• Для просмотра требуется вход в Instagram\n'
            '• Видео удалено или доступ к нему ограничен\n'
            '• Instagram временно ограничил запросы бота\n\n'
            'Попробуйте позже или сообщите администратору бота.'
        )
        return

    await status_message.edit_text(
        '❌ Не удалось скачать видео.\n\n'
        'Возможные причины:\n'
        f'• Размер видео превышает {format_size(MAX_DOWNLOAD_SIZE)}\n'
        '• Видео недоступно\n'
        '• Ограничения YouTube\n\n'
        'Попробуйте другое видео.'
    )


async def _send_video_parts(
    status_message: Any,
    parts: list[str],
) -> None:
    """Отправляет части видео пользователю.

    Args:
        status_message: Статусное сообщение
        parts: Список путей к частям
    """
    try:
        for i, part_path in enumerate(parts, 1):
            with open(part_path, 'rb') as part_file:
                await status_message.reply_video(video=part_file)
            logger.info('Отправлена часть %s/%s', i, len(parts))
    finally:
        _cleanup_parts(parts, base_dir=DOWNLOAD_DIR)


async def _send_large_video(
    task: DownloadTask,
    video_path: str,
) -> bool:
    """Отправляет большое видео по частям.

    Args:
        task: Задача скачивания
        video_path: Путь к видео

    Returns:
        True если успешно, иначе False
    """
    await task.status_message.edit_text(
        f'🔄 Видео большое ({format_size(os.path.getsize(video_path))}).\n'
        f'Разбиваю на части...'
    )

    worker = asyncio.create_task(asyncio.to_thread(split_video, video_path))
    try:
        parts = await asyncio.shield(worker)
    except asyncio.CancelledError:
        cancelled_downloads.add(task.user_id)
        parts = await worker
        _cleanup_parts(parts, base_dir=DOWNLOAD_DIR)
        raise

    if not parts:
        await task.status_message.edit_text(
            '❌ Не удалось разбить видео'
        )
        return False

    try:
        if task.user_id not in cancelled_downloads:
            await task.status_message.edit_text(f'📤 Отправляю {len(parts)} частей...')
            await _send_video_parts(task.status_message, parts)
        else:
            return False
    finally:
        _cleanup_parts(parts, base_dir=DOWNLOAD_DIR)

    await task.status_message.edit_text(
        f'✅ {task.user_name}, видео отправлено {len(parts)} частями!'
    )
    logger.info(f'[User {task.user_id}] Видео отправлено {len(parts)} частями')

    return True


async def _send_single_video(
    task: DownloadTask,
    video_path: str,
) -> None:
    """Отправляет видео целиком.

    Args:
        task: Задача скачивания
        video_path: Путь к видео
    """
    await task.status_message.edit_text('📤 Отправляю видео...')

    with open(video_path, 'rb') as video_file:
        await task.status_message.reply_video(video=video_file)

    await task.status_message.delete()
    logger.info(f'[User {task.user_id}] Видео отправлено')


async def _process_download_success(task: DownloadTask, video_path: str) -> None:
    """Обрабатывает успешное скачивание.

    Args:
        task: Задача скачивания
        video_path: Путь к скачанному видео
    """
    file_size = os.path.getsize(video_path)

    if file_size > MAX_FILE_SIZE:
        success = await _send_large_video(task, video_path)
        if not success:
            return
    else:
        await _send_single_video(task, video_path)


async def process_download(task: DownloadTask) -> None:
    """Асинхронная обработка скачивания видео.

    Args:
        task: Задача с информацией о пользователе и URL
    """
    user_id = task.user_id
    url = task.url
    video_path: Optional[str] = None
    user_mention = task.user_name
    task.download_id = task.download_id or uuid.uuid4().hex

    try:
        # Проверяем отмену
        if user_id in cancelled_downloads:
            logger.info(f'[User {user_id}] Загрузка отменена до начала')
            return

        # Создаём клавиатуру с кнопкой отмены
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ Отмена", callback_data=f'cancel_{user_id}_{task.download_id}')
        ]])

        await task.status_message.edit_text(
            f'⏳ Скачиваю видео...\n\n'
            f'👤 {user_mention}\n'
            f'📎 {url[:50]}...',
            reply_markup=keyboard
        )

        logger.info(f'[User {user_id}] Запуск скачивания: {url}')
        worker = asyncio.create_task(asyncio.to_thread(
            download_video_sync, url, task.download_id,
            lambda: user_id in cancelled_downloads,
        ))
        try:
            video_path = await asyncio.shield(worker)
        except asyncio.CancelledError:
            # Cancelling to_thread does not stop its worker. Keep ownership until
            # it exits so cleanup cannot race with writes or a new user request.
            cancelled_downloads.add(user_id)
            video_path = await worker
            raise
        task.video_path = video_path

        # Проверяем отмену после скачивания
        if user_id in cancelled_downloads:
            try:
                await task.status_message.edit_text('❌ Загрузка отменена')
            except Exception:
                pass
            return

        if not video_path or not os.path.exists(video_path):
            await _send_download_error(task.status_message, detect_platform(url))
            return

        await _process_download_success(task, video_path)

    except Exception:
        logger.exception('[User %s] Ошибка обработки', user_id)
        try:
            await task.status_message.edit_text('❌ Не удалось обработать видео. Попробуйте позже.')
        except Exception as msg_error:
            logger.warning(f'[User {user_id}] Не удалось обновить статус: {msg_error}')

    finally:
        cleanup_download(user_id, video_path, task.download_id)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /start."""
    message = (
        '👋 *Привет! Я бот для скачивания видео*\n\n'
        '🎬 *Функции:*\n'
        '• Скачивание с YouTube и Instagram\n'
        '• Качество до 1080p\n'
        '• Автоматическое разбиение на части\n'
        '• Одновременная обработка нескольких запросов\n\n'
        '📋 *Команды:*\n'
        '/start - Начать работу\n'
        '/help - Справка\n\n'
        '⚠️ *Ограничения:*\n'
        f'• Исходное видео: до {format_size(MAX_DOWNLOAD_SIZE)}\n'
        '• Часть для отправки: до 50MB\n'
        '• Без плейлистов и прямых трансляций'
    )

    await update.message.reply_text(message, parse_mode='Markdown')


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /help."""
    chat_type = update.message.chat.type

    message = (
        '📖 *Справка*\n\n'
        '*Как использовать:*\n'
        '1. Отправьте ссылку на видео\n'
        '2. Я скачаю его в лучшем качестве\n'
        '3. Если >50MB — разобью на части\n\n'
    )

    if chat_type in ['group', 'supergroup']:
        message += (
            '*В группах:*\n'
            '• Упомяните бота: @username ссылка\n'
            '• Или reply на сообщение бота со ссылкой\n'
            '• Или используйте команду /download ссылка\n\n'
        )
    else:
        message += (
            '*Команды:*\n'
            '/start - Начать работу\n'
            '/help - Справка\n\n'
        )

    message += (
        '*Поддерживаемые платформы:*\n\n'
        '*YouTube:*\n'
        '• youtube.com/watch?v=...\n'
        '• youtu.be/...\n'
        '• youtube.com/shorts/...\n\n'
        '*Instagram:*\n'
        '• instagram.com/p/... (посты)\n'
        '• instagram.com/reel/... (Reels)\n\n'
        '*Качество:*\n'
        '• YouTube: автоматический выбор (1080p → 720p → 480p → 360p)\n'
        '• Instagram: лучшее доступное\n\n'
        'Доступность видео зависит от ограничений платформы.'
    )

    await update.message.reply_text(message, parse_mode='Markdown')


async def _start_download(update: Update, url: str) -> None:
    user = update.effective_user
    message = update.message
    if not user or not message:
        return
    user_id = user.id
    if not detect_platform(url):
        if message.chat.type not in ('group', 'supergroup'):
            await message.reply_text(
                '❌ Неверная ссылка. Отправьте ссылку на видео YouTube или Instagram.'
            )
        return
    if user_id in active_downloads:
        await message.reply_text('⚠️ Вы уже скачиваете видео! Дождитесь окончания загрузки.')
        return
    if len(active_downloads) >= MAX_CONCURRENT_DOWNLOADS:
        await message.reply_text('⏳ Бот сейчас занят. Попробуйте немного позже.')
        return
    download_id = uuid.uuid4().hex
    active_downloads[user_id] = {'download_id': download_id}
    try:
        status = await message.reply_text('⏳ Добавлено в очередь...')
        task = DownloadTask(
            user_id, message.chat_id, message.message_id, url, status,
            f'@{user.username}' if user.username else user.first_name or f'User_{user_id}',
            download_id=download_id,
        )
        bg_task = asyncio.create_task(process_download(task))
        background_tasks.add(bg_task)
        bg_task.add_done_callback(background_tasks.discard)
    except BaseException:
        cleanup_download(user_id, download_id=download_id)
        raise


async def download_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return
    if not context.args:
        await update.message.reply_text(
            '❌ Укажите ссылку после команды.\n\n'
            'Пример: /download https://youtube.com/watch?v=...'
        )
        return
    await _start_download(update, ' '.join(context.args).strip())


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if not message or not update.effective_user:
        return
    text = message.text or ''
    url = text.strip()
    if message.chat.type in ('group', 'supergroup'):
        mention = f'@{context.bot.username}'
        reply = message.reply_to_message
        mentioned = mention.lower() in text.lower().split()
        replies_to_bot = reply and reply.from_user and reply.from_user.id == context.bot.id
        if not (mentioned or replies_to_bot):
            return
        if mentioned:
            url = ' '.join(word for word in text.split() if word.lower() != mention.lower())
    await _start_download(update, url)


async def _wait_for_downloads(application: Application) -> None:
    """Let workers stop and clean their files before Telegram is shut down."""
    cancelled_downloads.update(active_downloads)
    if background_tasks:
        await asyncio.gather(*list(background_tasks), return_exceptions=True)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log transient connection failures without interrupting polling retries."""
    error = context.error
    # BadRequest inherits from NetworkError, but retrying cannot fix an invalid request.
    if isinstance(error, NetworkError) and not isinstance(error, BadRequest):
        if update is None:
            logger.warning(
                'Связь с Telegram прервана (%s). Получение сообщений будет повторено автоматически.',
                type(error).__name__,
            )
        else:
            logger.warning(
                'Не удалось обработать сообщение из-за сетевой ошибки (%s). '
                'После восстановления связи повторите команду.',
                type(error).__name__,
            )
        return

    logger.error('Необработанная ошибка Telegram', exc_info=error)


def main() -> None:
    """Запуск бота."""
    if not BOT_TOKEN:
        raise ValueError(
            'TELEGRAM_BOT_TOKEN не найден в переменных окружения. '
            'Создайте .env файл с токеном бота.'
        )

    logger.info('Запуск бота...')
    logger.info('Макс. одновременных скачиваний: %s', MAX_CONCURRENT_DOWNLOADS)

    # Configure longer timeouts for file uploads
    request = HTTPXRequest(
        read_timeout=30.0,
        write_timeout=30.0,
        connect_timeout=10.0,
        pool_timeout=1.0,
        media_write_timeout=60.0,
    )

    application = (
        Application.builder().token(BOT_TOKEN).request(request)
        .post_stop(_wait_for_downloads).build()
    )
    application.add_error_handler(error_handler)

    application.add_handler(CommandHandler('start', start_command))
    application.add_handler(CommandHandler('help', help_command))
    application.add_handler(CommandHandler('download', download_command))
    application.add_handler(CallbackQueryHandler(cancel_button, pattern='^cancel_'))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info('Подключение к Telegram...')
    # Polling already retries indefinitely; also retry initialization (getMe/deleteWebhook).
    application.run_polling(allowed_updates=Update.ALL_TYPES, bootstrap_retries=-1)


if __name__ == '__main__':
    main()
