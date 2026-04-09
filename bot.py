"""Telegram Video Downloader Bot.

Downloads videos from YouTube and Instagram in best quality
and sends them to Telegram, splitting large files into 50MB parts.
"""

import asyncio
import logging
import os
import subprocess
import uuid
from dataclasses import dataclass
from typing import Any, Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
import yt_dlp

from config import BOT_TOKEN, DOWNLOAD_DIR, MAX_FILE_SIZE
from platforms import YouTubePlatform, InstagramPlatform


# Constants
MB = 1024 * 1024
TARGET_SIZE_MB = 45  # 90% of 50MB limit for safety
MAX_RETRIES = 2
RETRY_DURATION_MULTIPLIER = 0.8  # Reduce duration by 20% on retry

# Platform handlers
youtube_platform = YouTubePlatform()
instagram_platform = InstagramPlatform()
PLATFORMS = [youtube_platform, instagram_platform]


# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Create download directory
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

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


def format_size(bytes_size: int) -> str:
    """Форматирование байт в MB строку."""
    return f'{bytes_size / MB:.1f}MB'


def is_safe_path(path: str, base_dir: str = DOWNLOAD_DIR) -> bool:
    """Проверка, что путь находится внутри базовой директории.

    Args:
        path: Путь для проверки
        base_dir: Базовая директория

    Returns:
        True если путь безопасен
    """
    try:
        # Получаем абсолютный путь
        abs_path = os.path.abspath(path)
        abs_base = os.path.abspath(base_dir)

        # Проверяем, что путь начинается с базовой директории
        return abs_path.startswith(abs_base + os.sep) or abs_path == abs_base
    except (ValueError, TypeError):
        return False


def is_youtube_url(url: str) -> bool:
    """Проверка, является ли URL ссылкой на YouTube."""
    return youtube_platform.is_valid_url(url)


def is_instagram_url(url: str) -> bool:
    """Проверка, является ли URL ссылкой на Instagram."""
    return instagram_platform.is_valid_url(url)


def detect_platform(url: str) -> Optional[str]:
    """Определяет платформу по URL.

    Args:
        url: URL для проверки

    Returns:
        Название платформы ('youtube', 'instagram') или None
    """
    for platform in PLATFORMS:
        if platform.is_valid_url(url):
            return platform.name
    return None


def _get_platform_handler(url: str) -> Optional[Any]:
    """Определяет платформу по URL.

    Args:
        url: URL для проверки

    Returns:
        Обработчик платформы или None
    """
    for platform in PLATFORMS:
        if platform.is_valid_url(url):
            return platform
    return None


def _get_video_info(url: str, platform_name: str, download_id: str) -> Optional[dict]:
    """Получает информацию о видео.

    Args:
        url: URL видео
        platform_name: Название платформы
        download_id: ID для логирования

    Returns:
        Информация о видео или None
    """
    info_opts = {'quiet': True, 'no_warnings': True}

    try:
        with yt_dlp.YoutubeDL(info_opts) as ydl:
            logger.info(f'[Thread] [{download_id}] Анализ ({platform_name}): {url}')
            return ydl.extract_info(url, download=False)
    except Exception as e:
        logger.error(f'[Thread] [{download_id}] Ошибка получения информации: {e}')
        return None


def _find_downloaded_file(download_id: str) -> Optional[str]:
    """Ищет скачанный файл по download_id.

    Args:
        download_id: ID скачивания

    Returns:
        Путь к файлу или None
    """
    mp4_files = [
        os.path.join(DOWNLOAD_DIR, f)
        for f in os.listdir(DOWNLOAD_DIR)
        if f.startswith(download_id) and f.endswith('.mp4')
    ]

    if mp4_files:
        return max(mp4_files, key=os.path.getmtime)
    return None


