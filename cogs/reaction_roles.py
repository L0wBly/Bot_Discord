import os
import json
import discord
from discord.ext import commands
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
    ROLE_NOTIF_NEWS,
)

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
    "🔔": ("Notifications News", ROLE_NOTIF_NEWS)
}

DATA_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "role_stats.json")

def read_stats():
    if not os.path.exists(DATA_PATH):
        return {role_name: 0 for role_name, _ in EMOJI_ROLE_MAP.values()}
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def write_stats(stats):
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

class RoleStats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        if not os.path.exists(DATA_PATH):
            write_stats({role_name: 0 for role_name, _ in EMOJI_ROLE_MAP.values()})

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def setup_roles(self, ctx):
        """Affiche l'interface auto-rôle uniquement si la commande est faite dans le bon salon."""
        if ctx.channel.id != REACTION_ROLE_CHANNEL_ID:
            m = await ctx.send("❌ Tu dois utiliser cette commande dans le salon d'auto-rôle !")
            await ctx.message.delete()
            await m.delete(delay=3)
            return

        channel = self.bot.get_channel(REACTION_ROLE_CHANNEL_ID)
        if channel is None:
            m = await ctx.send("Salon introuvable.")
            await ctx.message.delete()
            await m.delete(delay=3)
            return

        embed = discord.Embed(
            title="🌟 Choisis ton rôle via les réactions ! 🌟",
            description=(
                "**Réagis avec l'emoji correspondant pour obtenir ou retirer un rôle :**\n"
                " \n"  # petit espace
                "Clique sur un emoji ci-dessous pour gérer tes rôles !"
            ),
            color=discord.Color.purple()
        )

        # Un field par rôle, bien lisible
        for emoji, (role_name, _) in EMOJI_ROLE_MAP.items():
            embed.add_field(
                name=f"{emoji}  {role_name}",
                value="\u200b",  # espace invisible pour un style compact mais espacé
                inline=False
            )

        msg = await channel.send(embed=embed)
        for emoji in EMOJI_ROLE_MAP.keys():
            await msg.add_reaction(emoji)

        await ctx.message.delete(delay=3)

    async def update_stats(self, guild):
        stats = {role_name: 0 for role_name, _ in EMOJI_ROLE_MAP.values()}
        for role_name, role_id in [v for v in EMOJI_ROLE_MAP.values()]:
            role = guild.get_role(role_id)
            if role:
                stats[role_name] = len(role.members)
        write_stats(stats)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.channel_id != REACTION_ROLE_CHANNEL_ID:
            return
        emoji = str(payload.emoji)
        if emoji not in EMOJI_ROLE_MAP:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        role_name, role_id = EMOJI_ROLE_MAP[emoji]
        member = guild.get_member(payload.user_id)
        if not member or member.bot:
            return
        role = guild.get_role(role_id)
        if not role:
            return
        if role not in member.roles:
            await member.add_roles(role, reason="Auto-role via réaction")
        await self.update_stats(guild)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        if payload.channel_id != REACTION_ROLE_CHANNEL_ID:
            return
        emoji = str(payload.emoji)
        if emoji not in EMOJI_ROLE_MAP:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        role_name, role_id = EMOJI_ROLE_MAP[emoji]
        member = guild.get_member(payload.user_id)
        if not member or member.bot:
            return
        role = guild.get_role(role_id)
        if not role:
            return
        if role in member.roles:
            await member.remove_roles(role, reason="Retrait auto-role via réaction")
        await self.update_stats(guild)

async def setup(bot):
    await bot.add_cog(RoleStats(bot))
