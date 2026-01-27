"""Telegram YouTube Downloader Bot.

Downloads YouTube videos in best quality (1080p → 720p → 480p → 360p)
and sends them to Telegram, splitting large files into 50MB parts.
"""

import asyncio
import logging
import os
import re
import subprocess
import uuid
from dataclasses import dataclass
from typing import Any, Optional

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
import yt_dlp

from config import BOT_TOKEN, DOWNLOAD_DIR, MAX_FILE_SIZE


# Constants
MB = 1024 * 1024
TARGET_SIZE_MB = 45  # 90% of 50MB limit for safety
MAX_RETRIES = 2
SIZE_THRESHOLD = 1.5  # Multiplier for format size estimation
RETRY_DURATION_MULTIPLIER = 0.8  # Reduce duration by 20% on retry

# YouTube URL pattern
YOUTUBE_PATTERN = r'^(https?://)?(www\.)?(youtube\.com|youtu\.be)/.+$'

# Format priorities (height, extractor_args)
FORMAT_CANDIDATES = [
    (1080, {'youtube': {'player_client': 'mediaconnect'}}),
    (720, {'youtube': {'player_client': 'mediaconnect'}}),
    (480, {}),
    (360, {}),
]


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


def is_youtube_url(url: str) -> bool:
    """Проверка, является ли URL ссылкой на YouTube."""
    return bool(re.match(YOUTUBE_PATTERN, url))


def estimate_format_size(info: dict, target_height: int) -> Optional[int]:
    """Оценка размера формата по заданному качеству.

    Args:
        info: Метаданные видео от yt-dlp
        target_height: Желаемая высота видео

    Returns:
        Оценочный размер в байтах или None если неизвестен
    """
    formats = info.get('formats', [])

    for fmt in formats:
        height = fmt.get('height')
        filesize = fmt.get('filesize')
        vcodec = fmt.get('vcodec', '')

        # Пропускаем аудио-только потоки
        if vcodec == 'none':
            continue

        # Ищем формат с целевым разрешением (в пределах 10px)
        if height and abs(height - target_height) <= 10:
            if filesize:
                return filesize

            # DASH формат: суммируем размеры видео + аудио
            if fmt.get('acodec') == 'none' and filesize is None:
                audio_fmt = next(
                    (
                        f for f in formats
                        if f.get('acodec') != 'none' and f.get('vcodec') == 'none'
                    ),
                    None,
                )
                if audio_fmt and audio_fmt.get('filesize'):
                    return fmt.get('filesize', 0) + audio_fmt.get('filesize', 0)

    return None


def should_skip_format(info: dict, target_height: int) -> bool:
    """Проверить, следует ли пропустить формат из-за лимита размера."""
    estimated = estimate_format_size(info, target_height)
    if estimated and estimated > MAX_FILE_SIZE * SIZE_THRESHOLD:
        logger.info(
            f'[Thread] {target_height}p пропущен '
            f'(оценка {format_size(estimated)} > {format_size(MAX_FILE_SIZE)})'
        )
        return True
    return False


def select_best_format(info: dict) -> list[tuple[str, dict]]:
    """Выбор лучшего формата от высокого к низкому качеству.

    Args:
        info: Метаданные видео от yt-dlp

    Returns:
        Список кортежей (format_selector, extractor_args)
    """
    formats_to_try = []

    for target_height, extractor_args in FORMAT_CANDIDATES:
        # Пропускаем форматы превышающие лимит
        if target_height in (1080, 720) and should_skip_format(info, target_height):
            continue

        # Формируем селектор формата
        if target_height >= 480:
            format_selector = (
                f'bestvideo[height<={target_height}][ext=mp4]+bestaudio[ext=m4a]/'
                f'bestvideo[height<={target_height}]+bestaudio'
            )
        else:
            format_selector = '18'

        formats_to_try.append((format_selector, extractor_args))

    return formats_to_try


def download_video_sync(url: str) -> Optional[str]:
    """Синхронное скачивание видео (выполняется в thread pool).

    Args:
        url: Ссылка на YouTube видео

    Returns:
        Путь к скачанному файлу или None при ошибке
    """
    download_id = str(uuid.uuid4())[:8]

    try:
        info_opts = {'quiet': True, 'no_warnings': True}

        with yt_dlp.YoutubeDL(info_opts) as ydl:
            logger.info(f'[Thread] [{download_id}] Анализ: {url}')
            info = ydl.extract_info(url, download=False)
            formats = select_best_format(info)

            if not formats:
                logger.warning(f'[Thread] [{download_id}] Подходящий формат не найден')
                return None

        # Пробуем каждый формат
        for i, (format_selector, extractor_args) in enumerate(formats, 1):
            client_name = (
                extractor_args.get('youtube', {}).get('player_client', 'default')
                if extractor_args
                else 'default'
            )
            logger.info(
                f'[Thread] [{download_id}] Попытка {i}/{len(formats)}: '
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
        '👋 *Привет! Я бот для скачивания видео с YouTube*\n\n'
        '🎬 *Функции:*\n'
        '• Скачивание видео до 1080p\n'
        '• Автоматическое разбиение на части\n'
        '• Одновременная обработка нескольких запросов\n\n'
        '📋 *Команды:*\n'
        '/start - Начать работу\n'
        '/help - Справка\n\n'
        '⚠️ *Ограничения:*\n'
        '• Макс. размер файла: 50MB\n'
        '• Только ссылки на YouTube'
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
        '*Поддерживаемые ссылки:*\n'
        '• youtube.com/watch?v=...\n'
        '• youtu.be/...\n'
        '• youtube.com/shorts/...\n\n'
        '*Качество:*\n'
        'Автоматически выбирается лучшее (1080p → 720p → 480p → 360p)\n'
        'Без привязки к аккаунту YouTube!'
    )

    await update.message.reply_text(message, parse_mode='Markdown')


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик текстовых сообщений (ссылки на YouTube)."""
    url = update.message.text.strip()
    user_id = update.effective_user.id

    # Проверка YouTube URL
    if not is_youtube_url(url):
        await update.message.reply_text(
            '❌ Это не ссылка на YouTube.\n\n'
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
