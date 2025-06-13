import discord
from discord.ext import commands

class PersoCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def clear(self, ctx, nombre: int = None):
        """Supprime tes propres messages dans le salon. Usage : !clear ou !clear <nombre>"""
        await ctx.message.delete()

        def is_author(m):
            return m.author == ctx.author

        deleted = []
        limit = None
        if nombre is not None and nombre > 0:
            limit = 1000  # on parcourt jusqu'à 1000 messages récents pour être large
            async for msg in ctx.channel.history(limit=limit):
                if msg.author == ctx.author:
                    deleted.append(msg)
                if len(deleted) >= nombre:
                    break
        else:
            async for msg in ctx.channel.history(limit=1000):
                if msg.author == ctx.author:
                    deleted.append(msg)

        if deleted:
            for msg in deleted:
                try:
                    await msg.delete()
                except Exception:
                    pass

    # Tu peux ajouter d'autres commandes ici

async def setup(bot):
    await bot.add_cog(PersoCommands(bot))
