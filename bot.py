import os
import sys
import discord
from discord.ext import commands
from dotenv import load_dotenv
import traceback

from utils.logger import logger

# 🔒 Ne lancer que via systemd
if os.getenv("INVOCATION_BY_SYSTEMD") != "1":
    print("❌ Ce bot ne peut être lancé qu'en tant que service systemd.")
    sys.exit(1)

# Chargement du token et configuration
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)
bot.remove_command("help")

async def load_cogs():
    cogs_folder = os.path.join(os.path.dirname(__file__), "cogs")
    for filename in os.listdir(cogs_folder):
        if not filename.endswith(".py") or filename.startswith("_"):
            continue
        ext = f"cogs.{filename[:-3]}"
        try:
            await bot.load_extension(ext)
            logger.info(f"✔️ Cog chargé : {ext}")
        except Exception as e:
            logger.error(f"❌ Erreur au chargement du cog {ext} : {e}\n{traceback.format_exc()}")

@bot.event
async def on_ready():
    logger.info(f"🤖 {bot.user} est connecté et prêt !")

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    contenu = message.content.strip().lower()
    if contenu == "!help":
        ctx = await bot.get_context(message)
        cmd = bot.get_command("help")
        if cmd:
            await ctx.invoke(cmd)
            return

    await bot.process_commands(message)

async def main():
    async with bot:
        await load_cogs()
        await bot.start(TOKEN)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
