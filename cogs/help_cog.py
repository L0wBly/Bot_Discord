import asyncio
import discord
from discord.ext import commands

from config import (
    HELP_CHANNEL_ID,
    HELPJEU_CHANNEL_ID,
    HELPER_ROLE_ID,
)

class HelpCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.general_commands = {
            "help": "Affiche toutes les commandes générales du serveur.",
            "classement": "Affiche le classement des messages, voice et de guess.."
        }
        self.jeu_commands = {
            "helpjeu": "Affiche les commandes liées au jeu.",
            "guess":   "Permet de deviner un personnage (jeu GuessCharacter)."
        }

    async def handle_help_command(self, message: discord.Message):
        # IGNORE les bots
        if message.author.bot:
            return False

        content = message.content.strip().lower()
        channel_id = message.channel.id
        author = message.author

        if content in ("!help", "!helpadmin", "!helpjeu", "!helpjeuadmin"):
            has_helper_role = any(role.id == HELPER_ROLE_ID for role in author.roles)
            if not has_helper_role:
                asyncio.create_task(self._delete_after(message, 2))
                err = await message.channel.send(
                    f"⚠️ Vous devez avoir le rôle <@&{HELPER_ROLE_ID}> pour utiliser cette commande."
                )
                asyncio.create_task(self._delete_after(err, 5))
                return True

        if content == "!helpadmin":
            asyncio.create_task(self._delete_after(message, 2))
            if channel_id != HELP_CHANNEL_ID:
                err = await message.channel.send(
                    "⚠️ La commande `!helpadmin` n'est autorisée que dans #commandes."
                )
                asyncio.create_task(self._delete_after(err, 5))
                return True
            embed = discord.Embed(
                title="📜 Commandes disponibles",
                description="Voici la liste des commandes **générales** disponibles :",
                color=discord.Color.blue()
            )
            for cmd_name, desc in self.general_commands.items():
                embed.add_field(name=f"`!{cmd_name}`", value=desc, inline=False)
            embed.set_footer(text="Tapez `!helpjeu` dans #jeu pour les commandes de jeu.")
            await message.channel.send(embed=embed)
            return True

        if content == "!help":
            asyncio.create_task(self._delete_after(message, 2))
            if channel_id != HELP_CHANNEL_ID:
                err = await message.channel.send(
                    "⚠️ La commande `!help` n'est autorisée que dans #commandes."
                )
                asyncio.create_task(self._delete_after(err, 5))
                return True
            embed = discord.Embed(
                title="📜 Commandes disponibles",
                description="Voici la liste des commandes **générales** disponibles :",
                color=discord.Color.blue()
            )
            for cmd_name, desc in self.general_commands.items():
                embed.add_field(name=f"`!{cmd_name}`", value=desc, inline=False)
            embed.set_footer(text="Tapez `!helpjeu` dans #jeu pour les commandes de jeu.")
            sent_embed = await message.channel.send(embed=embed)
            asyncio.create_task(self._delete_after(sent_embed, 60))
            return True

        if content == "!helpjeuadmin":
            asyncio.create_task(self._delete_after(message, 2))
            if channel_id != HELPJEU_CHANNEL_ID:
                err = await message.channel.send(
                    "⚠️ La commande `!helpjeuadmin` n'est autorisée que dans #jeu."
                )
                asyncio.create_task(self._delete_after(err, 5))
                return True
            embed = discord.Embed(
                title="🎮 Commandes liées au jeu",
                description="Voici la liste des commandes **liées au jeu** disponibles :",
                color=discord.Color.green()
            )
            for cmd_name, desc in self.jeu_commands.items():
                embed.add_field(name=f"`!{cmd_name}`", value=desc, inline=False)
            await message.channel.send(embed=embed)
            return True

        if content == "!helpjeu":
            asyncio.create_task(self._delete_after(message, 2))
            if channel_id != HELPJEU_CHANNEL_ID:
                err = await message.channel.send(
                    "⚠️ La commande `!helpjeu` n'est autorisée que dans #jeu."
                )
                asyncio.create_task(self._delete_after(err, 5))
                return True
            embed = discord.Embed(
                title="🎮 Commandes liées au jeu",
                description="Voici la liste des commandes **liées au jeu** disponibles :",
                color=discord.Color.green()
            )
            for cmd_name, desc in self.jeu_commands.items():
                embed.add_field(name=f"`!{cmd_name}`", value=desc, inline=False)
            sent_embed = await message.channel.send(embed=embed)
            asyncio.create_task(self._delete_after(sent_embed, 60))
            return True

        return False

    async def _delete_after(self, message: discord.Message, delay: float):
        await asyncio.sleep(delay)
        try:
            await message.delete()
        except Exception:
            pass

async def setup(bot):
    await bot.add_cog(HelpCog(bot))
