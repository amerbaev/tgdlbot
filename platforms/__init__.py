"""Platform handlers for video downloaders."""

from .base import BasePlatform
from .youtube import YouTubePlatform
from .instagram import InstagramPlatform

__all__ = ['BasePlatform', 'YouTubePlatform', 'InstagramPlatform']
