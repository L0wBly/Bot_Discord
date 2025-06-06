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
    """
    Cog qui gère manuellement les commandes !help, !helpadmin, !helpjeu et !helpjeuadmin.
    - Seuls les membres ayant le rôle HELPER_ROLE_ID peuvent les exécuter.
    - !help et !helpjeu    : suppression automatique du message + de l'embed.
    - !helpadmin et !helpjeuadmin : suppression automatique du message seul (embed reste visible).
    - Les commandes admin ne sont PAS listées dans les embeds de !help ou !helpjeu.
    """

    def __init__(self, bot):
        self.bot = bot

        # Commandes “générales” affichées par !help (sans mentionner helpadmin)
        self.general_commands = {
            "help": "Affiche toutes les commandes générales du serveur."
            # NOTE : on n'inclut PAS "helpadmin" ici
        }

        # Commandes “de jeu” affichées par !helpjeu (sans mentionner helpjeuadmin)
        self.jeu_commands = {
            "helpjeu": "Affiche les commandes liées au jeu.",
            "guess":   "Permet de deviner un personnage (jeu GuessCharacter)."
            # NOTE : on n'inclut PAS "helpjeuadmin" ici
        }

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # ─────────────────────────────────────────────────────────────────────────
        # 1) On ignore tout message provenant d'un bot (dont celui-ci)
        if message.author.bot:
            return

        content = message.content.strip().lower()
        channel_id = message.channel.id
        author = message.author

        # ─────────────────────────────────────────────────────────────────────────
        # 2) Vérification du rôle (seulement pour ces quatre commandes)
        if content in ("!help", "!helpadmin", "!helpjeu", "!helpjeuadmin"):
            has_helper_role = any(role.id == HELPER_ROLE_ID for role in author.roles)
            if not has_helper_role:
                # Supprimer la commande au bout de 2 s
                asyncio.create_task(self._delete_after(message, 2))
                # Envoyer un message d'erreur (supprimé en 5 s)
                err = await message.channel.send(
                    f"⚠️ Vous devez avoir le rôle <@&{HELPER_ROLE_ID}> pour utiliser cette commande."
                )
                asyncio.create_task(self._delete_after(err, 5))
                return

        # ─────────────────────────────────────────────────────────────────────────
        # 3) Traitement de !helpadmin (suppression du message, embed reste, salon #commandes)
        if content == "!helpadmin":
            # Supprimer la commande de l’utilisateur après 2 s
            asyncio.create_task(self._delete_after(message, 2))

            # Vérification du salon
            if channel_id != HELP_CHANNEL_ID:
                err = await message.channel.send(
                    "⚠️ La commande `!helpadmin` n'est autorisée que dans #commandes."
                )
                asyncio.create_task(self._delete_after(err, 5))
                return

            # Construction de l’embed des commandes générales (admin)
            embed = discord.Embed(
                title="📜 Commandes disponibles",
                description="Voici la liste des commandes **générales** disponibles :",
                color=discord.Color.blue()
            )
            for cmd_name, desc in self.general_commands.items():
                embed.add_field(name=f"`!{cmd_name}`", value=desc, inline=False)
                
            embed.set_footer(text="Tapez `!helpjeu` dans #jeu pour les commandes de jeu.")

            # On n’inclut pas !helpadmin dans cette liste, pour éviter la redondance.
            await message.channel.send(embed=embed)
            return

        # ─────────────────────────────────────────────────────────────────────────
        # 4) Traitement de !help (supprimable, salon #commandes)
        if content == "!help":
            # Supprimer la commande utilisateur après 2 s
            asyncio.create_task(self._delete_after(message, 2))

            if channel_id != HELP_CHANNEL_ID:
                err = await message.channel.send(
                    "⚠️ La commande `!help` n'est autorisée que dans #commandes."
                )
                asyncio.create_task(self._delete_after(err, 5))
                return

            # Construction de l’embed des commandes générales (normales)
            embed = discord.Embed(
                title="📜 Commandes disponibles",
                description="Voici la liste des commandes **générales** disponibles :",
                color=discord.Color.blue()
            )
            for cmd_name, desc in self.general_commands.items():
                embed.add_field(name=f"`!{cmd_name}`", value=desc, inline=False)

            embed.set_footer(text="Tapez `!helpjeu` dans #jeu pour les commandes de jeu.")
            sent_embed = await message.channel.send(embed=embed)
            # Supprimer l'embed au bout de 60 s
            asyncio.create_task(self._delete_after(sent_embed, 60))
            return

        # ─────────────────────────────────────────────────────────────────────────
        # 5) Traitement de !helpjeuadmin (suppression du message, embed reste, salon #jeu)
        if content == "!helpjeuadmin":
            # Supprimer la commande de l’utilisateur après 2 s
            asyncio.create_task(self._delete_after(message, 2))

            # Vérification du salon
            if channel_id != HELPJEU_CHANNEL_ID:
                err = await message.channel.send(
                    "⚠️ La commande `!helpjeuadmin` n'est autorisée que dans #jeu."
                )
                asyncio.create_task(self._delete_after(err, 5))
                return

            # Construction de l’embed des commandes de jeu (admin)
            embed = discord.Embed(
                title="🎮 Commandes liées au jeu",
                description="Voici la liste des commandes **liées au jeu** disponibles :",
                color=discord.Color.green()
            )
            for cmd_name, desc in self.jeu_commands.items():
                embed.add_field(name=f"`!{cmd_name}`", value=desc, inline=False)

            await message.channel.send(embed=embed)
            return

        # ─────────────────────────────────────────────────────────────────────────
        # 6) Traitement de !helpjeu (supprimable, salon #jeu)
        if content == "!helpjeu":
            # Supprimer la commande utilisateur après 2 s
            asyncio.create_task(self._delete_after(message, 2))

            if channel_id != HELPJEU_CHANNEL_ID:
                err = await message.channel.send(
                    "⚠️ La commande `!helpjeu` n'est autorisée que dans #jeu."
                )
                asyncio.create_task(self._delete_after(err, 5))
                return

            # Construction de l’embed des commandes de jeu (normales)
            embed = discord.Embed(
                title="🎮 Commandes liées au jeu",
                description="Voici la liste des commandes **liées au jeu** disponibles :",
                color=discord.Color.green()
            )
            for cmd_name, desc in self.jeu_commands.items():
                embed.add_field(name=f"`!{cmd_name}`", value=desc, inline=False)

            sent_embed = await message.channel.send(embed=embed)
            # Supprimer l’embed au bout de 60 s
            asyncio.create_task(self._delete_after(sent_embed, 60))
            return

        # ─────────────────────────────────────────────────────────────────────────
        # 7) Sinon, on délègue au traitement normal pour les autres commandes (ex. !guess)
        await self.bot.process_commands(message)

    async def _delete_after(self, message: discord.Message, delay: float):
        """Supprime un message après un délai donné (en secondes)."""
        await asyncio.sleep(delay)
        try:
            await message.delete()
        except Exception:
            pass

async def setup(bot: commands.Bot):
    await bot.add_cog(HelpCog(bot))
