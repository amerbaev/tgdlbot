"""Base platform interface."""

from abc import ABC, abstractmethod
from typing import Optional, List, Tuple
import re
import logging

logger = logging.getLogger(__name__)


class BasePlatform(ABC):
    """Базовый класс для платформ."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Название платформы."""

    @property
    @abstractmethod
    def url_pattern(self) -> str:
        """Регулярное выражение для URL."""

    def is_valid_url(self, url: str) -> bool:
        """Проверка, является ли URL ссылкой на эту платформу.

        Args:
            url: URL для проверки

        Returns:
            True если URL валиден для этой платформы
        """
        return bool(re.match(self.url_pattern, url))

    @abstractmethod
    def get_format_options(self, info: dict) -> List[Tuple[str, Optional[dict]]]:
        """Получить опции формата для скачивания.

        Args:
            info: Метаданные видео от yt-dlp

        Returns:
            Список кортежей (format_selector, extractor_args)
        """
        pass
