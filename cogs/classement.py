import discord
from discord.ext import commands
from collections import defaultdict, Counter
import asyncio

from config import EXCLUDED_CHANNEL_IDS
from utils.logger import logger

class Classement(commands.Cog):
    print(">>> CLASSEMENT COG CHARGÉ (Fichier : classement.py)")
    def __init__(self, bot):
        self.bot = bot
        self.guess_scores = Counter()
        self.message_counts = Counter()
        self.voice_times = defaultdict(int)
        self.voice_states = {}

    async def incr_message_count(self, message):
        if (
            not message.author.bot and
            message.guild and
            message.channel.id not in EXCLUDED_CHANNEL_IDS
        ):
            self.message_counts[message.author.id] += 1

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if before.channel is None and after.channel is not None:
            self.voice_states[member.id] = asyncio.get_event_loop().time()
        elif before.channel is not None and after.channel is None:
            start = self.voice_states.pop(member.id, None)
            if start:
                duration = int(asyncio.get_event_loop().time() - start)
                self.voice_times[member.id] += duration

    def add_guess_win(self, user_id):
        self.guess_scores[user_id] += 1

    print(">>> REGISTRATION COMMANDE CLASSEMENT")
    @commands.command(name="classement", help="Affiche le classement général")
    async def classement(self, ctx):
        print(">>> EXECUTION commande !classement")
        view = ClassementView(self, ctx.guild)
        message = await ctx.send("Sélectionne une catégorie de classement :", view=view)

        async def auto_delete():
            await asyncio.sleep(180)
            try:
                await message.delete()
            except Exception:
                pass
        ctx.bot.loop.create_task(auto_delete())

    def get_classement_embed(self, guild, category):
        if category == "messages":
            counts = self.message_counts
            title = "🏆 Classement Messages"
            desc = "Les membres les plus bavards !"
        elif category == "vocal":
            counts = self.voice_times
            title = "🎙️ Classement Vocal"
            desc = "Ceux qui squattent le plus les vocaux !"
        else:  # guess
            counts = self.guess_scores
            title = "🎮 Classement !guess"
            desc = "Score du mini-jeu !guess"

        top = counts.most_common(10)
        embed = discord.Embed(title=title, description=desc, color=0x7289da)
        for i, (user_id, score) in enumerate(top, 1):
            member = guild.get_member(user_id)
            name = member.display_name if member else f"Utilisateur inconnu ({user_id})"
            if category == "vocal":
                value = f"{score//3600}h {(score%3600)//60}min"
            else:
                value = str(score)
            embed.add_field(
                name=f"{i}. {name}",
                value=value,
                inline=False
            )
        if not top:
            embed.description = "Pas encore de données."
        return embed

class ClassementView(discord.ui.View):
    def __init__(self, cog, guild):
        super().__init__(timeout=180)
        self.cog = cog
        self.guild = guild
        self.clear_items()
        self.add_item(ClassementSelect(cog, guild, self))

class ClassementSelect(discord.ui.Select):
    def __init__(self, cog, guild, view):
        options = [
            discord.SelectOption(label="Messages", value="messages", description="Classement des messages"),
            discord.SelectOption(label="Vocal", value="vocal", description="Classement temps vocal"),
            discord.SelectOption(label="Guess", value="guess", description="Classement jeu !guess"),
        ]
        super().__init__(placeholder="Choisis une catégorie", min_values=1, max_values=1, options=options)
        self.cog = cog
        self.guild = guild
        self.parent_view = view

    async def callback(self, interaction: discord.Interaction):
        category = self.values[0]
        embed = self.cog.get_classement_embed(self.guild, category)
        await interaction.response.edit_message(embed=embed, view=self.parent_view)

async def setup(bot):
    await bot.add_cog(Classement(bot))
