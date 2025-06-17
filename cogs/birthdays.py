# cogs/birthdays.py

import discord
from discord.ext import commands, tasks
from datetime import datetime
import json
import os

from config import BIRTHDAY_CHANNEL_ID
from utils.logger import logger  # si tu as un système de log

class Birthdays(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.birthday_file = "data/birthdays.json"
        self.check_birthdays.start()

    def cog_unload(self):
        self.check_birthdays.cancel()

    def load_birthdays(self):
        if not os.path.exists(self.birthday_file):
            return {}
        with open(self.birthday_file, "r", encoding="utf-8") as f:
            return json.load(f)

    @tasks.loop(time=datetime.strptime("00:00", "%H:%M").time())
    async def check_birthdays(self):
        today = datetime.utcnow().strftime("%m-%d")
        birthdays = self.load_birthdays()

        channel = self.bot.get_channel(BIRTHDAY_CHANNEL_ID)
        if channel is None:
            logger.warning("[Birthdays] Salon introuvable.")
            return

        for user_id, date in birthdays.items():
            if date == today:
                try:
                    user = await self.bot.fetch_user(int(user_id))
                    await channel.send(f"🎉 Joyeux anniversaire {user.mention} ! 🎂")
                except Exception as e:
                    logger.error(f"[Birthdays] Erreur en envoyant le message à {user_id} : {e}")

    @commands.command(name="set_birthday")
    async def set_birthday(self, ctx, date: str):
        """Enregistre ta date d'anniversaire au format MM-JJ (ex: 06-17)"""
        try:
            datetime.strptime(date, "%m-%d")
        except ValueError:
            return await ctx.send("❌ Format invalide. Utilise MM-JJ, ex: `06-17`")

        birthdays = self.load_birthdays()
        birthdays[str(ctx.author.id)] = date
        os.makedirs("data", exist_ok=True)
        with open(self.birthday_file, "w", encoding="utf-8") as f:
            json.dump(birthdays, f, indent=4)

        await ctx.send(f"✅ Ton anniversaire a été enregistré pour le **{date}** !")

async def setup(bot):
    await bot.add_cog(Birthdays(bot))
