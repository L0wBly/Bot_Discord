import discord
from discord.ext import commands

from config import ADMIN_ROLE_ID

class HelpCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="help")
    async def help_cmd(self, ctx):
        """Affiche les commandes générales du bot (hors jeu)."""
        embed = discord.Embed(
            title="📖 Commandes générales",
            description="Voici la liste des commandes organisées par module (sauf jeu) :",
            color=discord.Color.blurple()
        )

        # Vérifie si l'utilisateur a le rôle admin
        has_admin_role = any(role.id == ADMIN_ROLE_ID for role in ctx.author.roles)

        for cog_name, cog in self.bot.cogs.items():
            if cog_name.lower() == "jeu":
                continue

            if cog_name.lower() in ["rolestats", "reactionroles"] and not has_admin_role:
                continue  # Masque ce cog pour les non-admins

            command_list = []
            for command in cog.get_commands():
                if command.hidden:
                    continue
                name = command.name
                description = command.help or "Aucune description."
                command_list.append(f"**`{name}`** : {description}")
            if command_list:
                embed.add_field(
                    name=f"📂 {cog_name}",
                    value="\n".join(command_list),
                    inline=False
                )

        message = await ctx.send(embed=embed)

        # Supprimer aussi le message d'origine s'il est admin
        if has_admin_role:
            await message.delete(delay=180)
            await ctx.message.delete(delay=180)


    @commands.command(name="helpjeu")
    async def helpjeu_cmd(self, ctx):
        """Affiche les commandes du jeu uniquement."""
        embed = discord.Embed(
            title="🧠 Commandes du jeu",
            description="Voici les commandes disponibles pour les modules de jeu :",
            color=discord.Color.orange()
        )

        jeux_commands_found = False
        for cog_name, cog in self.bot.cogs.items():
            if cog_name.lower() != "jeu":
                continue

            command_list = []
            for command in cog.get_commands():
                if command.hidden:
                    continue
                name = command.name
                description = command.help or "Aucune description."
                command_list.append(f"**`{name}`** : {description}")
            if command_list:
                jeux_commands_found = True
                embed.add_field(
                    name=f"🎮 {cog_name}",
                    value="\n".join(command_list),
                    inline=False
                )

        if not jeux_commands_found:
            embed.description = "Aucune commande de jeu trouvée. Assurez-vous que les cogs de jeu ont name=\"Jeu\"."

        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(HelpCog(bot))
