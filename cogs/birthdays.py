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
        with open(self.birthday_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def save_birthdays(self, birthdays):
        with open(self.birthday_file, "w", encoding="utf-8") as f:
            json.dump(birthdays, f, indent=4)

    def get_today_date_paris(self):
        paris_tz = pytz.timezone("Europe/Paris")
        return datetime.now(paris_tz).strftime("%m-%d")

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
                    embed = discord.Embed(
                        title="🎉 Joyeux anniversaire ! 🎉",
                        description=f"Souhaitons un merveilleux anniversaire à {user.mention} ! 🥳🎂",
                        color=discord.Color.magenta()
                    )
                    embed.set_thumbnail(url=user.display_avatar.url)
                    embed.set_footer(text="Toute la communauté te souhaite le meilleur ! ❤️")
                    await channel.send(content=user.mention, embed=embed)
                except Exception as e:
                    logger.error(f"[Birthdays] Erreur lors du message à {user_id} : {e}")

    @commands.command(name="anniv")
    async def anniv(self, ctx, date: str = None):
        """Ajoute, modifie ou affiche ton anniversaire (format MM-JJ)"""
        birthdays = self.load_birthdays()
        user_id = str(ctx.author.id)

        if date is None:
            if user_id in birthdays:
                return await ctx.send(f"🎂 Ton anniversaire est : **{birthdays[user_id]}**")
            else:
                return await ctx.send("❌ Tu n'as pas encore enregistré de date. Utilise `!anniv MM-JJ`")
        
        try:
            datetime.strptime(date, "%m-%d")
        except ValueError:
            return await ctx.send("❌ Format invalide. Utilise `MM-JJ`, par ex. `06-17`")

        birthdays[user_id] = date
        self.save_birthdays(birthdays)
        await ctx.send(f"✅ Ton anniversaire a été enregistré/modifié pour le **{date}** !")

    @commands.command(name="delanniv")
    async def delanniv(self, ctx):
        """Supprime ton anniversaire"""
        birthdays = self.load_birthdays()
        user_id = str(ctx.author.id)

        if user_id in birthdays:
            del birthdays[user_id]
            self.save_birthdays(birthdays)
            await ctx.send("🗑️ Ton anniversaire a été supprimé.")
        else:
            await ctx.send("❌ Tu n'avais pas enregistré de date.")

    @commands.command(name="annivs")
    async def annivs(self, ctx):
        """Affiche les 20 prochains anniversaires à venir"""
        birthdays = self.load_birthdays()
        today = datetime.now(pytz.timezone("Europe/Paris"))
        today_mmdd = today.strftime("%m-%d")

        # Crée une liste (user_id, date complète) triée
        upcoming = []
        for user_id, date_str in birthdays.items():
            try:
                date_full = datetime.strptime(date_str, "%m-%d").replace(year=today.year)
                if date_full < today:
                    date_full = date_full.replace(year=today.year + 1)
                upcoming.append((user_id, date_full))
            except:
                continue

        # Trie et prend les 20 premiers
        upcoming.sort(key=lambda x: x[1])
        top_20 = upcoming[:20]

        if not top_20:
            return await ctx.send("🎉 Aucun anniversaire à venir pour l’instant.")

        embed = discord.Embed(
            title="📅 Prochains anniversaires (20 max)",
            color=discord.Color.blurple()
        )

        for user_id, d in top_20:
            try:
                user = await self.bot.fetch_user(int(user_id))
                embed.add_field(
                    name=user.display_name,
                    value=d.strftime("🎂 %d %B (%m-%d)"),
                    inline=False
                )
            except:
                continue

        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Birthdays(bot))
