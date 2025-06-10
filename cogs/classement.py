import discord
from discord.ext import commands
from discord import app_commands
from collections import defaultdict, Counter
import asyncio

from config import EXCLUDED_CHANNEL_IDS  # à définir, liste d'IDs de salons à exclure
from utils.logger import logger

class Classement(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # À remplacer par stockage persistant si besoin !
        self.guess_scores = Counter()     # {user_id: int}
        self.message_counts = Counter()   # {user_id: int}
        self.voice_times = defaultdict(int)  # {user_id: secondes}

        self.voice_states = {}  # {user_id: timestamp entrée vocal}

    async def setup_hook(self):
        # Chargement des données persistantes ici (à compléter)
        pass

    @commands.Cog.listener()
    async def on_message(self, message):
        if (
            not message.author.bot and
            message.guild and
            message.channel.id not in EXCLUDED_CHANNEL_IDS
        ):
            self.message_counts[message.author.id] += 1

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        # Entrée en vocal
        if before.channel is None and after.channel is not None:
            self.voice_states[member.id] = asyncio.get_event_loop().time()
        # Sortie du vocal
        elif before.channel is not None and after.channel is None:
            start = self.voice_states.pop(member.id, None)
            if start:
                duration = int(asyncio.get_event_loop().time() - start)
                self.voice_times[member.id] += duration

    # À appeler depuis le jeu !guess pour ajouter une victoire :
    def add_guess_win(self, user_id):
        self.guess_scores[user_id] += 1

    # Commande principale
    @commands.command(name="classement", help="Affiche le classement général")
    async def classement(self, ctx):
        class SelectClassement(discord.ui.Select):
            def __init__(self, outer):
                options = [
                    discord.SelectOption(label="Messages", value="messages", description="Classement des messages"),
                    discord.SelectOption(label="Vocal", value="vocal", description="Classement temps vocal"),
                    discord.SelectOption(label="Guess", value="guess", description="Classement jeu !guess"),
                ]
                super().__init__(placeholder="Choisis une catégorie", min_values=1, max_values=1, options=options)
                self.outer = outer

            async def callback(self, interaction: discord.Interaction):
                value = self.values[0]
                if value == "messages":
                    await interaction.response.edit_message(embed=self.outer.get_classement_embed(ctx.guild, "messages"))
                elif value == "vocal":
                    await interaction.response.edit_message(embed=self.outer.get_classement_embed(ctx.guild, "vocal"))
                elif value == "guess":
                    await interaction.response.edit_message(embed=self.outer.get_classement_embed(ctx.guild, "guess"))

        class ClassementView(discord.ui.View):
            def __init__(self, outer):
                super().__init__(timeout=60)
                self.add_item(SelectClassement(outer))

        await ctx.send(
            "Sélectionne une catégorie de classement :",
            view=ClassementView(self)
        )

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

        # Top 10 uniquement
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

async def setup(bot):
    await bot.add_cog(Classement(bot))
