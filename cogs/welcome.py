import discord
from discord.ext import commands
from config import WELCOME_CHANNEL_ID

class Welcome(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member):
        channel = member.guild.get_channel(WELCOME_CHANNEL_ID)
        if channel:
            # Mention dans le message texte
            mention = member.mention
            embed = discord.Embed(
                title=f"🌟 Bienvenue {member.display_name} ! 🌟",
                description=(
                    f"Bienvenue sur **{member.guild.name}** !\n\n"
                    "Nous sommes ravis de t’accueillir parmi nous.\n"
                    "N’hésite pas à te présenter et à découvrir nos salons !\n\n"
                    "👉 **Lis bien les règles et amuse-toi bien !**"
                ),
                color=discord.Color.purple()
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(text="La team t’accueille à bras ouverts ❤️")
            await channel.send(content=mention, embed=embed)

async def setup(bot):
    await bot.add_cog(Welcome(bot))
