import discord
from discord.ext import commands

class HelpCog(commands.Cog):
    def __init__(self, bot):
        print("HelpCog loaded!")  # DEBUG: Vérifie si la cog est chargée
        self.bot = bot

    @commands.command(name="help")
    async def help_cmd(self, ctx):
        print("help_cmd called")  # DEBUG: Affiche à chaque appel de !help
        await ctx.send("Help command OK !")

    @commands.command(name="helpjeu")
    async def helpjeu_cmd(self, ctx):
        print("helpjeu_cmd called")  # DEBUG: Affiche à chaque appel de !helpjeu
        await ctx.send("HelpJEU command OK !")

async def setup(bot):
    print(">>> SETUP help_cog.py CALLED <<<")  # DEBUG: Le setup de la cog est bien appelé
    await bot.add_cog(HelpCog(bot))
    print("Commandes enregistrées :", [cmd.name for cmd in bot.commands])  # Affiche toutes les commandes reconnues
