"""YouTube platform handler."""

from typing import List, Tuple, Optional
import re
from urllib.parse import parse_qs, urlsplit
from .base import BasePlatform
from config import MAX_FILE_SIZE


SIZE_THRESHOLD = 1.5  # Multiplier for format size estimation


def estimate_format_size(info: dict, target_height: int) -> Optional[int]:
    """Оценка размера формата по короткой стороне кадра.

    Args:
        info: Метаданные видео от yt-dlp
        target_height: Желаемое качество (короткая сторона для вертикального видео)

    Returns:
        Оценочный размер в байтах или None если неизвестен
    """
    formats = info.get('formats', [])

    for fmt in formats:
        height = fmt.get('height')
        width = fmt.get('width')
        resolution = min(width, height) if width and height else height
        filesize = fmt.get('filesize')
        vcodec = fmt.get('vcodec', '')

        # Пропускаем аудио-только потоки
        if vcodec == 'none':
            continue

        # Ищем формат с целевым разрешением (в пределах 10px)
        if resolution and abs(resolution - target_height) <= 10:
            if filesize is None:
                return None

            # DASH формат: суммируем размеры видео + аудио
            if fmt.get('acodec') == 'none':
                audio_fmt = next(
                    (
                        f for f in formats
                        if f.get('acodec') not in (None, 'none') and f.get('vcodec') == 'none'
                    ),
                    None,
                )
                if audio_fmt is None or audio_fmt.get('filesize') is None:
                    return None
                return filesize + audio_fmt['filesize']

            return filesize

    return None


def _video_audio_selector(dimension: str, resolution: int) -> str:
    """Prefer MP4/M4A, then allow other codecs at the same quality limit."""
    return (
        f'bestvideo[{dimension}<={resolution}][ext=mp4]+bestaudio[ext=m4a]/'
        f'bestvideo[{dimension}<={resolution}]+bestaudio'
    )


def select_best_format(info: dict) -> List[Tuple[str, Optional[dict]]]:
    """Выбор лучшего формата от высокого к низкому качеству.

    Логика:
    - Если размер 1080p/720p неизвестн ИЛИ слишком большой → пропускаем
    - Всегда пробуем 480p как безопасный вариант
    - Fallback на 360p если нет 480p

    Args:
        info: Метаданные видео от yt-dlp

    Returns:
        Список кортежей (format_selector, extractor_args)
    """
    formats_to_try = []
    # Shorts are usually portrait: 1080p is 1080x1920, so cap width.
    portrait = any(
        0 < (fmt.get('width') or 0) < (fmt.get('height') or 0)
        for fmt in info.get('formats', []) if fmt.get('vcodec') != 'none'
    )
    dimension = 'width' if portrait else 'height'

    # High qualities require a known video + audio size within the budget.
    for resolution in (1080, 720):
        estimated = estimate_format_size(info, resolution)
        if estimated is None or estimated > MAX_FILE_SIZE * SIZE_THRESHOLD:
            continue
        formats_to_try.append((_video_audio_selector(dimension, resolution), None))

    formats_to_try.append((_video_audio_selector(dimension, 480), None))

    # Shorts may offer 360p only as separate video and audio streams.
    fallback = f'{_video_audio_selector("width", 360)}/18' if portrait else '18'
    formats_to_try.append((fallback, None))

    return formats_to_try


class YouTubePlatform(BasePlatform):
    """Обработчик для YouTube."""

    @property
    def name(self) -> str:
        return 'youtube'

    @property
    def url_pattern(self) -> str:
        return (
            r'(?:https?://)?(?:'
            r'(?:www\.|m\.)?youtube\.com/(?:watch|shorts/[A-Za-z0-9_-]+/?)|'
            r'(?:www\.)?youtu\.be/[A-Za-z0-9_-]+/?)'
            r'(?:\?[^#]*)?(?:#.*)?'
        )

    def is_valid_url(self, url: str) -> bool:
        if not super().is_valid_url(url):
            return False

        parsed = urlsplit(url if url.startswith(('http://', 'https://')) else f'https://{url}')
        if parsed.hostname in ('youtube.com', 'www.youtube.com', 'm.youtube.com') and parsed.path == '/watch':
            video_ids = parse_qs(parsed.query, keep_blank_values=True).get('v', [])
            return len(video_ids) == 1 and bool(re.fullmatch(r'[A-Za-z0-9_-]+', video_ids[0]))
        return True

    def get_format_options(self, info: dict) -> List[Tuple[str, Optional[dict]]]:
        """Выбор лучшего формата от высокого к низкому качеству."""
        return select_best_format(info)
