import discord
from discord.ext import commands, tasks
import aiohttp
import json
import os
from datetime import datetime, time as dtime
import pytz
from urllib.parse import quote

from config import (
    WEATHER_API_KEY,
    NEWS_API_KEY,
    NEWS_COUNTRY,
    NEWS_CATEGORY
)

from utils.logger import logger

DATA_FILE = os.path.join(os.path.dirname(__file__), "../data/user_cities.json")

class UserCityWeather(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.paris_tz = pytz.timezone("Europe/Paris")
        # 7h UTC = 9h heure de Paris
        self.daily_weather_and_news.change_interval(time=dtime(hour=20, minute=30, tzinfo=pytz.utc))
        self.daily_weather_and_news.start()
        logger.info("[UserCityWeather] Tâche quotidienne météo/actu démarrée")

    def cog_unload(self):
        self.daily_weather_and_news.cancel()
        logger.info("[UserCityWeather] Tâche arrêtée")

    @commands.command(name="ville")
    async def set_city(self, ctx, *, city: str):
        user_id = str(ctx.author.id)
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass

        cities = self.load_city_data()
        cities[user_id] = city
        self.save_city_data(cities)

        confirm = await ctx.send(f"✅ Ta ville a bien été enregistrée pour la météo quotidienne !")
        await confirm.delete(delay=5)
        logger.info(f"[UserCityWeather] Ville enregistrée pour {ctx.author} : {city}")

    @commands.command(name="delville")
    async def delete_city(self, ctx):
        user_id = str(ctx.author.id)
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass

        cities = self.load_city_data()
        if user_id in cities:
            del cities[user_id]
            self.save_city_data(cities)
            confirm = await ctx.send("🗑️ Ta ville a bien été supprimée.")
        else:
            confirm = await ctx.send("❌ Tu n'avais pas encore enregistré de ville.")

        await confirm.delete(delay=5)

    def load_city_data(self):
        if not os.path.exists(DATA_FILE):
            return {}
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    def save_city_data(self, data):
        os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @tasks.loop(time=dtime(hour=7, minute=0, tzinfo=pytz.utc))
    async def daily_weather_and_news(self):
        cities = self.load_city_data()
        embed = await self.build_news_embed()

        for user_id, city in cities.items():
            try:
                user = await self.bot.fetch_user(int(user_id))
                weather_text, icon_url = await self.get_weather_text(city)
                personalized_embed = embed.copy()
                personalized_embed.insert_field_at(0, name=f"🌤️ Météo à {city}", value=weather_text, inline=False)
                if icon_url:
                    personalized_embed.set_thumbnail(url=icon_url)
                await user.send(embed=personalized_embed)
                logger.info(f"[UserCityWeather] Météo envoyée à {user} pour {city}")
            except Exception as e:
                logger.error(f"[UserCityWeather] Erreur pour {user_id} ({city}) : {e}")

    async def get_weather_text(self, city):
        encoded_city = quote(city)
        url = f"http://api.weatherapi.com/v1/current.json?key={WEATHER_API_KEY}&lang=fr&q={encoded_city}"

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                try:
                    data = await resp.json()
                except Exception as e:
                    logger.warning(f"[Météo] Erreur JSON pour '{city}' : {e}")
                    return "Erreur de réponse de l'API météo.", None

                logger.debug(f"[Météo] Réponse WeatherAPI pour '{city}' : {data}")

                if resp.status != 200 or "current" not in data:
                    return "Ville introuvable ou erreur météo.", None

                temp = data['current']['temp_c']
                desc = data['current']['condition']['text']
                icon_url = f"https:{data['current']['condition']['icon']}"

                return f"{desc}, {temp} °C", icon_url

    async def build_news_embed(self):
        async with aiohttp.ClientSession() as session:
            url = f"https://newsapi.org/v2/top-headlines?country={NEWS_COUNTRY}&category={NEWS_CATEGORY}&apiKey={NEWS_API_KEY}"
            async with session.get(url) as resp:
                try:
                    data = await resp.json()
                except Exception as e:
                    logger.warning(f"[News] Erreur JSON : {e}")
                    data = {}

        headlines = data.get("articles", [])[:3]

        today = datetime.now(self.paris_tz).strftime("%d/%m/%Y")
        embed = discord.Embed(
            title=f"📰 Actus du jour - {today}",
            color=discord.Color.orange()
        )

        news_text = ""
        for article in headlines:
            news_text += f"**{article['title']}**\n{article['url']}\n\n"

        embed.add_field(name="🗞️ Sélection des actualités", value=news_text or "Aucune actu trouvée.", inline=False)
        return embed


async def setup(bot):
    await bot.add_cog(UserCityWeather(bot))
