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
        # Chargement du dernier bump (datetime ou None)
        self.last_bump = load_last_bump()
        # Lancement de la tâche qui tourne toutes les 60 s
        self.remind_task.start()
        logger.info("La tâche de rappel bump_reminder a démarré.")

    def cog_unload(self):
        # Quand on unload le Cog, on arrête la loop
        self.remind_task.cancel()
        logger.info("Arrêt du module bump_reminder.")

    @tasks.loop(seconds=60)
    async def remind_task(self):
        """Boucle qui vérifie toutes les 60 s si on doit envoyer un nouveau rappel."""
        await self.bot.wait_until_ready()
        now = datetime.now(timezone.utc)

        # Ne pas envoyer de rappel entre 00h00 et 10h59 (UTC)
        if 0 <= now.hour < 11:
            return

        # Récupération du canal configuré pour les bumps
        channel = self.bot.get_channel(BUMP_CHANNEL_ID)
        if not channel or not channel.guild:
            logger.warning("Impossible de récupérer le salon BUMP_CHANNEL_ID.")
            return

        # Récupération du rôle à mentionner
        role = channel.guild.get_role(BUMP_ROLE_ID)
        if not role:
            logger.warning("Impossible de récupérer le rôle BUMP_ROLE_ID.")
            return

        # 1) On calcule le temps écoulé depuis le dernier bump
        last_bump_dt = self.last_bump or (now - timedelta(hours=2))
        time_since_bump = (now - last_bump_dt).total_seconds()
        if time_since_bump < BUMP_COOLDOWN:
            # On n'a pas dépassé le cooldown : pas de rappel
            return

        # 2) On regarde si un rappel récent a déjà été envoyé
        try:
            # On prend juste le dernier message du canal pour vérifier s'il s'agit déjà d'un rappel
            async for msg in channel.history(limit=1):
                is_last_reminder = (
                    msg.author == self.bot.user
                    and msg.embeds
                    and msg.embeds[0].title
                    and "bump" in msg.embeds[0].title.lower()
                )
                if is_last_reminder:
                    # Calcul du temps écoulé depuis le dernier rappel
                    time_since_last_reminder = (now - msg.created_at.replace(tzinfo=timezone.utc)).total_seconds()
                    if time_since_last_reminder < REMIND_INTERVAL:
                        # Il y a déjà un rappel récent : on attend encore
                        return
        except Exception as e:
            logger.warning(f"Erreur lors de la lecture du dernier message pour reminders : {e}")

        # 3) Avant d'envoyer le nouveau rappel, on purge tous les anciens rappels 
        #    (sauf celui qu'on va poster tout de suite). 
        try:
            await self.purge_old_reminders(channel)
        except Exception as e:
            logger.warning(f"Impossible de purger les anciens rappels avant envoi du nouveau : {e}")

        # 4) Construction & envoi de l'embed de rappel
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

            # On mentionne le rôle puis on envoie l'embed
            await channel.send(content=role.mention, embed=embed)
            logger.info(f"Rappel envoyé dans #{channel.name} ({channel.id}) à {now.isoformat()}")
        except Exception as e:
            logger.error(f"Erreur lors de l'envoi du rappel bump_reminder : {e}")

    async def purge_old_reminders(self, channel: discord.TextChannel):
        """
        Supprime tous les anciens messages « C'est l'heure du bump ! »
        postés par le bot, sauf le plus récent (celui qu'on va laisser).
        """
        reminder_msgs = []
        # On cherche dans les 100 derniers messages du canal
        async for msg in channel.history(limit=100):
            if (
                msg.author == self.bot.user
                and msg.embeds
                and msg.embeds[0].title
                and "bump" in msg.embeds[0].title.lower()
            ):
                reminder_msgs.append(msg)

        # On trie du plus récent au plus ancien
        reminder_msgs.sort(key=lambda m: m.created_at, reverse=True)

        # On supprime tous sauf le plus récent (index 0)
        for old_msg in reminder_msgs[1:]:
            try:
                await old_msg.delete()
                logger.info("Ancien rappel supprimé.")
            except Exception as e:
                logger.warning(f"Impossible de supprimer un ancien rappel : {e}")

    async def purge_old_disboard(self, channel: discord.TextChannel, except_id: int = None):
        """
        Supprime tous les anciens messages Disboard « Bump effectué ! » 
        sauf celui dont l'ID est `except_id`.
        """
        async for msg in channel.history(limit=100):
            if msg.author.id != DISBOARD_ID:
                continue

            # Si on est sur celui qu'on vient de recevoir, on le garde
            if except_id is not None and msg.id == except_id:
                continue

            content_lower = (msg.content or "").lower()
            embed = msg.embeds[0] if msg.embeds else None
            embed_desc = (embed.description or "").lower() if (embed and embed.description) else ""
            embed_title = (embed.title or "").lower() if (embed and embed.title) else ""

            # On vérifie que le message contient bien "bump effectué" ou "bump réussi"
            if "bump effectué" in content_lower or "bump effectué" in embed_desc or "bump réussi" in embed_title:
                try:
                    await msg.delete()
                    logger.info("Ancien message Disboard 'Bump effectué !' supprimé.")
                except Exception as e:
                    logger.warning(f"Impossible de supprimer un message Disboard : {e}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """
        Quand on détecte un nouveau message Disboard « Bump effectué ! » dans le channel BUMP_CHANNEL_ID :
          1) On enregistre la date/heure du bump,
          2) On purge tous les anciens rappels sauf le dernier,
          3) On purge tous les anciens messages Disboard sauf celui qu'on vient de recevoir.
        """
        # On ne traite qu'un message venant du canal bump configuré, et de l'auteur DISBOARD_ID
        if (
            message.channel.id == BUMP_CHANNEL_ID
            and message.author.id == DISBOARD_ID
        ):
            # On cherche "bump effectué" dans content ou embed.description ou embed.title
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

                # 1) On purge tous les anciens rappels sauf le plus récent
                try:
                    await self.purge_old_reminders(message.channel)
                except Exception as e:
                    logger.warning(f"Erreur purge_old_reminders dans on_message : {e}")

                # 2) On purge tous les anciens Disboard sauf celui-ci
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
