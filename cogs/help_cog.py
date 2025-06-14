import asyncio
import discord
from discord.ext import commands

from config import (
    HELP_CHANNEL_ID,
    HELPJEU_CHANNEL_ID,
    ADMIN_HELP_ROLE_ID,
)

class HelpCog(commands.Cog):
    """Commande help contextuel selon rôle."""

    def __init__(self, bot):
        self.bot = bot
        self.general_commands = {
            "help": "Affiche toutes les commandes générales du serveur.",
            "classement": "Affiche tous les classements sur le serveur.",
            "clear": "Supprime les messages de l'utilisateur dans le salon.",
            "clear [nombre]": "Supprime un certain nombre de messages de l'utilisateur dans le salon.",
        }
        self.general_commands_admin = {
            "help": "Affiche toutes les commandes générales du serveur.",
            "classement": "Affiche tous les classements sur le serveur.",
            "setup_roles": "Configure les rôles de réaction.",
            "clear": "Supprime les messages de l'utilisateur dans le salon.",
            "clear [nombre]": "Supprime un certain nombre de messages de l'utilisateur dans le salon.",
        }
        self.jeu_commands = {
            "helpjeu": "Affiche les commandes liées au jeu.",
            "guess":   "Permet de deviner un personnage (jeu GuessCharacter)."
        }
        self.jeu_commands_admin = {
            "helpjeu": "Affiche les commandes liées au jeu.",
            "guess":   "Permet de deviner un personnage (jeu GuessCharacter)."
        }

    async def _delete_after(self, msg, delay):
        await asyncio.sleep(delay)
        try:
            await msg.delete()
        except:
            pass

    @commands.command(name="help")
    async def help_cmd(self, ctx):
        """Affiche le help adapté selon si tu as le rôle admin ou non. Supprime l'embed après 2min."""

        # Commande seulement dans le salon prévu
        if ctx.channel.id != HELP_CHANNEL_ID:
            m = await ctx.send("⚠️ `!help` uniquement dans #commandes.")
            await ctx.message.delete()
            await self._delete_after(m, 5)
            return

        await self._delete_after(ctx.message, 2)

        # On regarde si le membre a le rôle admin
        is_admin = any(role.id == ADMIN_HELP_ROLE_ID for role in ctx.author.roles)

        # On choisit le set de commandes et le style
        if is_admin:
            embed = discord.Embed(
                title="🛡️ Commandes administrateur",
                description="**Liste des commandes avancées réservées staff/admin**",
                color=discord.Color.orange()
            )
            for cmd, desc in self.general_commands_admin.items():
                embed.add_field(name=f"`!{cmd}`", value=desc, inline=False)
            embed.set_footer(text="⚠️ Tu as accès aux commandes staff.")
        else:
            embed = discord.Embed(
                title="📒 Commandes générales",
                description="Liste des commandes disponibles :",
                color=discord.Color.blue()
            )
            for cmd, desc in self.general_commands.items():
                embed.add_field(name=f"`!{cmd}`", value=desc, inline=False)
            embed.set_footer(text="Besoin des commandes jeu ? Tape !helpjeu dans #jeu.")

        sent = await ctx.send(embed=embed)
        await self._delete_after(sent, 120)  # 2 min

    @commands.command(name="helpjeu")
    async def helpjeu_cmd(self, ctx):
        """Affiche le helpjeu adapté selon si tu as le rôle admin ou non. Supprime l'embed après 2min."""

        # Commande seulement dans le salon prévu
        if ctx.channel.id != HELPJEU_CHANNEL_ID:
            m = await ctx.send("⚠️ `!helpjeu` uniquement dans #jeu.")
            await ctx.message.delete()
            await self._delete_after(m, 5)
            return

        await self._delete_after(ctx.message, 2)

        # On regarde si le membre a le rôle admin
        is_admin = any(role.id == ADMIN_HELP_ROLE_ID for role in ctx.author.roles)

        # On choisit le set de commandes et le style
        if is_admin:
            embed = discord.Embed(
                title="🛡️ Commandes jeu (admin)",
                description="**Liste des commandes de jeu pour staff/admin**",
                color=discord.Color.orange()
            )
            for cmd, desc in self.jeu_commands_admin.items():
                embed.add_field(name=f"`!{cmd}`", value=desc, inline=False)
            embed.set_footer(text="⚠️ Tu as accès aux commandes jeu avancées.")
        else:
            embed = discord.Embed(
                title="🎮 Commandes de jeu",
                description="Liste des commandes de jeu :",
                color=discord.Color.green()
            )
            for cmd, desc in self.jeu_commands.items():
                embed.add_field(name=f"`!{cmd}`", value=desc, inline=False)
            embed.set_footer(text="")

        sent = await ctx.send(embed=embed)
        await self._delete_after(sent, 120)  # 2 min

async def setup(bot):
    await bot.add_cog(HelpCog(bot))
