# cogs/meteo_news.py
import os
import json
from datetime import datetime, timezone, timedelta, time as dtime

import aiohttp
import pytz
import discord
from discord.ext import commands, tasks

from utils.logger import logger
from config import WEATHER_API_KEY  # Assure-toi que la clé est dispo dans config.py

DATA_FILE = os.path.join(os.path.dirname(__file__), "../data/user_cities.json")
PARIS_TZ = pytz.timezone("Europe/Paris")


def _load_user_cities() -> dict:
    if not os.path.exists(DATA_FILE):
        os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f)
        return {}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        logger.warning("[Meteo] Fichier user_cities corrompu, réinitialisation.")
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f)
        return {}


def _save_user_cities(d: dict):
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


class UserCityWeather(commands.Cog):
    """
    Envoie la météo quotidienne + un récap 'heure par heure' (12 prochaines heures).
    Commandes:
      - !ville <nom_de_ville>  → enregistre ta ville
      - !meteo                 → météo immédiate (avec heure par heure)
      - !meteo <ville>         → météo immédiate pour une ville donnée
    Envoi quotidien: autour de 08:00 (heure Paris) en DM à chaque utilisateur enregistré.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.user_cities = _load_user_cities()
        self.last_daily_date = None  # pour éviter les doublons journaliers
        # Tâche toutes les 5 minutes qui déclenche l'envoi quotidien à ~08:00 Paris
        self.daily_weather_and_news.start()
        logger.info("[UserCityWeather] Tâche quotidienne météo démarrée (avec heure par heure).")

    def cog_unload(self):
        self.daily_weather_and_news.cancel()

    # -----------------------
    # Helpers OpenWeatherMap
    # -----------------------
    def _owm_emoji(self, weather_id: int) -> str:
        if 200 <= weather_id < 300:
            return "⛈️"
        if 300 <= weather_id < 400:
            return "🌦️"
        if 500 <= weather_id < 600:
            return "🌧️"
        if 600 <= weather_id < 700:
            return "❄️"
        if 700 <= weather_id < 800:
            return "🌫️"
        if weather_id == 800:
            return "☀️"
        if 801 <= weather_id <= 802:
            return "⛅"
        if 803 <= weather_id <= 804:
            return "☁️"
        return "🌡️"

    async def _geocode_city(self, session: aiohttp.ClientSession, city: str):
        url = "http://api.openweathermap.org/geo/1.0/direct"
        params = {"q": city, "limit": 1, "appid": WEATHER_API_KEY}
        async with session.get(url, params=params, timeout=15) as r:
            r.raise_for_status()
            data = await r.json()
            if not data:
                return None
            return data[0]["lat"], data[0]["lon"], data[0].get("name") or city

    async def _fetch_onecall(self, city: str):
        """
        Renvoie (current, today_daily, hourly[:12], city_label) ou None si échec
        """
        async with aiohttp.ClientSession() as session:
            coords = await self._geocode_city(session, city)
            if not coords:
                return None
            lat, lon, label = coords

            url = "https://api.openweathermap.org/data/2.5/onecall"
            params = {
                "lat": lat,
                "lon": lon,
                "exclude": "minutely,alerts",
                "units": "metric",
                "lang": "fr",
                "appid": WEATHER_API_KEY,
            }
            async with session.get(url, params=params, timeout=25) as r:
                r.raise_for_status()
                data = await r.json()

        current = data.get("current") or {}
        daily = (data.get("daily") or [])
        today_daily = daily[0] if daily else {}
        hourly = (data.get("hourly") or [])[:12]
        return current, today_daily, hourly, label

    # -----------------------
    # Embeds
    # -----------------------
    def _build_daily_embed(self, city_label: str, current: dict, today_daily: dict) -> discord.Embed:
        now_local = datetime.now(timezone.utc).astimezone(PARIS_TZ).strftime("%d/%m %H:%M")
        weather = (current.get("weather") or [{}])[0]
        wid = int(weather.get("id", 800))
        emoji = self._owm_emoji(wid)
        desc = weather.get("description", "—").capitalize()
        temp = round(current.get("temp", 0))
        feels = round(current.get("feels_like", temp))
        hum = current.get("humidity", 0)
        wind = round(current.get("wind_speed", 0))
        uvi = current.get("uvi", 0)
        pop_today = int(round(((today_daily.get("pop", 0) or 0) * 100)))

        # min/max
        tmin = round((today_daily.get("temp") or {}).get("min", temp))
        tmax = round((today_daily.get("temp") or {}).get("max", temp))

        # lever/coucher
        sunrise = today_daily.get("sunrise")
        sunset = today_daily.get("sunset")
        sunrise_s = datetime.fromtimestamp(sunrise, tz=timezone.utc).astimezone(PARIS_TZ).strftime("%H:%M") if sunrise else "—"
        sunset_s = datetime.fromtimestamp(sunset, tz=timezone.utc).astimezone(PARIS_TZ).strftime("%H:%M") if sunset else "—"

        embed = discord.Embed(
            title=f"{emoji} Météo du jour — {city_label}",
            description=f"**{desc}** — {temp}°C (ressenti {feels}°C)",
            color=discord.Color.teal(),
        )
        embed.add_field(name="Min / Max", value=f"{tmin}°C / {tmax}°C", inline=True)
        embed.add_field(name="Humidité", value=f"{hum}%", inline=True)
        embed.add_field(name="Vent", value=f"{wind} m/s", inline=True)
        embed.add_field(name="UV", value=f"{uvi}", inline=True)
        embed.add_field(name="Prob. précip.", value=f"{pop_today}%", inline=True)
        embed.add_field(name="Lever / Coucher", value=f"{sunrise_s} / {sunset_s}", inline=True)
        embed.set_footer(text=f"Heure locale Paris — Généré le {now_local}")
        return embed

    def _build_hourly_embed(self, city_label: str, hourly_list: list) -> discord.Embed:
        embed = discord.Embed(title=f"🕒 Heures à venir — {city_label} (12 prochaines)", color=discord.Color.blue())
        lines = []
        for h in hourly_list:
            dt_local = datetime.fromtimestamp(h.get("dt", 0), tz=timezone.utc).astimezone(PARIS_TZ)
            hour = dt_local.strftime("%Hh")
            weather = (h.get("weather") or [{}])[0]
            wid = int(weather.get("id", 800))
            emoji = self._owm_emoji(wid)
            temp = round(h.get("temp", 0))
            pop = int(round((h.get("pop", 0) or 0) * 100))
            rain_mm = 0.0
            if isinstance(h.get("rain"), dict):
                rain_mm = float(h["rain"].get("1h", 0.0))
            rain_txt = f"{rain_mm:.1f}mm" if rain_mm > 0 else "—"
            lines.append(f"**{hour}**  {emoji}  {temp}°C  *(POP {pop}%, pluie {rain_txt})*")

        # coupe en champs de 900-1000 caractères pour respecter la limite 1024
        chunk = ""
        for line in lines:
            if len(chunk) + len(line) + 1 > 1000:
                embed.add_field(name="Heures", value=chunk, inline=False)
                chunk = line
            else:
                chunk += ("\n" if chunk else "") + line
        if chunk:
            embed.add_field(name="Heures", value=chunk, inline=False)

        embed.set_footer(text="Source: OpenWeatherMap — heure locale Europe/Paris")
        return embed

    # -----------------------
    # Commandes
    # -----------------------
    @commands.command(name="ville")
    async def set_city(self, ctx: commands.Context, *, city: str):
        """!ville <nom> — Enregistre/MAJ ta ville."""
        uid = str(ctx.author.id)
        self.user_cities[uid] = city.strip()
        _save_user_cities(self.user_cities)
        try:
            await ctx.message.delete()
        except Exception:
            pass
        await ctx.send(f"✅ Ville enregistrée pour **{ctx.author.display_name}**: `{city}`", delete_after=6)

    @commands.command(name="meteo")
    async def meteo_now(self, ctx: commands.Context, *, city: str = None):
        """!meteo [ville] — Météo immédiate + heure par heure."""
        if city is None:
            city = self.user_cities.get(str(ctx.author.id))
        if not city:
            await ctx.reply("❌ Aucune ville enregistrée. Utilise `!ville <ta_ville>`.", mention_author=False)
            return

        try:
            data = await self._fetch_onecall(city)
            if not data:
                await ctx.reply("❌ Impossible de récupérer la météo pour cette ville.", mention_author=False)
                return
            current, today, hourly, label = data
            daily_embed = self._build_daily_embed(label, current, today)
            hourly_embed = self._build_hourly_embed(label, hourly)
            await ctx.send(embeds=[daily_embed, hourly_embed])
        except Exception as e:
            logger.error(f"[Meteo] Erreur !meteo pour {city}: {e}")
            await ctx.reply("❌ Erreur lors de la récupération des données météo.", mention_author=False)

    # -----------------------
    # Tâche quotidienne (en DM)
    # -----------------------
    @tasks.loop(minutes=5)
    async def daily_weather_and_news(self):
        """
        Toutes les 5 minutes on check: si on est entre 08:00 et 08:10 Paris
        et qu'on n'a pas encore envoyé aujourd'hui, on envoie aux utilisateurs.
        """
        now_paris = datetime.now(timezone.utc).astimezone(PARIS_TZ)
        if self.last_daily_date == now_paris.date():
            return
        # fenêtre d'envoi 08:00–08:10 pour éviter le raté si le bot redémarre
        if not (now_paris.hour == 8 and now_paris.minute < 10):
            return

        if not self.user_cities:
            self.last_daily_date = now_paris.date()
            return

        for uid, city in list(self.user_cities.items()):
            try:
                user = self.bot.get_user(int(uid)) or await self.bot.fetch_user(int(uid))
                if not user:
                    continue
                data = await self._fetch_onecall(city)
                if not data:
                    continue
                current, today, hourly, label = data
                daily_embed = self._build_daily_embed(label, current, today)
                hourly_embed = self._build_hourly_embed(label, hourly)
                await user.send(embeds=[daily_embed, hourly_embed])
            except discord.Forbidden:
                logger.warning(f"[Meteo] Impossible d'envoyer un DM à {uid}.")
            except Exception as e:
                logger.warning(f"[Meteo] Envoi échoué pour {uid}/{city}: {e}")

        self.last_daily_date = now_paris.date()

    @daily_weather_and_news.before_loop
    async def _before_daily(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(UserCityWeather(bot))
