import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta, timezone
import os
import json
from utils.logger import logger
from config import (
    BUMP_CHANNEL_ID,
    BUMP_ROLE_ID,
    BUMP_COOLDOWN,
    REMIND_INTERVAL,
    DISBOARD_ID
)

DATA_FILE = "data/bump_status.json"

def load_last_bump():
    if not os.path.exists(DATA_FILE):
        logger.info("Aucun fichier bump_status.json trouvé, on part de zéro.")
        return None

    with open(DATA_FILE, "r") as f:
        try:
            data = json.load(f)
            logger.info(f"Dernier bump chargé : {data['last_bump']}")
            return datetime.fromisoformat(data["last_bump"])
        except Exception:
            logger.warning("Erreur de lecture de bump_status.json, on réinitialise.")
            return None

def save_last_bump(dt: datetime):
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump({"last_bump": dt.isoformat()}, f)
    logger.info(f"Nouveau bump enregistré : {dt.isoformat()}")

class BumpReminder(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.last_bump = load_last_bump()
        self.last_reminder_msg_id = None
        self.remind_task.start()
        logger.info("La tâche de rappel bump_reminder a démarré.")

    def cog_unload(self):
        self.remind_task.cancel()
        logger.info("Arrêt du module bump_reminder.")

    @tasks.loop(seconds=60)
    async def remind_task(self):
        await self.bot.wait_until_ready()
        now = datetime.now(timezone.utc)

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

        # Supprimer le rappel précédent s'il a +1h
        if self.last_reminder_msg_id:
            try:
                reminder_msg = await channel.fetch_message(self.last_reminder_msg_id)
                if (now - reminder_msg.created_at.replace(tzinfo=timezone.utc)).total_seconds() >= 3600:
                    await reminder_msg.delete()
                    logger.info("Rappel automatique supprimé après 1h sans bump.")
                    self.last_reminder_msg_id = None
            except discord.NotFound:
                self.last_reminder_msg_id = None
            except Exception as e:
                logger.warning(f"Erreur lors de la suppression auto du rappel expiré : {e}")

        # Vérifie s’il y a déjà un rappel très récent
        try:
            async for msg in channel.history(limit=1):
                if (
                    msg.author == self.bot.user
                    and msg.embeds
                    and msg.embeds[0].title
                    and "bump" in msg.embeds[0].title.lower()
                ):
                    if (now - msg.created_at.replace(tzinfo=timezone.utc)).total_seconds() < REMIND_INTERVAL:
                        return
        except Exception as e:
            logger.warning(f"Erreur lors de la lecture du dernier message : {e}")

        try:
            await self.purge_old_reminders(channel)
        except Exception as e:
            logger.warning(f"Erreur purge anciens rappels : {e}")

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
            msg = await channel.send(content=role.mention, embed=embed)
            self.last_reminder_msg_id = msg.id
            logger.info(f"Rappel envoyé dans #{channel.name} à {now.isoformat()}")
        except Exception as e:
            logger.error(f"Erreur envoi du rappel bump : {e}")

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
                logger.warning(f"Erreur suppression ancien rappel : {e}")

    async def purge_old_disboard(self, channel: discord.TextChannel, except_id: int = None):
        async for msg in channel.history(limit=100):
            if msg.author.id != DISBOARD_ID:
                continue
            if except_id and msg.id == except_id:
                continue
            content = msg.content.lower()
            desc = (msg.embeds[0].description.lower() if msg.embeds else "") or ""
            title = (msg.embeds[0].title.lower() if msg.embeds else "") or ""
            if "bump effectué" in content or "bump effectué" in desc or "bump réussi" in title:
                try:
                    await msg.delete()
                    logger.info("Ancien message Disboard supprimé.")
                except Exception as e:
                    logger.warning(f"Erreur suppression message Disboard : {e}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if (
            message.channel.id == BUMP_CHANNEL_ID
            and message.author.id == DISBOARD_ID
        ):
            content = message.content.lower()
            desc = (message.embeds[0].description.lower() if message.embeds else "") or ""
            title = (message.embeds[0].title.lower() if message.embeds else "") or ""
            if "bump effectué" in content or "bump effectué" in desc or "bump réussi" in title:
                now = datetime.now(timezone.utc)
                self.last_bump = now
                save_last_bump(now)
                logger.info(f"Bump détecté à {now.isoformat()}")
                try:
                    await self.purge_old_reminders(message.channel)
                except Exception as e:
                    logger.warning(f"Erreur purge reminder dans on_message : {e}")
                try:
                    await self.purge_old_disboard(message.channel, except_id=message.id)
                except Exception as e:
                    logger.warning(f"Erreur purge disboard dans on_message : {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(BumpReminder(bot))
