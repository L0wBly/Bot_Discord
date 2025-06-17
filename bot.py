import os
import discord
from discord.ext import commands
from dotenv import load_dotenv

from utils.logger import logger

# Chargement du token et configuration
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# Intents complets pour toutes les fonctionnalités du bot
intents = discord.Intents.all()

# Commande prefix (ici "!")
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)
bot.remove_command("help")

async def load_cogs():
    """
    Charge dynamiquement chaque extension/cog du dossier cogs/
    """
    cogs_folder = os.path.join(os.path.dirname(__file__), "cogs")
    for filename in os.listdir(cogs_folder):
        if not filename.endswith(".py") or filename.startswith("_"):
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

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    contenu = message.content.strip()
    if contenu.startswith("!help"):
        ctx = await bot.get_context(message)
        cmd = bot.get_command("help")
        if cmd:
            await ctx.invoke(cmd)
            return
    await bot.process_commands(message)

# ✅ FIX ici : utilise le bon contexte async
async def main():
    async with bot:
        await load_cogs()
        await bot.start(TOKEN)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
