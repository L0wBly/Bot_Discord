import discord
from discord.ext import commands

class Calendar(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @commands.command(name="caltest")
    async def caltest(self, ctx):
        await ctx.send("cal OK")

async def setup(bot: commands.Bot):
    await bot.add_cog(Calendar(bot))
