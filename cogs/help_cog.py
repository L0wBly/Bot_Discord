import discord
from discord.ext import commands

class HelpCog(commands.Cog):
    def __init__(self, bot):
        print("HelpCog loaded!")  # DEBUG pour voir si la cog est chargée
        self.bot = bot

    @commands.command(name="help")
    async def help_cmd(self, ctx):
        print("help_cmd called")
        await ctx.send("Help command OK !")

    @commands.command(name="helpjeu")
    async def helpjeu_cmd(self, ctx):
        print("helpjeu_cmd called")
        await ctx.send("HelpJEU command OK !")

async def setup(bot):
    await bot.add_cog(HelpCog(bot))
