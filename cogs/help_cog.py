import discord
from discord.ext import commands

class HelpCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="help")
    async def help_cmd(self, ctx):
        await ctx.send("Help command OK !")

    @commands.command(name="helpjeu")
    async def helpjeu_cmd(self, ctx):
        await ctx.send("HelpJEU command OK !")

async def setup(bot):
    await bot.add_cog(HelpCog(bot))
