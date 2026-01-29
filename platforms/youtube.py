"""YouTube platform handler."""

from typing import List, Tuple, Optional
from .base import BasePlatform
from config import MAX_FILE_SIZE


# Format priorities (height, extractor_args)
FORMAT_CANDIDATES = [
    (1080, {'youtube': {'player_client': 'mediaconnect'}}),
    (720, {'youtube': {'player_client': 'mediaconnect'}}),
    (480, {}),
    (360, {}),
]

SIZE_THRESHOLD = 1.5  # Multiplier for format size estimation


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
    MB = 1024 * 1024
    if estimated and estimated > MAX_FILE_SIZE * SIZE_THRESHOLD:
        return True
    return False


def select_best_format(info: dict) -> List[Tuple[str, Optional[dict]]]:
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


class YouTubePlatform(BasePlatform):
    """Обработчик для YouTube."""

    @property
    def name(self) -> str:
        return 'youtube'

    @property
    def url_pattern(self) -> str:
        return r'^(https?://)?(www\.)?(youtube\.com|youtu\.be)/.+$'

    def get_format_options(self, info: dict) -> List[Tuple[str, Optional[dict]]]:
        """Выбор лучшего формата от высокого к низкому качеству."""
        return select_best_format(info)
