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

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
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


@dataclass
class DownloadTask:
    """Информация о задаче на скачивание."""

    user_id: int
    chat_id: int
    message_id: int
    url: str
    status_message: Any
    video_path: Optional[str] = None


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


def download_video_sync(url: str) -> Optional[str]:
    """Синхронное скачивание видео (выполняется в thread pool).

    Args:
        url: Ссылка на YouTube или Instagram видео

    Returns:
        Путь к скачанному файлу или None при ошибке
    """
    download_id = str(uuid.uuid4())[:8]

    # Определяем платформу и получаем опции форматов
    platform_handler = None
    for platform in PLATFORMS:
        if platform.is_valid_url(url):
            platform_handler = platform
            break

    if not platform_handler:
        logger.error(f'[{download_id}] Неизвестная платформа для URL: {url}')
        return None

    try:
        info_opts = {'quiet': True, 'no_warnings': True}

        with yt_dlp.YoutubeDL(info_opts) as ydl:
            logger.info(f'[Thread] [{download_id}] Анализ ({platform_handler.name}): {url}')
            info = ydl.extract_info(url, download=False)

            # Получаем опции форматов от платформы
            formats_to_try = platform_handler.get_format_options(info)
            if not formats_to_try:
                logger.warning(f'[Thread] [{download_id}] Подходящий формат не найден')
                return None

        # Пробуем каждый формат
        for i, (format_selector, extractor_args) in enumerate(formats_to_try, 1):
            client_name = (
                extractor_args.get('youtube', {}).get('player_client', 'default')
                if extractor_args
                else 'default'
            )
            logger.info(
                f'[Thread] [{download_id}] Попытка {i}/{len(formats_to_try)}: '
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
                    mp4_files = [
                        os.path.join(DOWNLOAD_DIR, f)
                        for f in os.listdir(DOWNLOAD_DIR)
                        if f.startswith(download_id) and f.endswith('.mp4')
                    ]
                    if mp4_files:
                        newest_file = max(mp4_files, key=os.path.getmtime)
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
                continue

        logger.error(f'[Thread] [{download_id}] Все форматы не сработали')
        return None

    except Exception as e:
        logger.error(f'[Thread] [{download_id}] Ошибка скачивания: {e}')
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
        # Получаем длительность через ffprobe
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
            return []

        try:
            duration = float(result.stdout.strip())
        except ValueError:
            logger.error(f'[Thread] Не удалось распарсить длительность: {result.stdout}')
            return []

        file_size = os.path.getsize(video_path)
        target_size = MAX_FILE_SIZE * (TARGET_SIZE_MB / 50.0)
        num_parts = int(file_size / target_size) + 1
        part_duration = duration / num_parts

        output_files: list[str] = []

        for i in range(num_parts):
            start_time = i * part_duration
            output_path = video_path.replace('.mp4', f'_part{i+1}.mp4')

            # Проверка безопасности выходного пути
            if not is_safe_path(output_path):
                logger.error(f'[Thread] Небезопасный путь: {output_path}')
                return []

            for attempt in range(MAX_RETRIES):
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
                except subprocess.CalledProcessError as e:
                    logger.error(
                        f'[Thread] Ошибка ffmpeg: '
                        f'{e.stderr.decode() if e.stderr else str(e)}'
                    )
                    # Очистка при ошибке
                    for f in output_files:
                        if os.path.exists(f):
                            os.remove(f)
                    return []

                actual_size = os.path.getsize(output_path)

                if actual_size <= MAX_FILE_SIZE:
                    output_files.append(output_path)
                    logger.info(
                        f'[Thread] Часть {i+1}/{num_parts}: '
                        f'{format_size(actual_size)}'
                    )
                    break

                # Часть слишком большая, повторяем с меньшей длительностью
                logger.warning(
                    f'[Thread] Часть {i+1} слишком большая: {format_size(actual_size)}'
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
                    logger.error(f'[Thread] Часть {i+1} превышает лимит, отказываемся')
                    # Очищаем все части
                    for f in output_files:
                        if os.path.exists(f):
                            os.remove(f)
                    return []

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

    if video_path and os.path.exists(video_path):
        # Проверка безопасности перед удалением
        if not is_safe_path(video_path):
            logger.warning(f'Небезопасный путь при очистке: {video_path}')
            return

        try:
            os.remove(video_path)
        except OSError as e:
            logger.warning(f'Не удалось удалить {video_path}: {e}')


async def process_download(task: DownloadTask) -> None:
    """Асинхронная обработка скачивания видео.

    Args:
        task: Задача с информацией о пользователе и URL
    """
    user_id = task.user_id
    url = task.url
    video_path: Optional[str] = None

    try:
        await task.status_message.edit_text(
            f'⏳ Скачиваю видео...\n\n📎 {url[:50]}...'
        )

        logger.info(f'[User {user_id}] Запуск скачивания: {url}')
        video_path = await asyncio.to_thread(download_video_sync, url)

        if not video_path or not os.path.exists(video_path):
            await task.status_message.edit_text(
                '❌ Не удалось скачать видео.\n\n'
                'Возможные причины:\n'
                '• Видео слишком большое\n'
                '• Видео недоступно\n'
                '• Ограничения YouTube\n\n'
                'Попробуйте другое видео.'
            )
            return

        file_size = os.path.getsize(video_path)

        if file_size > MAX_FILE_SIZE:
            # Разбиваем на части
            await task.status_message.edit_text(
                f'🔄 Видео большое ({format_size(file_size)}).\n'
                f'Разбиваю на части...'
            )

            parts = await asyncio.to_thread(split_video, video_path)

            if not parts:
                await task.status_message.edit_text(
                    '❌ Не удалось разбить видео'
                )
                cleanup_download(user_id, video_path)
                return

            await task.status_message.edit_text(
                f'📤 Отправляю {len(parts)} частей...'
            )

            for i, part_path in enumerate(parts, 1):
                part_size = os.path.getsize(part_path)

                with open(part_path, 'rb') as part_file:
                    await task.status_message.reply_video(
                        video=part_file,
                        caption=f'🎬 Часть {i}/{len(parts)} ({format_size(part_size)})',
                    )

                logger.info(f'[User {user_id}] Отправлена часть {i}/{len(parts)}')
                os.remove(part_path)

            os.remove(video_path)

            await task.status_message.edit_text(
                f'✅ Видео отправлено {len(parts)} частями!'
            )
            logger.info(f'[User {user_id}] Видео отправлено {len(parts)} частями')

        else:
            # Отправляем целиком
            await task.status_message.edit_text('📤 Отправляю видео...')

            with open(video_path, 'rb') as video_file:
                await task.status_message.reply_video(
                    video=video_file,
                    caption=f'✅ Ваше видео готово! ({format_size(file_size)})',
                )

            await task.status_message.delete()
            os.remove(video_path)
            logger.info(f'[User {user_id}] Видео отправлено')

        cleanup_download(user_id)

    except Exception as e:
        logger.error(f'[User {user_id}] Ошибка обработки: {e}')
        try:
            await task.status_message.edit_text(f'❌ Ошибка: {e}')
        except Exception as msg_error:
            logger.warning(f'[User {user_id}] Не удалось обновить статус: {msg_error}')

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
    message = (
        '📖 *Справка*\n\n'
        '*Как использовать:*\n'
        '1. Отправьте ссылку на видео\n'
        '2. Я скачаю его в лучшем качестве\n'
        '3. Если >50MB — разобью на части\n\n'
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


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик текстовых сообщений (ссылки на YouTube/Instagram)."""
    url = update.message.text.strip()
    user_id = update.effective_user.id

    # Проверка поддерживаемых URL
    platform = detect_platform(url)
    if not platform:
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

    # Создаём задачу
    task = DownloadTask(
        user_id=user_id,
        chat_id=update.message.chat_id,
        message_id=update.message.message_id,
        url=url,
        status_message=status_message,
    )

    # Регистрируем активную загрузку
    active_downloads[user_id] = {
        'chat_id': update.message.chat_id,
        'message_id': update.message.message_id,
        'status': 'downloading',
        'url': url,
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
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info('Бот запущен!')
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
