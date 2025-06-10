import discord
from discord.ext import commands
from collections import defaultdict, Counter
import asyncio

from config import EXCLUDED_CHANNEL_IDS  # à définir dans config.py
from utils.logger import logger

class Classement(commands.Cog):
    def __init__(self, bot):
        print(">>> CLASSEMENT COG CHARGÉ (Fichier : classement.py)")
        self.bot = bot
        self.guess_scores = Counter()
        self.message_counts = Counter()
        self.voice_times = defaultdict(int)
        self.voice_states = {}

    @commands.Cog.listener()
    async def on_message(self, message):
        # On enregistre le message UNIQUEMENT, pas de process_commands ici !
        if (
            not message.author.bot and
            message.guild and
            message.channel.id not in EXCLUDED_CHANNEL_IDS
        ):
            self.message_counts[message.author.id] += 1

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        try:
            # Entrée en vocal
            if before.channel is None and after.channel is not None:
                self.voice_states[member.id] = asyncio.get_event_loop().time()
            # Sortie du vocal
            elif before.channel is not None and after.channel is None:
                start = self.voice_states.pop(member.id, None)
                if start:
                    duration = int(asyncio.get_event_loop().time() - start)
                    self.voice_times[member.id] += duration
        except Exception as e:
            logger.error(f"[Classement] Erreur dans on_voice_state_update : {e}")

    def add_guess_win(self, user_id):
        self.guess_scores[user_id] += 1

    @commands.command(name="classement", help="Affiche le classement général")
    async def classement(self, ctx):
        print(">>> EXECUTION commande !classement")
        try:
            view = ClassementView(self, ctx.guild)
            message = await ctx.send("**Sélectionne une catégorie de classement :**", view=view)
            
            # Supprime le message de commande après 3 secondes
            async def delete_user_command():
                await asyncio.sleep(3)
                try:
                    await ctx.message.delete()
                except Exception:
                    pass

            # Suppression auto après 3min (180s)
            async def auto_delete():
                await asyncio.sleep(180)
                try:
                    await message.delete()
                except Exception:
                    pass
            ctx.bot.loop.create_task(auto_delete())
            ctx.bot.loop.create_task(delete_user_command())
        except Exception as e:
            print(f"[Classement] Erreur lors de l'affichage du classement : {e}")
            await ctx.send("Erreur lors de l’affichage du classement.")

    def get_classement_embed(self, guild, category):
        try:
            if category == "messages":
                counts = self.message_counts
                title = "🏆 Classement Messages"
                desc = "Les membres les plus bavards !"
            elif category == "vocal":
                counts = Counter(self.voice_times)  # Correction ICI
                title = "🎙️ Classement Vocal"
                desc = "Ceux qui squattent le plus les vocaux !"
            else:  # guess
                counts = self.guess_scores
                title = "🎮 Classement !guess"
                desc = "Score du mini-jeu !guess"

            # Top 10
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
        except Exception as e:
            # Log et retourne une embed d’erreur
            logger.error(f"[Classement] Erreur dans get_classement_embed : {e}")
            embed = discord.Embed(
                title="Erreur",
                description="Impossible de générer le classement.",
                color=0xe74c3c
            )
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
        print(f"[Classement] Interaction menu par {interaction.user} : {self.values}")
        try:
            category = self.values[0]
            embed = self.cog.get_classement_embed(self.guild, category)
            await interaction.response.edit_message(embed=embed, view=self.parent_view)
        except Exception as e:
            print("Erreur dans le callback du classement :", e)
            try:
                await interaction.response.send_message(
                    "Une erreur est survenue lors de l’affichage du classement. Contacte un admin.",
                    ephemeral=True
                )
            except:
                pass

async def setup(bot):
    await bot.add_cog(Classement(bot))
