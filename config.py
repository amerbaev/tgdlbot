import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

# Максимальный размер видео для Telegram (50MB - лимит для ботов)
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

# Качество видео
VIDEO_FORMAT = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'

# Директория для временных файлов
DOWNLOAD_DIR = 'downloads'
