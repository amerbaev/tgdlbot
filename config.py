import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

# Необязательный файл cookies Instagram в формате Netscape.
INSTAGRAM_COOKIES_FILE = os.getenv('INSTAGRAM_COOKIES_FILE', '').strip()

# Максимальный размер видео для Telegram (50MB - лимит для ботов)
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

# Директория для временных файлов
DOWNLOAD_DIR = 'downloads'
