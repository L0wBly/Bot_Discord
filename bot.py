# bot.py

import os
import discord
from discord.ext import commands
from dotenv import load_dotenv

from utils.logger import logger  # Votre logger perso (dans utils/logger.py)

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# ───> 1) On crée le Bot en désactivant la help intégrée
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# Même si help_command=None, on appelle remove_command("help") juste après
# pour être sûr qu'aucune commande "help" existante ne subsiste.
bot.remove_command("help")


async def load_cogs():
    """
    Charge chaque fichier .py valide dans le dossier cogs/
    (ignore les fichiers commençant par '_' ou ceux qui n'ont pas l'extension .py).
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


# ───────────────────────────────────────────────────────────────────
# NOUVEAU : on intercepte tous les messages pour filtrer "!help" avant que
# Discord.py n'appelle automatiquement sa help par défaut.
@bot.event
async def on_message(message: discord.Message):
    # Si le message vient d’un bot, on ne fait rien.
    if message.author.bot:
        return

    contenu = message.content.strip()
    # Si le message commence précisément par "!help" ou "!help " (avec un espace),
    # on récupère le context et on invoque la commande personnalisée "help"
    if contenu.startswith("!help"):
        ctx = await bot.get_context(message)
        cmd = bot.get_command("help")    # c’est la méthode help_all dans help_cog.py
        if cmd:
            # On invoque explicitement notre commande help personnalisée
            await ctx.invoke(cmd)
            return

    # Sinon, on laisse Discord.py traiter normalement les autres commandes
    await bot.process_commands(message)
# ───────────────────────────────────────────────────────────────────


async def main():
    # 1. Charger tous les cogs avant de démarrer le bot
    await load_cogs()
    # 2. Lancer le bot
    await bot.start(TOKEN)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
