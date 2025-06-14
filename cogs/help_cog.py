# cogs/help_cog.py

import asyncio
import discord
from discord.ext import commands

from config import (
    HELP_CHANNEL_ID,
    HELPJEU_CHANNEL_ID,
    HELPER_ROLE_ID,
)

class HelpCog(commands.Cog):
    """Cog exposant 4 commandes : help/helpadmin/helpjeu/helpjeuadmin."""

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

    def _has_role(self, ctx):
        return any(r.id == HELPER_ROLE_ID for r in ctx.author.roles)

    async def _delete_after(self, msg, delay):
        await asyncio.sleep(delay)
        try:
            await msg.delete()
        except:
            pass

    # ─────────────────────────────────────────────────────────────────────────
    @commands.command(name="helpadmin")
    async def help_admin(self, ctx):
        """!helpadmin (admin only) — liste des commandes générales, embed persistant."""
        # Permission
        if not self._has_role(ctx):
            await self._delete_after(await ctx.message.delete(), 0)
            err = await ctx.send(f"⚠️ Rôle requis : <@&{HELPER_ROLE_ID}>")
            return await self._delete_after(err, 5)

        # Canal
        if ctx.channel.id != HELP_CHANNEL_ID:
            err = await ctx.send("⚠️ `!helpadmin` réservé au salon #commandes.")
            return await self._delete_after(err, 5)

        # Supprimer la commande après 2s pour être clean
        asyncio.create_task(self._delete_after(ctx.message, 2))

        # Embed admin bien différencié !
        embed = discord.Embed(
            title="🛡️ Commandes générales (admin)",
            description="**Liste des commandes administrateur du serveur :**\n\n"
                        "*(Inclut les commandes avancées uniquement pour staff)*",
            color=discord.Color.orange()
        )
        for cmd, desc in self.general_commands_admin.items():
            embed.add_field(name=f"`!{cmd}`", value=desc, inline=False)

        embed.set_footer(text="Seuls les membres avec le rôle staff peuvent utiliser ces commandes avancées.")

        await ctx.send(embed=embed)
        # PAS de suppression de l'embed ici !

    # ─────────────────────────────────────────────────────────────────────────
    @commands.command(name="help")
    async def help_user(self, ctx):
        """!help — liste des commandes générales, embed auto-supprimé après 3min."""
        # Permission
        if not self._has_role(ctx):
            await self._delete_after(await ctx.message.delete(), 0)
            err = await ctx.send(f"⚠️ Rôle requis : <@&{HELPER_ROLE_ID}>")
            return await self._delete_after(err, 5)

        # Canal
        if ctx.channel.id != HELP_CHANNEL_ID:
            await self._delete_after(ctx.message, 2)
            err = await ctx.send("⚠️ `!help` réservé au salon #commandes.")
            return await self._delete_after(err, 5)

        # Suppression commande après 2s
        asyncio.create_task(self._delete_after(ctx.message, 2))

        # Embed user classique (bleu)
        embed = discord.Embed(
            title="📒 Commandes générales",
            description="Liste des commandes :",
            color=discord.Color.blue()
        )
        for cmd, desc in self.general_commands.items():
            embed.add_field(name=f"`!{cmd}`", value=desc, inline=False)
        embed.set_footer(text="Tapez `!helpjeu` dans #jeu pour les commandes de jeu.")

        sent = await ctx.send(embed=embed)
        # Suppression embed après 180s (3min)
        return await self._delete_after(sent, 180)

    # ─────────────────────────────────────────────────────────────────────────
    @commands.command(name="helpjeuadmin")
    async def help_jeu_admin(self, ctx):
        """!helpjeuadmin (admin only) — liste des commandes de jeu, embed persistant."""
        # Permission
        if not self._has_role(ctx):
            await self._delete_after(await ctx.message.delete(), 0)
            err = await ctx.send(f"⚠️ Rôle requis : <@&{HELPER_ROLE_ID}>")
            return await self._delete_after(err, 5)

        # Canal
        if ctx.channel.id != HELPJEU_CHANNEL_ID:
            err = await ctx.send("⚠️ `!helpjeuadmin` réservé au salon #jeu.")
            return await self._delete_after(err, 5)

        # Supprimer la commande après 2s pour être clean
        asyncio.create_task(self._delete_after(ctx.message, 2))

        # Embed admin jeu
        embed = discord.Embed(
            title="🛡️ Commandes de jeu (admin)",
            description="**Liste des commandes de jeu pour les administrateurs :**",
            color=discord.Color.orange()
        )
        for cmd, desc in self.jeu_commands_admin.items():
            embed.add_field(name=f"`!{cmd}`", value=desc, inline=False)

        embed.set_footer(text="Seuls les membres avec le rôle staff peuvent utiliser ces commandes avancées.")

        await ctx.send(embed=embed)
        # PAS de suppression de l'embed ici !

    # ─────────────────────────────────────────────────────────────────────────
    @commands.command(name="helpjeu")
    async def help_jeu_user(self, ctx):
        """!helpjeu — liste des commandes de jeu, embed auto-supprimé après 3min."""
        # Permission
        if not self._has_role(ctx):
            await self._delete_after(await ctx.message.delete(), 0)
            err = await ctx.send(f"⚠️ Rôle requis : <@&{HELPER_ROLE_ID}>")
            return await self._delete_after(err, 5)

        # Canal
        if ctx.channel.id != HELPJEU_CHANNEL_ID:
            await self._delete_after(ctx.message, 2)
            err = await ctx.send("⚠️ `!helpjeu` réservé au salon #jeu.")
            return await self._delete_after(err, 5)

        # Suppression commande après 2s
        asyncio.create_task(self._delete_after(ctx.message, 2))

        # Embed user jeu
        embed = discord.Embed(
            title="🎮 Commandes de jeu",
            description="Liste des commandes de jeu :",
            color=discord.Color.green()
        )
        for cmd, desc in self.jeu_commands.items():
            embed.add_field(name=f"`!{cmd}`", value=desc, inline=False)

        sent = await ctx.send(embed=embed)
        # Suppression embed après 180s (3min)
        return await self._delete_after(sent, 180)

async def setup(bot: commands.Bot):
    await bot.add_cog(HelpCog(bot))