def _try_download_format(
    url: str,
    download_id: str,
    format_selector: str,
    extractor_args: Optional[dict],
    attempt: int,
    total: int,
) -> Optional[str]:
    """Пытается скачать видео в указанном формате.

    Args:
        url: URL видео
        download_id: ID для логирования
        format_selector: Селектор формата
        extractor_args: Аргументы экстрактора
        attempt: Номер попытки
        total: Общее количество попыток

    Returns:
        Путь к скачанному файлу или None
    """
    client_name = (
        extractor_args.get('youtube', {}).get('player_client', 'default')
        if extractor_args
        else 'default'
    )
    logger.info(
        f'[Thread] [{download_id}] Попытка {attempt}/{total}: '
        f'{format_selector} (client: {client_name})'
    )

    download_opts = {
        'format': format_selector,
        'outtmpl': os.path.join(DOWNLOAD_DIR, f'{download_id}_%(title)s.%(ext)s'),
        'quiet': True,
        'no_warnings': True,
        'merge_output_format': 'mp4',
    }

    if extractor_args:
        download_opts['extractor_args'] = extractor_args

    try:
        with yt_dlp.YoutubeDL(download_opts) as download_ydl:
            download_ydl.download([url])
            info_after = download_ydl.extract_info(url, download=False)
            filename = download_ydl.prepare_filename(info_after)

            if os.path.exists(filename):
                file_size = os.path.getsize(filename)
                logger.info(
                    f'[Thread] [{download_id}] Скачано: '
                    f'{format_selector}, размер: {format_size(file_size)}'
                )
                return filename

            # Ищем новейший файл с нашим ID
            newest_file = _find_downloaded_file(download_id)
            if newest_file:
                file_size = os.path.getsize(newest_file)
                logger.info(
                    f'[Thread] [{download_id}] Скачано: '
                    f'{format_selector}, размер: {format_size(file_size)}'
                )
                return newest_file

    except Exception as e:
        logger.warning(
            f'[Thread] [{download_id}] Формат {format_selector} не сработал: {e}'
        )

    return None


def download_video_sync(url: str) -> Optional[str]:
    """Синхронное скачивание видео (выполняется в thread pool).

    Args:
        url: Ссылка на YouTube или Instagram видео

    Returns:
        Путь к скачанному файлу или None при ошибке
    """
    download_id = str(uuid.uuid4())[:8]

    # Определяем платформу
    platform_handler = _get_platform_handler(url)
    if not platform_handler:
        logger.error(f'[{download_id}] Неизвестная платформа для URL: {url}')
        return None

    # Получаем информацию о видео
    info = _get_video_info(url, platform_handler.name, download_id)
    if not info:
        return None

    # Получаем опции форматов от платформы
    formats_to_try = platform_handler.get_format_options(info)
    if not formats_to_try:
        logger.warning(f'[Thread] [{download_id}] Подходящий формат не найден')
        return None

    # Пробуем каждый формат
    for i, (format_selector, extractor_args) in enumerate(formats_to_try, 1):
        result = _try_download_format(
            url, download_id, format_selector, extractor_args, i, len(formats_to_try)
        )
        if result:
            return result

    logger.error(f'[Thread] [{download_id}] Все форматы не сработали')
    return None


