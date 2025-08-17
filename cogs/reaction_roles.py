# cogs/role_panel.py
import os
import json
import discord
from discord.ext import commands, tasks
from config import (
    REACTION_ROLE_CHANNEL_ID,
    ROLE_REGARDE_ANIME_ID,
    ROLE_LECTEUR_SCANS_ID,
    ROLE_LECTEUR_MANGA_ID,
    ROLE_HINA_TACHIBANA_ID,
    ROLE_RUI_TACHIBANA_ID,
    ROLE_MOMO_KASHIWABARA_ID,
    ROLE_MIU_ASHIHARA_ID,
    ROLE_NATSUO_FUJII_ID,
    ROLE_FUMIYA_KURIMOTO_ID,
    ROLE_POETE_ID,
    ROLE_ECRIVAIN_ID,
    ROLE_BUMP_ID,
    ROLE_NOTIF_NEWS,   # tel que dans ton config
)

# ---- Map Emoji -> (Nom lisible, role_id)
EMOJI_ROLE_MAP = {
    "📺": ("Regarde l'anime", ROLE_REGARDE_ANIME_ID),
    "📖": ("Lecteur des scans", ROLE_LECTEUR_SCANS_ID),
    "📚": ("Lecteur du manga", ROLE_LECTEUR_MANGA_ID),
    "🟠": ("Hina Tachibana", ROLE_HINA_TACHIBANA_ID),
    "🔵": ("Rui Tachibana", ROLE_RUI_TACHIBANA_ID),
    "🟣": ("Momo Kashibawara", ROLE_MOMO_KASHIWABARA_ID),
    "🟢": ("Miu Ashihara", ROLE_MIU_ASHIHARA_ID),
    "⚫": ("Natsuo Fujii", ROLE_NATSUO_FUJII_ID),
    "🟤": ("Fumiya Kurimoto", ROLE_FUMIYA_KURIMOTO_ID),
    "📝": ("Poète", ROLE_POETE_ID),
    "✍️": ("Écrivain", ROLE_ECRIVAIN_ID),
    "🌐": ("Bump", ROLE_BUMP_ID),
    "🔔": ("Notifications News", ROLE_NOTIF_NEWS),
}

# Stats (optionnel, tu avais déjà)
DATA_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "role_stats.json")

# Panneau : on garde l'ID du message pour l'éditer (pas recréer)
PANEL_STATE_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "role_panel.json")


def read_stats():
    if not os.path.exists(DATA_PATH):
        return {role_name: 0 for role_name, _ in EMOJI_ROLE_MAP.values()}
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def write_stats(stats):
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)


