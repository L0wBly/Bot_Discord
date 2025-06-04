# utils/logger.py

import logging
import os

LOGS_DIR = "logs"
os.makedirs(LOGS_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOGS_DIR, "bot.log")

logging.basicConfig(
    level=logging.DEBUG,  # DEBUG pour tout voir de ton bot, sinon INFO
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8", mode="w"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("BotDiscord")

# Filtrer les logs trop verbeux des bibliothèques tierces
logging.getLogger("discord").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)
logging.getLogger("websockets").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
