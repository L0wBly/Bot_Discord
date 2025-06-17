import discord
from discord.ext import commands, tasks
from datetime import datetime, time
import json
import os
import pytz

from config import BIRTHDAY_CHANNEL_ID
from utils.logger import logger

class Birthdays(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.birthday_file = os.path.join("data", "birthdays.json")
        self.check_birthdays.start()

    def cog_unload(self):
        self.check_birthdays.cancel()

    def load_birthdays(self):
        os.makedirs("data", exist_ok=True)
        if not os.path.exists(self.birthday_file):
            with open(self.birthday_file, "w", encoding="utf-8") as f:
                json.dump({}, f)
            return {}

        try:
            with open(self.birthday_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            logger.warning("[Birthdays] Fichier JSON vide ou invalide. Remise à zéro.")
            with open(self.birthday_file, "w", encoding="utf-8") as f:
                json.dump({}, f)
            return {}

    def save_birthdays(self, birthdays):
        with open(self.birthday_file, "w", encoding="utf-8") as f:
            json.dump(birthdays, f, indent=4)

    def get_today_date_paris(self):
        paris_tz = pytz.timezone("Europe/Paris")
        now = datetime.now(paris_tz)
        return now.strftime("%d-%m")  # JJ-MM

    @tasks.loop(time=time(hour=8, minute=0))  # 08:00 UTC = 10:00 Paris
    async def check_birthdays(self):
        today = self.get_today_date_paris()
        birthdays = self.load_birthdays()

        channel = self.bot.get_channel(BIRTHDAY_CHANNEL_ID)
        if channel is None:
            logger.warning("[Birthdays] Salon d'anniversaire introuvable.")
            return

        for user_id, date in birthdays.items():
            if date == today:
                try:
                    user = await self.bot.fetch_user(int(user_id))
                    jour, mois = map(int, date.split("-"))
                    date_formatee = datetime(2000, mois, jour).strftime("%d %B")

                    embed = discord.Embed(
                        title="🥳 Joyeux anniversaire !",
                        description=(
                            f"🎂 **{user.mention}** fête son anniversaire aujourd’hui !\n\n"
                            f"📅 Date : **{date_formatee} ({date})**\n"
                            f"💌 Toute la communauté te souhaite une journée inoubliable !"
                        ),
                        color=discord.Color.gold()
                    )
                    embed.set_thumbnail(url=user.display_avatar.url)
                    embed.set_footer(text="🎈 Profite bien de ta journée !")
                    await channel.send(content=user.mention, embed=embed)
                except Exception as e:
                    logger.error(f"[Birthdays] Erreur lors du message à {user_id} : {e}")

    @commands.command(name="anniv")
    async def anniv(self, ctx, date: str = None):
        """Ajoute, modifie ou affiche ton anniversaire (format JJ-MM)"""
        birthdays = self.load_birthdays()
        user_id = str(ctx.author.id)

        if date is None:
            if user_id in birthdays:
                embed = discord.Embed(
                    title="🎂 Ton anniversaire",
                    description=f"Tu as enregistré la date : **{birthdays[user_id]}**",
                    color=discord.Color.blue()
                )
                return await ctx.send(embed=embed)
            else:
                embed = discord.Embed(
                    title="❌ Aucune date trouvée",
                    description="Tu n'as pas encore enregistré de date. Utilise `!anniv JJ-MM`",
                    color=discord.Color.red()
                )
                return await ctx.send(embed=embed)

        try:
            jour, mois = map(int, date.split("-"))
            datetime.strptime(f"{mois}-{jour}", "%m-%d")
        except ValueError:
            embed = discord.Embed(
                title="❌ Format invalide",
                description="Utilise le format `JJ-MM`, par exemple `10-06`",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        birthdays[user_id] = date
        self.save_birthdays(birthdays)
        embed = discord.Embed(
            title="✅ Anniversaire enregistré !",
            description=f"Ton anniversaire a été enregistré/modifié pour le **{date}** 🎂",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    @commands.command(name="delanniv")
    async def delanniv(self, ctx):
        """Supprime ton anniversaire"""
        birthdays = self.load_birthdays()
        user_id = str(ctx.author.id)

        if user_id in birthdays:
            del birthdays[user_id]
            self.save_birthdays(birthdays)
            embed = discord.Embed(
                title="🗑️ Anniversaire supprimé",
                description="Ton anniversaire a été supprimé avec succès.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
        else:
            embed = discord.Embed(
                title="❌ Aucun anniversaire enregistré",
                description="Tu n'avais pas enregistré de date.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)

    @commands.command(name="annivs")
    async def annivs(self, ctx):
        """Affiche les 20 prochains anniversaires à venir"""
        birthdays = self.load_birthdays()
        today = datetime.now(pytz.timezone("Europe/Paris"))

        upcoming = []
        for user_id, date_str in birthdays.items():
            try:
                jour, mois = map(int, date_str.split("-"))
                date_full = datetime(today.year, mois, jour)
                if date_full < today:
                    date_full = date_full.replace(year=today.year + 1)
                upcoming.append((user_id, date_full, date_str))
            except:
                continue

        upcoming.sort(key=lambda x: x[1])
        top_20 = upcoming[:20]

        if not top_20:
            embed = discord.Embed(
                title="🎉 Prochains anniversaires",
                description="Aucun anniversaire à venir pour l’instant.",
                color=discord.Color.blurple()
            )
            return await ctx.send(embed=embed)

        embed = discord.Embed(
            title="📅 Prochains anniversaires (20 max)",
            color=discord.Color.blurple()
        )

        for user_id, d, raw_date in top_20:
            try:
                user = await self.bot.fetch_user(int(user_id))
                date_formatted = d.strftime("%d %B")
                embed.add_field(
                    name=user.display_name,
                    value=f"🎂 {date_formatted} ({raw_date})",
                    inline=False
                )
            except:
                continue

        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Birthdays(bot))
