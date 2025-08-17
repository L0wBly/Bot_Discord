# cogs/meteo_news.py
import discord
from discord.ext import commands, tasks
import aiohttp
import json
import os
from datetime import datetime, timezone
import pytz
from urllib.parse import quote

from config import (
    WEATHER_API_KEY,
    GNEWS_API_KEY,
)

from utils.logger import logger

DATA_FILE = os.path.join(os.path.dirname(__file__), "../data/user_cities.json")

# Config heure d'envoi (heure locale Paris)
SEND_HOUR = int(os.getenv("METEO_SEND_HOUR", "8"))            # 8h par défaut
WINDOW_MINUTES = int(os.getenv("METEO_WINDOW_MINUTES", "10")) # fenêtre 10 min par défaut
HOURLY_COUNT = int(os.getenv("METEO_HOURLY_COUNT", "12"))     # 12 prochaines heures

class UserCityWeather(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.paris_tz = pytz.timezone("Europe/Paris")
        self.last_daily_date = None  # évite le double envoi journalier
        self.daily_weather_and_news.start()
        logger.info("[UserCityWeather] Tâche quotidienne météo/actu démarrée")

    def cog_unload(self):
        self.daily_weather_and_news.cancel()
        logger.info("[UserCityWeather] Tâche arrêtée")

    # -------------------- stockage villes --------------------
    def load_city_data(self):
        if not os.path.exists(DATA_FILE):
            return {}
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f) or {}

    def save_city_data(self, data):
        os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # -------------------- commandes --------------------
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

    @commands.command(name="meteo")
    async def meteo_now(self, ctx, *, city: str = None):
        """!meteo [ville] — envoie la météo + heure par heure immédiatement."""
        if city is None:
            city = self.load_city_data().get(str(ctx.author.id))
        if not city:
            await ctx.reply("❌ Aucune ville enregistrée. Utilise `!ville <ta_ville>` ou `!meteo <ville>`.", mention_author=False)
            return

        try:
            weather_text, icon_url, hourly_blocks = await self.get_weather_with_hourly(city)
            embed = await self.build_news_embed(city)
            embed.insert_field_at(0, name=f"🌤️ Météo à {city}", value=weather_text, inline=False)
            # Ajoute 1 à 2 champs "Heure par heure" (Discord limite 1024 chars / field)
            for idx, block in enumerate(hourly_blocks, start=1):
                embed.add_field(name="🕒 Heure par heure" if idx == 1 else "🕒 (suite)", value=block, inline=False)
            if icon_url:
                embed.set_thumbnail(url=icon_url)
            await ctx.send(embed=embed)
        except Exception as e:
            logger.error(f"[UserCityWeather] Erreur !meteo pour {city}: {e}")
            await ctx.reply("❌ Erreur lors de la récupération des données météo.", mention_author=False)

    # -------------------- scheduler quotidien --------------------
    @tasks.loop(minutes=5)
    async def daily_weather_and_news(self):
        """Check toutes les 5 min; envoie entre SEND_HOUR:00 et +WINDOW_MINUTES (heure Paris)."""
        now_paris = datetime.now(timezone.utc).astimezone(self.paris_tz)
        if self.last_daily_date == now_paris.date():
            return
        if not (now_paris.hour == SEND_HOUR and now_paris.minute < WINDOW_MINUTES):
            return

        cities = self.load_city_data()
        for user_id, city in cities.items():
            try:
                user = await self.bot.fetch_user(int(user_id))
                weather_text, icon_url, hourly_blocks = await self.get_weather_with_hourly(city)
                embed = await self.build_news_embed(city)
                embed.insert_field_at(0, name=f"🌤️ Météo à {city}", value=weather_text, inline=False)
                for idx, block in enumerate(hourly_blocks, start=1):
                    embed.add_field(name="🕒 Heure par heure" if idx == 1 else "🕒 (suite)", value=block, inline=False)
                if icon_url:
                    embed.set_thumbnail(url=icon_url)
                await user.send(embed=embed)
                logger.info(f"[UserCityWeather] Météo envoyée à {user} pour {city}")
            except Exception as e:
                logger.error(f"[UserCityWeather] Erreur pour {user_id} ({city}) : {e}")

        self.last_daily_date = now_paris.date()

    @daily_weather_and_news.before_loop
    async def _before_daily(self):
        await self.bot.wait_until_ready()

    # -------------------- météo + heure par heure --------------------
    def _emoji_from_weatherapi_code(self, code: int) -> str:
        # mapping simple des codes WeatherAPI → emoji
        if code == 1000: return "☀️"                # Clear/Sunny
        if code == 1003: return "⛅"                 # Partly cloudy
        if code in (1006, 1009): return "☁️"        # Cloudy/Overcast
        if code in (1030, 1135, 1147): return "🌫️"  # Mist/Fog
        # pluie / bruine
        if 1150 <= code <= 1207 or 1240 <= code <= 1246: return "🌧️"
        # neige / grésil
        if 1210 <= code <= 1237 or 1255 <= code <= 1264: return "❄️"
        # orage
        if 1273 <= code <= 1282: return "⛈️"
        return "🌦️"

    async def get_weather_with_hourly(self, city):
        """
        Retourne (weather_text:str, icon_url:str|None, hourly_blocks:list[str])
        hourly_blocks = 1..2 blocs texte formatés pour Discord (<=1024 chars)
        """
        encoded_city = quote(city)
        url = (
            f"http://api.weatherapi.com/v1/forecast.json"
            f"?key={WEATHER_API_KEY}&lang=fr&q={encoded_city}"
            f"&days=1&aqi=no&alerts=no"
        )

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json(content_type=None)
                if resp.status != 200:
                    logger.warning(f"[Météo] {city} — HTTP {resp.status} — {data}")
                    return "Ville introuvable ou erreur météo.", None, []

        # ----- courant -----
        if "current" not in data or "location" not in data:
            return "Ville introuvable ou erreur météo.", None, []

        current = data["current"]
        location = data["location"]
        temp = round(current.get("temp_c") or 0)
        cond = current.get("condition") or {}
        desc = cond.get("text") or "—"
        icon_url = f"https:{cond.get('icon')}" if cond.get("icon") else None
        weather_code = int(cond.get("code") or 1000)
        emoji = self._emoji_from_weatherapi_code(weather_code)

        weather_text = f"{emoji} {desc}, {temp} °C"

        # ----- heure par heure (prochaines 12h) -----
        hourly_lines = []
        try:
            forecast_hours = data["forecast"]["forecastday"][0]["hour"]
        except Exception:
            forecast_hours = []

        # on part de l'heure locale du lieu (fourni par WeatherAPI)
        now_local_epoch = int(location.get("localtime_epoch") or 0)
        count = 0
        for h in forecast_hours:
            t_epoch = int(h.get("time_epoch") or 0)
            if t_epoch < now_local_epoch:
                continue
            # format heure locale HHh
            # (WeatherAPI renvoie time local sous forme 'YYYY-MM-DD HH:MM')
            t_str = h.get("time") or ""
            hour_txt = t_str[-5:-3] + "h" if len(t_str) >= 16 else "—"

            h_cond = h.get("condition") or {}
            h_code = int(h_cond.get("code") or 1000)
            h_emoji = self._emoji_from_weatherapi_code(h_code)
            h_temp = round(h.get("temp_c") or 0)
            # prob pluie
            pop = h.get("chance_of_rain")
            try:
                pop = int(pop)
            except Exception:
                pop = 0
            # pluie mm
            rain_mm = h.get("precip_mm")
            try:
                rain_mm = float(rain_mm or 0.0)
            except Exception:
                rain_mm = 0.0
            rain_txt = f"{rain_mm:.1f}mm" if rain_mm > 0 else "—"

            hourly_lines.append(f"**{hour_txt}**  {h_emoji}  {h_temp}°C  *(POP {pop}%, pluie {rain_txt})*")

            count += 1
            if count >= HOURLY_COUNT:
                break

        # split en blocs <= 1000 chars pour champ Discord
        blocks = []
        chunk = ""
        for line in hourly_lines:
            if len(chunk) + len(line) + 1 > 1000:
                blocks.append(chunk)
                chunk = line
            else:
                chunk += ("\n" if chunk else "") + line
        if chunk:
            blocks.append(chunk)

        return weather_text, icon_url, blocks

    # -------------------- news --------------------
    async def build_news_embed(self, city):
        async with aiohttp.ClientSession() as session:
            query = quote(city)
            url = f"https://gnews.io/api/v4/search?q={query}&lang=fr&max=3&token={GNEWS_API_KEY}"
            async with session.get(url) as resp:
                try:
                    data = await resp.json(content_type=None)
                except Exception as e:
                    logger.warning(f"[News] Erreur JSON : {e}")
                    data = {}

        articles = data.get("articles", [])
        today = datetime.now(self.paris_tz).strftime("%d/%m/%Y")
        embed = discord.Embed(
            title=f"📰 Actus du jour - {today}",
            color=discord.Color.orange()
        )

        news_text = ""
        for article in articles:
            title = article.get("title")
            url = article.get("url")
            if title and url:
                news_text += f"**{title}**\n{url}\n\n"

        embed.add_field(name="🗞️ Sélection des actualités", value=news_text or "Aucune actu trouvée.", inline=False)
        return embed


async def setup(bot):
    await bot.add_cog(UserCityWeather(bot))
