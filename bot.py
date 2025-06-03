import os
import discord
from discord.ext import commands
from dotenv import load_dotenv

from utils.logger import logger  # Toujours après avoir supprimé toute config logging ici !

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

async def load_cogs():
    for filename in os.listdir("./cogs"):
        if filename.endswith(".py"):
            ext = f"cogs.{filename[:-3]}"
            try:
                await bot.load_extension(ext)
                logger.info(f"Cog chargé : {ext}")
            except Exception as e:
                logger.error(f"Erreur au chargement du cog {ext}: {e}")

@bot.event
async def on_ready():
    logger.info(f"{bot.user} est connecté !")

async def main():
    await load_cogs()
    await bot.start(TOKEN)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
