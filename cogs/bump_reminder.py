import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta, timezone
import os
import json
from utils.logger import logger
from config import (
    BUMP_CHANNEL_ID,   # ID du salon où on fait les bumps/rappels
    BUMP_ROLE_ID,      # ID du rôle à ping quand on envoie le rappel
    BUMP_COOLDOWN,     # cooldown (en secondes) entre deux bumps
    REMIND_INTERVAL,   # intervalle (en secondes) minimum entre deux envois de rappel
    DISBOARD_ID        # ID du bot Disboard (pour détecter "Bump effectué")
)

DATA_FILE = "data/bump_status.json"


def load_last_bump():
    """Charge la date/heure du dernier bump depuis le fichier JSON, ou None si pas de fichier."""
    if not os.path.exists(DATA_FILE):
        logger.info("Aucun fichier bump_status.json trouvé, on part de zéro.")
        return None

    with open(DATA_FILE, "r") as f:
        try:
            data = json.load(f)
            logger.info(f"Dernier bump chargé : {data['last_bump']}")
            # fromisoformat gère le timezone si on a stocké un isoformat UTC
            return datetime.fromisoformat(data["last_bump"])
        except Exception:
            logger.warning("Erreur de lecture de bump_status.json, on réinitialise.")
            return None


def save_last_bump(dt: datetime):
    """Enregistre la date/heure du dernier bump dans data/bump_status.json."""
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump({"last_bump": dt.isoformat()}, f)
    logger.info(f"Nouveau bump enregistré : {dt.isoformat()}")



class BumpReminder(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.last_bump = load_last_bump()
        self.remind_task.start()
        logger.info("La tâche de rappel bump_reminder a démarré.")

    def cog_unload(self):
        self.remind_task.cancel()
        logger.info("Arrêt du module bump_reminder.")

    @tasks.loop(seconds=60)
    async def remind_task(self):
        await self.bot.wait_until_ready()
        now = datetime.now(timezone.utc)
        # Blocage entre 22h00 UTC et 09h00 UTC (minuit-11h heure FR)
        if now.hour >= 22 or now.hour < 9:
            return

        channel = self.bot.get_channel(BUMP_CHANNEL_ID)
        if not channel or not channel.guild:
            logger.warning("Impossible de récupérer le salon BUMP_CHANNEL_ID.")
            return
        role = channel.guild.get_role(BUMP_ROLE_ID)
        if not role:
            logger.warning("Impossible de récupérer le rôle BUMP_ROLE_ID.")
            return

        last_bump_dt = self.last_bump or (now - timedelta(hours=2))
        time_since_bump = (now - last_bump_dt).total_seconds()
        if time_since_bump < BUMP_COOLDOWN:
            return

        # Check si un rappel récent existe déjà
        try:
            async for msg in channel.history(limit=1):
                is_last_reminder = (
                    msg.author == self.bot.user
                    and msg.embeds
                    and msg.embeds[0].title
                    and "bump" in msg.embeds[0].title.lower()
                )
                if is_last_reminder:
                    time_since_last_reminder = (now - msg.created_at.replace(tzinfo=timezone.utc)).total_seconds()
                    if time_since_last_reminder < REMIND_INTERVAL:
                        return
        except Exception as e:
            logger.warning(f"Erreur lors de la lecture du dernier message pour reminders : {e}")

        # Purge anciens rappels (hors le plus récent)
        try:
            await self.purge_old_reminders(channel)
        except Exception as e:
            logger.warning(f"Impossible de purger les anciens rappels avant envoi du nouveau : {e}")

        # Envoi du rappel
        try:
            embed = discord.Embed(
                title="✨ C'est l'heure du bump ! ✨",
                description=(
                    "Le serveur a besoin de **visibilité** 🚀\n"
                    "Merci de faire un **/bump** pour soutenir la commu !\n"
                    "> *Ce message disparaîtra dès qu'un bump sera effectué.*"
                ),
                color=discord.Color.purple()
            )
            embed.set_thumbnail(url="https://cdn-icons-png.flaticon.com/512/565/565547.png")
            embed.set_footer(text="Merci à tous pour votre soutien ❤️")
            await channel.send(content=role.mention, embed=embed)
            logger.info(f"Rappel envoyé dans #{channel.name} ({channel.id}) à {now.isoformat()}")
        except Exception as e:
            logger.error(f"Erreur lors de l'envoi du rappel bump_reminder : {e}")

    async def purge_old_reminders(self, channel: discord.TextChannel):
        reminder_msgs = []
        async for msg in channel.history(limit=100):
            if (
                msg.author == self.bot.user
                and msg.embeds
                and msg.embeds[0].title
                and "bump" in msg.embeds[0].title.lower()
            ):
                reminder_msgs.append(msg)
        reminder_msgs.sort(key=lambda m: m.created_at, reverse=True)
        for old_msg in reminder_msgs[1:]:
            try:
                await old_msg.delete()
                logger.info("Ancien rappel supprimé.")
            except Exception as e:
                logger.warning(f"Impossible de supprimer un ancien rappel : {e}")

    async def purge_old_disboard(self, channel: discord.TextChannel, except_id: int = None):
        async for msg in channel.history(limit=100):
            if msg.author.id != DISBOARD_ID:
                continue
            if except_id is not None and msg.id == except_id:
                continue
            content_lower = (msg.content or "").lower()
            embed = msg.embeds[0] if msg.embeds else None
            embed_desc = (embed.description or "").lower() if (embed and embed.description) else ""
            embed_title = (embed.title or "").lower() if (embed and embed.title) else ""
            if "bump effectué" in content_lower or "bump effectué" in embed_desc or "bump réussi" in embed_title:
                try:
                    await msg.delete()
                    logger.info("Ancien message Disboard 'Bump effectué !' supprimé.")
                except Exception as e:
                    logger.warning(f"Impossible de supprimer un message Disboard : {e}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Détecte UNIQUEMENT les bumps Disboard (ne touche à rien d'autre !)
        if (
            message.channel.id == BUMP_CHANNEL_ID
            and message.author.id == DISBOARD_ID
        ):
            content_lower = (message.content or "").lower()
            embed = message.embeds[0] if message.embeds else None
            embed_desc = (embed.description or "").lower() if (embed and embed.description) else ""
            embed_title = (embed.title or "").lower() if (embed and embed.title) else ""
            if "bump effectué" in content_lower or "bump effectué" in embed_desc or "bump réussi" in embed_title:
                now = datetime.now(timezone.utc)
                self.last_bump = now
                save_last_bump(now)
                logger.info(
                    f"Bump détecté à {now.strftime('%Y-%m-%d %H:%M:%S')} "
                    f"dans #{message.channel.name} ({message.channel.id})"
                )
                try:
                    await self.purge_old_reminders(message.channel)
                except Exception as e:
                    logger.warning(f"Erreur purge_old_reminders dans on_message : {e}")
                try:
                    await self.purge_old_disboard(message.channel, except_id=message.id)
                except Exception as e:
                    logger.warning(f"Erreur purge_old_disboard dans on_message : {e}")


# ───────────────────────────────────────────────────────────────────────────────
# >> N O T E   I M P O R T A N T E : la fonction setup **doit** être en-dehors
#    de la classe. Discord.py la cherche à la racine du fichier.
#
async def setup(bot: commands.Bot):
    await bot.add_cog(BumpReminder(bot))
