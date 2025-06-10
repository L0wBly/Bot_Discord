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
    # Ce listener NE gère que le help custom, puis laisse le reste aux autres cogs via process_commands.
    if message.author.bot:
        return
    # Si tu veux un !help custom, il se gère ICI (sinon, laisse le cog help_cog gérer tout seul)
    contenu = message.content.strip()
    if contenu.startswith("!help"):
        ctx = await bot.get_context(message)
        cmd = bot.get_command("help")
        if cmd:
            await ctx.invoke(cmd)
            return
    await bot.process_commands(message)  # NE PAS SUPPRIMER, sinon les autres cogs ne reçoivent pas les commandes

async def main():
    await load_cogs()
    print(">>> BIENTÔT BOT START !")
    await bot.start(TOKEN)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