def _get_video_duration(video_path: str) -> Optional[float]:
    """Получает длительность видео через ffprobe.

    Args:
        video_path: Путь к видео

    Returns:
        Длительность в секундах или None
    """
    result = subprocess.run(
        [
            'ffprobe', '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            video_path,
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        logger.error(f'[Thread] Ошибка ffprobe: {result.stderr}')
        return None

    try:
        return float(result.stdout.strip())
    except ValueError:
        logger.error(f'[Thread] Не удалось распарсить длительность: {result.stdout}')
        return None


def _calculate_parts(file_size: int, duration: float) -> tuple[int, float]:
    """Вычисляет количество частей и длительность каждой.

    Args:
        file_size: Размер файла в байтах
        duration: Длительность видео в секундах

    Returns:
        Кортеж (количество_частей, длительность_части)
    """
    target_size = MAX_FILE_SIZE * (TARGET_SIZE_MB / 50.0)
    num_parts = int(file_size / target_size) + 1
    part_duration = duration / num_parts
    return num_parts, part_duration


def _cleanup_parts(parts: list[str]) -> None:
    """Удаляет все созданные части.

    Args:
        parts: Список путей к частям
    """
    for part_path in parts:
        if os.path.exists(part_path):
            os.remove(part_path)


def _create_video_part(
    video_path: str,
    output_path: str,
    start_time: float,
    part_duration: float,
) -> bool:
    """Создаёт одну часть видео.

    Args:
        video_path: Путь к исходному видео
        output_path: Путь для выходного файла
        start_time: Начальное время в секундах
        part_duration: Длительность части в секундах

    Returns:
        True если успешно, иначе False
    """
    try:
        subprocess.run(
            [
                'ffmpeg', '-i', video_path,
                '-ss', str(start_time),
                '-t', str(part_duration),
                '-c', 'copy',
                '-y',
                output_path,
            ],
            capture_output=True,
            check=True,
        )
        return True
    except subprocess.CalledProcessError as e:
        logger.error(
            f'[Thread] Ошибка ffmpeg: '
            f'{e.stderr.decode() if e.stderr else str(e)}'
        )
        return False


def _split_part_with_retry(
    video_path: str,
    output_path: str,
    start_time: float,
    initial_duration: float,
    part_index: int,
    total_parts: int,
) -> Optional[str]:
    """Создаёт часть с ретраями если превышен размер.

    Args:
        video_path: Путь к исходному видео
        output_path: Путь для выходного файла
        start_time: Начальное время в секундах
        initial_duration: Начальная длительность части
        part_index: Номер части
        total_parts: Общее количество частей

    Returns:
        Путь к части или None при ошибке
    """
    part_duration = initial_duration

    for attempt in range(MAX_RETRIES):
        if not _create_video_part(video_path, output_path, start_time, part_duration):
            return None

        actual_size = os.path.getsize(output_path)

        if actual_size <= MAX_FILE_SIZE:
            logger.info(
                f'[Thread] Часть {part_index}/{total_parts}: '
                f'{format_size(actual_size)}'
            )
            return output_path

        # Часть слишком большая
        logger.warning(
            f'[Thread] Часть {part_index} слишком большая: {format_size(actual_size)}'
        )

        if attempt < MAX_RETRIES - 1:
            os.remove(output_path)
            part_duration *= RETRY_DURATION_MULTIPLIER
            logger.info(
                f'[Thread] Попытка {attempt+2}: '
                f'длительность уменьшена до {part_duration:.1f}s'
            )
        else:
            os.remove(output_path)
            logger.error(f'[Thread] Часть {part_index} превышает лимит, отказываемся')
            return None

    return None


def split_video(video_path: str) -> list[str]:
    """Разбиение видео на части до 50MB каждая.

    Args:
        video_path: Путь к исходному видео

    Returns:
        Список путей к частям или пустой список при ошибке
    """
    # Проверка безопасности пути
    if not is_safe_path(video_path):
        logger.error(f'[Thread] Небезопасный путь: {video_path}')
        return []

    try:
        # Получаем длительность
        duration = _get_video_duration(video_path)
        if not duration:
            return []

        # Вычисляем параметры разбиения
        file_size = os.path.getsize(video_path)
        num_parts, part_duration = _calculate_parts(file_size, duration)

        output_files: list[str] = []

        for i in range(num_parts):
            start_time = i * part_duration
            output_path = video_path.replace('.mp4', f'_part{i+1}.mp4')

            # Проверка безопасности выходного пути
            if not is_safe_path(output_path):
                logger.error(f'[Thread] Небезопасный путь: {output_path}')
                _cleanup_parts(output_files)
                return []

            # Создаём часть с ретраями
            result = _split_part_with_retry(
                video_path,
                output_path,
                start_time,
                part_duration,
                i + 1,
                num_parts,
            )

            if not result:
                _cleanup_parts(output_files)
                return []

            output_files.append(result)

        return output_files

    except Exception as e:
        logger.error(f'[Thread] Ошибка разбиения: {e}')
        return []


def cleanup_download(user_id: int, video_path: Optional[str] = None) -> None:
    """Очистка ресурсов после завершения или ошибки.

    Args:
        user_id: Telegram ID пользователя
        video_path: Опциональный путь к видео для удаления
    """
    if user_id in active_downloads:
        del active_downloads[user_id]

    # Очищаем из отменённых
    cancelled_downloads.discard(user_id)

    if video_path and os.path.exists(video_path):
        # Проверка безопасности перед удалением
        if not is_safe_path(video_path):
            logger.warning(f'Небезопасный путь при очистке: {video_path}')
            return

        try:
            os.remove(video_path)
        except OSError as e:
            logger.warning(f'Не удалось удалить {video_path}: {e}')


async def cancel_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик кнопки отмены."""
    query = update.callback_query
    await query.answer()

    # Парсим callback_data: "cancel_{user_id}"
    callback_data = query.data
    if not callback_data or not callback_data.startswith('cancel_'):
        return

    try:
        user_id = int(callback_data.split('_')[1])
    except (IndexError, ValueError):
        return

    # Проверяем, что нажал тот же пользователь
    if query.from_user.id != user_id:
        await query.edit_message_text('❌ Это не ваша загрузка!')
        return

    # Помечаем как отменённую
    cancelled_downloads.add(user_id)

    # Обновляем сообщение
    try:
        await query.edit_message_text('❌ Загрузка отменена')
    except Exception as e:
        logger.warning(f'Не удалось обновить сообщение: {e}')

    logger.info(f'[User {user_id}] Загрузка отменена пользователем')


async def _send_download_error(status_message: Any) -> None:
    """Отправляет сообщение об ошибке скачивания.

    Args:
        status_message: Статусное сообщение для редактирования
    """
    await status_message.edit_text(
        '❌ Не удалось скачать видео.\n\n'
        'Возможные причины:\n'
        '• Видео слишком большое\n'
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
    for i, part_path in enumerate(parts, 1):
        part_size = os.path.getsize(part_path)

        with open(part_path, 'rb') as part_file:
            await status_message.reply_video(video=part_file)

        logger.info(f'Отправлена часть {i}/{len(parts)}')
        os.remove(part_path)


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

    parts = await asyncio.to_thread(split_video, video_path)

    if not parts:
        await task.status_message.edit_text(
            '❌ Не удалось разбить видео'
        )
        cleanup_download(task.user_id, video_path)
        return False

    await task.status_message.edit_text(
        f'📤 Отправляю {len(parts)} частей...'
    )

    await _send_video_parts(task.status_message, parts)
    os.remove(video_path)

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

    file_size = os.path.getsize(video_path)

    with open(video_path, 'rb') as video_file:
        await task.status_message.reply_video(video=video_file)

    await task.status_message.delete()
    os.remove(video_path)
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

    cleanup_download(task.user_id)


async def process_download(task: DownloadTask) -> None:
    """Асинхронная обработка скачивания видео.

    Args:
        task: Задача с информацией о пользователе и URL
    """
    user_id = task.user_id
    url = task.url
    video_path: Optional[str] = None
    user_mention = task.user_name

    try:
        # Проверяем отмену
        if user_id in cancelled_downloads:
            logger.info(f'[User {user_id}] Загрузка отменена до начала')
            return

        # Создаём клавиатуру с кнопкой отмены
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ Отмена", callback_data=f'cancel_{user_id}')
        ]])

        await task.status_message.edit_text(
            f'⏳ Скачиваю видео...\n\n'
            f'👤 {user_mention}\n'
            f'📎 {url[:50]}...',
            reply_markup=keyboard
        )

        logger.info(f'[User {user_id}] Запуск скачивания: {url}')
        video_path = await asyncio.to_thread(download_video_sync, url)

        # Проверяем отмену после скачивания
        if user_id in cancelled_downloads:
            try:
                await task.status_message.edit_text('❌ Загрузка отменена')
            except Exception:
                pass
            return

        if not video_path or not os.path.exists(video_path):
            await _send_download_error(task.status_message)
            return

        await _process_download_success(task, video_path)

    except Exception as e:
        logger.error(f'[User {user_id}] Ошибка обработки: {e}')
        try:
            await task.status_message.edit_text(f'❌ Ошибка: {e}')
        except Exception as msg_error:
            logger.warning(f'[User {user_id}] Не удалось обновить статус: {msg_error}')

    finally:
        cleanup_download(user_id, video_path)


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
        '• Макс. размер файла: 50MB\n'
        '• Только публичные видео'
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
        'Без привязки к аккаунту!'
    )

    await update.message.reply_text(message, parse_mode='Markdown')


async def download_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /download для групповых чатов."""
    # Проверяем, есть ли аргументы (URL после команды)
    if not context.args or len(context.args) == 0:
        await update.message.reply_text(
            '❌ Укажите ссылку после команды.\n\n'
            'Пример: /download https://youtube.com/watch?v=...'
        )
        return

    # Получаем URL из аргументов команды
    url = ' '.join(context.args)
    user_id = update.effective_user.id
    chat_type = update.message.chat.type

    # Получаем имя пользователя для отображения
    user = update.effective_user
    if user.username:
        user_name = f'@{user.username}'
    else:
        user_name = user.first_name or f'User_{user_id}'

    # Проверка поддерживаемых URL
    platform = detect_platform(url)
    if not platform:
        if chat_type in ['group', 'supergroup']:
            return
        await update.message.reply_text(
            '❌ Неверная ссылка.\n\n'
            'Поддерживаются:\n'
            '• YouTube (youtube.com, youtu.be)\n'
            '• Instagram (instagram.com/p, instagram.com/reel)\n\n'
            'Пожалуйста, отправьте действительную ссылку.'
        )
        return

    # Проверка активной загрузки
    if user_id in active_downloads:
        await update.message.reply_text(
            '⚠️ Вы уже скачиваете видео!\n'
            'Дождитесь окончания текущей загрузки.'
        )
        return

    # Создаём статусное сообщение
    status_message = await update.message.reply_text('⏳ Добавлено в очередь...')

    # Генерируем ID для этого скачивания
    download_id = str(uuid.uuid4())[:8]

    # Создаём задачу
    task = DownloadTask(
        user_id=user_id,
        chat_id=update.message.chat_id,
        message_id=update.message.message_id,
        url=url,
        status_message=status_message,
        user_name=user_name,
        download_id=download_id,
    )

    # Регистрируем активную загрузку
    active_downloads[user_id] = {
        'chat_id': update.message.chat_id,
        'message_id': update.message.message_id,
        'status': 'downloading',
        'url': url,
        'download_id': download_id,
    }

    # Запускаем фоновую задачу
    bg_task = asyncio.create_task(process_download(task))
    bg_task.add_done_callback(background_tasks.discard)
    background_tasks.add(bg_task)

    logger.info(f'[User {user_id}] Задача добавлена: {url}')


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик текстовых сообщений (ссылки на YouTube/Instagram)."""
    url = update.message.text.strip()
    user_id = update.effective_user.id
    chat_type = update.message.chat.type

    # В групповых чатах проверяем упоминание бота или reply
    if chat_type in ['group', 'supergroup']:
        bot_username = context.bot.username
        text = update.message.text or ''

        # Проверяем: упоминание бота, reply на сообщение бота, или команда
        mentioned = (
            f'@{bot_username}' in text or
            (update.message.reply_to_message and
             update.message.reply_to_message.from_user.id == context.bot.id) or
            text.startswith('/')
        )

        if not mentioned:
            # Игнорируем сообщения без упоминания бота в группах
            return

        # Убираем упоминание бота из URL если есть
        if f'@{bot_username}' in text:
            url = text.replace(f'@{bot_username}', '').strip()

    # Получаем имя пользователя для отображения
    user = update.effective_user
    if user.username:
        user_name = f'@{user.username}'
    else:
        user_name = user.first_name or f'User_{user_id}'

    # Проверка поддерживаемых URL
    platform = detect_platform(url)
    if not platform:
        # В группах не отвечаем на неверные ссылки без упоминания
        if chat_type in ['group', 'supergroup']:
            return
        await update.message.reply_text(
            '❌ Неверная ссылка.\n\n'
            'Поддерживаются:\n'
            '• YouTube (youtube.com, youtu.be)\n'
            '• Instagram (instagram.com/p, instagram.com/reel)\n\n'
            'Пожалуйста, отправьте действительную ссылку.'
        )
        return

    # Проверка активной загрузки
    if user_id in active_downloads:
        await update.message.reply_text(
            '⚠️ Вы уже скачиваете видео!\n'
            'Дождитесь окончания текущей загрузки.'
        )
        return

    # Создаём статусное сообщение
    status_message = await update.message.reply_text('⏳ Добавлено в очередь...')

    # Генерируем ID для этого скачивания
    download_id = str(uuid.uuid4())[:8]

    # Создаём задачу
    task = DownloadTask(
        user_id=user_id,
        chat_id=update.message.chat_id,
        message_id=update.message.message_id,
        url=url,
        status_message=status_message,
        user_name=user_name,
        download_id=download_id,
    )

    # Регистрируем активную загрузку
    active_downloads[user_id] = {
        'chat_id': update.message.chat_id,
        'message_id': update.message.message_id,
        'status': 'downloading',
        'url': url,
        'download_id': download_id,
    }

    # Запускаем фоновую задачу
    bg_task = asyncio.create_task(process_download(task))
    bg_task.add_done_callback(background_tasks.discard)
    background_tasks.add(bg_task)

    logger.info(f'[User {user_id}] Задача добавлена: {url}')


def main() -> None:
    """Запуск бота."""
    if not BOT_TOKEN:
        raise ValueError(
            'TELEGRAM_BOT_TOKEN не найден в переменных окружения. '
            'Создайте .env файл с токеном бота.'
        )

    logger.info('Запуск бота...')
    logger.info('Макс. одновременных скачиваний: 3')

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler('start', start_command))
    application.add_handler(CommandHandler('help', help_command))
    application.add_handler(CommandHandler('download', download_command))
    application.add_handler(CallbackQueryHandler(cancel_button, pattern='^cancel_'))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info('Бот запущен!')
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
