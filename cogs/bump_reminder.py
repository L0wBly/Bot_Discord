import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta, timezone
import os
import json
from utils.logger import logger
from config import BUMP_CHANNEL_ID, BUMP_ROLE_ID, BUMP_COOLDOWN, REMIND_INTERVAL, DISBOARD_ID

DATA_FILE = "data/bump_status.json"

def load_last_bump():
    if not os.path.exists(DATA_FILE):
        logger.info("Aucun fichier bump_status.json, on part de zéro.")
        return None
    with open(DATA_FILE, "r") as f:
        data = json.load(f)
        logger.info(f"Dernier bump chargé : {data['last_bump']}")
        return datetime.fromisoformat(data["last_bump"])

def save_last_bump(dt):
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump({"last_bump": dt.isoformat()}, f)
    logger.info(f"Nouveau bump enregistré : {dt.isoformat()}")

class BumpReminder(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.last_bump = load_last_bump()
        self.last_reminder_message_id = None
        self.remind_task.start()
        logger.info("La task de rappel bump_reminder a démarré.")

    def cog_unload(self):
        logger.info("Arrêt du module bump_reminder")
        self.remind_task.cancel()

    @tasks.loop(seconds=60)
    async def remind_task(self):
        await self.bot.wait_until_ready()
        now = datetime.now(timezone.utc)
        channel = self.bot.get_channel(BUMP_CHANNEL_ID)
        if not channel or not channel.guild:
            logger.warning("Channel ou guild introuvable")
            return
        role = channel.guild.get_role(BUMP_ROLE_ID)
        if not role:
            logger.warning("Rôle à ping introuvable")
            return

        # 1. On vérifie le temps depuis le dernier bump
        last_bump = self.last_bump or now - timedelta(hours=2)
        time_since_bump = (now - last_bump).total_seconds()
        if time_since_bump < BUMP_COOLDOWN:
            return

        # 2. On regarde le dernier message dans le salon
        try:
            async for msg in channel.history(limit=1, oldest_first=False):
                is_last_reminder = False
                if msg.author == self.bot.user:
                    if (msg.embeds and msg.embeds[0].title and "bump" in msg.embeds[0].title.lower()):
                        is_last_reminder = True
                if is_last_reminder:
                    # Si le dernier message est déjà un rappel, on vérifie la date
                    time_since_last_reminder = (now - msg.created_at.replace(tzinfo=timezone.utc)).total_seconds()
                    if time_since_last_reminder < REMIND_INTERVAL:
                        # On attend encore avant de renvoyer un rappel
                        return
        except Exception as e:
            logger.warning(f"Erreur lecture dernier message: {e}")

        try:
            # Supprimer tous les anciens rappels sauf le dernier qui va être posté
            await self.purge_old_reminders(channel)

            # ------ MESSAGE DE RAPPEL STYLÉ EN EMBED ------
            embed = discord.Embed(
                title="✨ C'est l'heure du bump ! ✨",
                description=(
                    "Le serveur a besoin de **visibilité** 🚀\n"
                    "Merci de faire un **/bump** pour soutenir la commu !\n"
                ),
                color=discord.Color.purple()
            )
            embed.set_thumbnail(url="https://cdn-icons-png.flaticon.com/512/565/565547.png")
            embed.set_footer(text="Merci à tous pour votre soutien ❤️")

            # Ping dans le champ content pour la notif
            reminder = await channel.send(content=role.mention, embed=embed)
            self.last_reminder_message_id = reminder.id
            logger.info(f"Rappel envoyé dans #{channel.name} ({channel.id}) à {now.isoformat()}")
        except Exception as e:
            logger.error(f"Erreur lors de l'envoi du rappel: {e}")

    async def purge_old_reminders(self, channel):
        """Supprime tous les anciens rappels du bot sauf le plus récent."""
        reminder_msgs = []
        async for msg in channel.history(limit=200, oldest_first=False):
            is_reminder = False
            if msg.author == self.bot.user:
                if msg.embeds and msg.embeds[0].title and "bump" in msg.embeds[0].title.lower():
                    is_reminder = True
                if "Il est temps de faire un **/bump** !" in msg.content:
                    is_reminder = True
            if is_reminder:
                reminder_msgs.append(msg)
        # Trie du plus récent au plus ancien
        reminder_msgs.sort(key=lambda m: m.created_at, reverse=True)
        # Supprime tous sauf le plus récent
        for old_msg in reminder_msgs[1:]:
            try:
                await old_msg.delete()
                logger.info("Ancien rappel supprimé.")
            except Exception as e:
                logger.warning(f"Impossible de supprimer un rappel : {e}")

    async def purge_old_disboard(self, channel, except_id=None):
        """Supprime tous les anciens messages Disboard 'Bump effectué !' sauf le dernier (except_id)."""
        disboard_msgs = []
        async for msg in channel.history(limit=200, oldest_first=True):
            if (
                msg.author.id == DISBOARD_ID and
                (except_id is None or msg.id != except_id) and
                (
                    (msg.content and "bump effectué" in msg.content.lower()) or
                    (msg.embeds and msg.embeds[0].description and "bump effectué" in msg.embeds[0].description.lower()) or
                    (msg.embeds and msg.embeds[0].title and "bump réussi" in msg.embeds[0].title.lower())
                )
            ):
                disboard_msgs.append(msg)
        # Trie du plus ancien au plus récent
        disboard_msgs.sort(key=lambda m: m.created_at)
        # Supprime tous sauf le plus récent
        for old_msg in disboard_msgs[:-1]:
            try:
                await old_msg.delete()
                logger.info("Ancien message Disboard 'Bump effectué !' supprimé.")
            except Exception as e:
                logger.warning(f"Impossible de supprimer un message Disboard : {e}")

    @commands.Cog.listener()
    async def on_message(self, message):
        # Détecte le message Disboard “Bump effectué !”
        if (
            message.channel.id == BUMP_CHANNEL_ID
            and message.author.id == DISBOARD_ID
            and (
                (message.content and "bump effectué" in message.content.lower())
                or (message.embeds and message.embeds[0].description and "bump effectué" in message.embeds[0].description.lower())
                or (message.embeds and message.embeds[0].title and "bump réussi" in message.embeds[0].title.lower())
            )
        ):
            now = datetime.now(timezone.utc)
            self.last_bump = now
            save_last_bump(now)
            logger.info(
                f"Bump détecté à {now.strftime('%Y-%m-%d %H:%M:%S')} "
                f"dans #{message.channel.name} ({message.channel.id})"
            )
            channel = message.channel

            # Supprimer tous les anciens rappels
            await self.purge_old_reminders(channel)
            # Supprimer tous les anciens Disboard sauf ce message (le tout dernier)
            await self.purge_old_disboard(channel, except_id=message.id)

async def setup(bot):
    await bot.add_cog(BumpReminder(bot))
