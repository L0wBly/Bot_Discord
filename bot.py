# bot.py

import os
import discord
from discord.ext import commands
from dotenv import load_dotenv

from utils.logger import logger  # Votre logger perso, dans utils/logger.py

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)


async def load_cogs():
    """
    Charge chaque fichier .py valide dans cogs/ exactement une seule fois.
    On ignore :
      - tout fichier dont le nom commence par '_'
      - tout fichier dont l'extension n'est pas '.py'
    """
    cogs_folder = os.path.join(os.path.dirname(__file__), "cogs")
    for filename in os.listdir(cogs_folder):
        if not filename.endswith(".py"):
            continue
        if filename.startswith("_"):
            continue

        ext = f"cogs.{filename[:-3]}"
        try:
            await bot.load_extension(ext)
            logger.info(f"✔️ Cog chargé : {ext}")
        except Exception as e:
            logger.error(f"❌ Erreur au chargement du cog {ext} : {e}")


@bot.event
async def on_ready():
    logger.info(f"🤖 {bot.user} est connecté et prêt !")


async def main():
    # 1. Charger tous les cogs avant de démarrer le bot
    await load_cogs()
    # 2. Lancer le bot
    await bot.start(TOKEN)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
