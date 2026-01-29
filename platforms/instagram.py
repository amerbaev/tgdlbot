"""Instagram platform handler."""

from typing import List, Tuple, Optional
from .base import BasePlatform


class InstagramPlatform(BasePlatform):
    """Обработчик для Instagram."""

    @property
    def name(self) -> str:
        return 'instagram'

    @property
    def url_pattern(self) -> str:
        # Поддерживает посты и Reels
        return r'^(https?://)?(www\.)?instagram\.com/(p|reel)/.+$'

    def get_format_options(self, info: dict) -> List[Tuple[str, Optional[dict]]]:
        """Возвращает лучшее доступное качество для Instagram.

        Instagram использует простую логику - всегда качаем лучшее качество.
        """
        return [('best[ext=mp4]/best', None)]