class RoleStats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # init fichier stats si absent
        if not os.path.exists(DATA_PATH):
            write_stats({role_name: 0 for role_name, _ in EMOJI_ROLE_MAP.values()})

        # auto-sync panneau au démarrage puis toutes les 5 min
        self.panel_auto_sync.start()

    # -------------------- Helpers panneau --------------------

    def _save_panel_msg_id(self, message_id: int):
        os.makedirs(os.path.dirname(PANEL_STATE_FILE), exist_ok=True)
        with open(PANEL_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({"message_id": message_id}, f)

    def _load_panel_msg_id(self) -> int | None:
        if not os.path.exists(PANEL_STATE_FILE):
            return None
        try:
            with open(PANEL_STATE_FILE, "r", encoding="utf-8") as f:
                return (json.load(f) or {}).get("message_id")
        except Exception:
            return None

    def _build_roles_embed(self, guild: discord.Guild) -> discord.Embed:
        embed = discord.Embed(
            title="🌟 Choisis ton rôle via les réactions ! 🌟",
            description=(
                "**Réagis avec l'emoji correspondant pour obtenir ou retirer un rôle :**\n\n"
                "Clique sur un emoji ci-dessous pour gérer tes rôles !"
            ),
            color=discord.Color.purple()
        )
        # un field par rôle + le compteur réel (membres ayant le rôle)
        for emoji, (role_name, role_id) in EMOJI_ROLE_MAP.items():
            role = guild.get_role(int(role_id))
            count = len(role.members) if role else 0
            embed.add_field(name=f"{emoji}  {role_name}", value=f"**{count}** membre(s)", inline=False)
        return embed

    async def _ensure_reactions(self, message: discord.Message):
        """Ajoute sur le message les réactions manquantes par rapport à EMOJI_ROLE_MAP."""
        existing = {str(r.emoji) for r in message.reactions}
        for emoji in EMOJI_ROLE_MAP.keys():
            if emoji not in existing:
                try:
                    await message.add_reaction(emoji)
                except discord.HTTPException:
                    pass

    async def _ensure_panel_exists_and_synced(self):
        """Crée/édite le panneau dans le salon configuré et s'assure que tout est à jour."""
        channel = self.bot.get_channel(int(REACTION_ROLE_CHANNEL_ID))
        if not isinstance(channel, discord.TextChannel) or not channel.guild:
            return

        # (re)calcul des stats pour disque (facultatif)
        await self.update_stats(channel.guild)

        embed = self._build_roles_embed(channel.guild)

        # essayer d'éditer le panneau existant
        panel_id = self._load_panel_msg_id()
        message = None
        if panel_id:
            try:
                message = await channel.fetch_message(panel_id)
                await message.edit(embed=embed)
                await self._ensure_reactions(message)
                return
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                message = None  # on recréera

        # sinon, on crée le panneau et on mémorise son ID
        try:
            message = await channel.send(embed=embed)
            for emoji in EMOJI_ROLE_MAP.keys():
                try:
                    await message.add_reaction(emoji)
                except discord.HTTPException:
                    pass
            self._save_panel_msg_id(message.id)
        except discord.Forbidden:
            # pas la peine d'insister sans permissions
            return

    async def update_stats(self, guild: discord.Guild):
        stats = {role_name: 0 for role_name, _ in EMOJI_ROLE_MAP.values()}
        for role_name, role_id in [v for v in EMOJI_ROLE_MAP.values()]:
            role = guild.get_role(int(role_id))
            if role:
                stats[role_name] = len(role.members)
        write_stats(stats)

    async def _refresh_panel_message(self, guild: discord.Guild):
        """Met à jour l'embed du panneau avec les compteurs courants."""
        channel = guild.get_channel(int(REACTION_ROLE_CHANNEL_ID))
        if not isinstance(channel, discord.TextChannel):
            return
        msg_id = self._load_panel_msg_id()
        if not msg_id:
            return
        try:
            msg = await channel.fetch_message(msg_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return
        embed = self._build_roles_embed(guild)
        await msg.edit(embed=embed)
        await self._ensure_reactions(msg)

    # -------------------- Commande admin (setup initial / forcage) --------------------

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def setup_roles(self, ctx):
        """Crée/Met à jour le panneau d'auto-rôles (à lancer une fois)."""
        if ctx.channel.id != int(REACTION_ROLE_CHANNEL_ID):
            m = await ctx.send("❌ Utilise cette commande dans le salon d'auto-rôle configuré.")
            await ctx.message.delete()
            await m.delete(delay=4)
            return

        await self._ensure_panel_exists_and_synced()
        try:
            await ctx.message.delete(delay=3)
        except Exception:
            pass

    # -------------------- Auto-sync périodique (pas besoin de refaire la commande) --------------------

    @tasks.loop(minutes=5)
    async def panel_auto_sync(self):
        await self.bot.wait_until_ready()
        await self._ensure_panel_exists_and_synced()

    @panel_auto_sync.before_loop
    async def _before_sync(self):
        await self.bot.wait_until_ready()

    # -------------------- Réactions : on agit uniquement sur le panneau --------------------

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        panel_id = self._load_panel_msg_id()
        # si on a le panel_id, on ignore toute réaction ailleurs
        if panel_id and payload.message_id != panel_id:
            return
        if payload.channel_id != int(REACTION_ROLE_CHANNEL_ID):
            return

        emoji = str(payload.emoji)
        if emoji not in EMOJI_ROLE_MAP:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        member = guild.get_member(payload.user_id)
        if not member or member.bot:
            return

        role_name, role_id = EMOJI_ROLE_MAP[emoji]
        role = guild.get_role(int(role_id))
        if not role:
            return

        if role not in member.roles:
            try:
                await member.add_roles(role, reason="Auto-role via réaction")
            except discord.Forbidden:
                return

        await self.update_stats(guild)
        await self._refresh_panel_message(guild)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        panel_id = self._load_panel_msg_id()
        if panel_id and payload.message_id != panel_id:
            return
        if payload.channel_id != int(REACTION_ROLE_CHANNEL_ID):
            return

        emoji = str(payload.emoji)
        if emoji not in EMOJI_ROLE_MAP:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        member = guild.get_member(payload.user_id)
        if not member or member.bot:
            return

        role_name, role_id = EMOJI_ROLE_MAP[emoji]
        role = guild.get_role(int(role_id))
        if not role:
            return

        if role in member.roles:
            try:
                await member.remove_roles(role, reason="Retrait auto-role via réaction")
            except discord.Forbidden:
                return

        await self.update_stats(guild)
        await self._refresh_panel_message(guild)

    # -------------------- Cog unload --------------------
    def cog_unload(self):
        self.panel_auto_sync.cancel()


async def setup(bot):
    await bot.add_cog(RoleStats(bot))
