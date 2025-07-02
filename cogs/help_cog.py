import discord
from discord.ext import commands

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

        for cog_name, cog in self.bot.cogs.items():
            if cog_name.lower() == "jeu":
                continue  # On ignore le cog de jeu ici

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

        await ctx.send(embed=embed)

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
