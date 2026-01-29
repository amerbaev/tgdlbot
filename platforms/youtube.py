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

    # Проверяем 1080p и 720p
    for target_height, extractor_args in FORMAT_CANDIDATES[:2]:  # 1080, 720
        estimated = estimate_format_size(info, target_height)

        # Пропускаем если:
        # 1. Размер неизвестн (не можем оценить)
        # 2. Размер слишком большой
        if estimated is None or estimated > MAX_FILE_SIZE * SIZE_THRESHOLD:
            continue

        # Размер известен и приемлем - добавляем
        format_selector = (
            f'bestvideo[height<={target_height}][ext=mp4]+bestaudio[ext=m4a]/'
            f'bestvideo[height<={target_height}]+bestaudio'
        )
        formats_to_try.append((format_selector, extractor_args))

    # Всегда добавляем 480p (без extractor_args для совместимости)
    format_selector_480 = (
        'bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/'
        'bestvideo[height<=480]+bestaudio'
    )
    formats_to_try.append((format_selector_480, None))

    # Fallback на 360p (формат 18)
    formats_to_try.append(('18', None))

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
