# cogs/user_city_weather.py

import discord
from discord.ext import commands, tasks
import aiohttp
import json
import os
from datetime import datetime, time
import pytz
from urllib.parse import quote

from config import (
    WEATHER_API_KEY,
    NEWS_API_KEY,
    NEWS_COUNTRY,
    NEWS_CATEGORY,
    CHANNEL_ID_METEO_NEWS
)

DATA_FILE = os.path.join(os.path.dirname(__file__), "../data/user_cities.json")

class UserCityWeather(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.paris_tz = pytz.timezone("Europe/Paris")
        self.daily_weather_and_news.change_interval(time=time(hour=9, minute=20, tzinfo=pytz.utc))
        self.daily_weather_and_news.start()

    def cog_unload(self):
        self.daily_weather_and_news.cancel()

    @commands.command(name="ville")
    async def set_city(self, ctx, *, city: str):
        """Permet d'enregistrer ta ville pour la météo quotidienne."""
        user_id = str(ctx.author.id)

        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass

        cities = self.load_city_data()
        cities[user_id] = city
        self.save_city_data(cities)

        confirm = await ctx.send(f"✅ Ta ville **{city}** a bien été enregistrée pour la météo quotidienne !")
        await confirm.delete(delay=5)

    @commands.command(name="delville")
    async def delete_city(self, ctx):
        """Supprime la ville enregistrée pour la météo quotidienne."""
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

    @commands.command(name="meteo")
    async def force_meteo(self, ctx):
        """Force l'envoi de ta météo + actus (commande de test)."""
        user_id = str(ctx.author.id)
        cities = self.load_city_data()

        if user_id not in cities:
            await ctx.send("❌ Tu n'as pas encore enregistré de ville avec `!ville`.")
            return

        city = cities[user_id]
        weather_text, icon_url = await self.get_weather_text(city)
        embed = await self.build_news_embed()
        embed.insert_field_at(0, name=f"🌤️ Météo à {city}", value=weather_text, inline=False)

        if icon_url:
            embed.set_thumbnail(url=icon_url)

        await ctx.send(embed=embed)

    def load_city_data(self):
        if not os.path.exists(DATA_FILE):
            return {}
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    def save_city_data(self, data):
        os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @tasks.loop(time=time(hour=6, minute=0, tzinfo=pytz.utc))  # 6h UTC = 8h Paris
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
            except Exception as e:
                print(f"Erreur en envoyant à {user_id} : {e}")

    async def get_weather_text(self, city):
        async with aiohttp.ClientSession() as session:
            encoded_city = quote(city)
            url = f"http://api.openweathermap.org/data/2.5/weather?q={encoded_city}&appid={WEATHER_API_KEY}&units=metric&lang=fr"
            async with session.get(url) as resp:
                data = await resp.json()
                if resp.status != 200 or "main" not in data:
                    return "Ville introuvable ou erreur météo.", None
                temp = data['main']['temp']
                desc = data['weather'][0]['description'].capitalize()
                icon = data['weather'][0]['icon']
                return f"{desc}, {temp}°C", f"http://openweathermap.org/img/wn/{icon}@2x.png"

    async def build_news_embed(self):
        async with aiohttp.ClientSession() as session:
            url = f"https://newsapi.org/v2/top-headlines?country={NEWS_COUNTRY}&category={NEWS_CATEGORY}&apiKey={NEWS_API_KEY}"
            async with session.get(url) as resp:
                data = await resp.json()
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
