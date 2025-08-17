# cogs/meteo_news.py
import discord
from discord.ext import commands, tasks
import aiohttp
import json
import os
import re
import unicodedata
from typing import Optional, List, Tuple
from datetime import datetime, timezone, timedelta
import pytz
from urllib.parse import quote

from config import (
    WEATHER_API_KEY,
    GNEWS_API_KEY,
)
from utils.logger import logger

# --------- Fichier de persistance ----------
DATA_FILE = os.path.join(os.path.dirname(__file__), "../data/user_cities.json")

# --------- Paramètres d'envoi ----------
# Envoi quotidien (heure locale Paris)
SEND_HOUR = int(os.getenv("METEO_SEND_HOUR", "8"))
WINDOW_MINUTES = int(os.getenv("METEO_WINDOW_MINUTES", "10"))

class UserCityWeather(commands.Cog):
    """
    - !ville <ville>  : enregistre la ville de l'utilisateur
    - !delville       : supprime la ville enregistrée
    - !meteo [ville]  : **DM** météo + heure-par-heure (00h→23h du jour), la commande est supprimée du salon
    """

    def __init__(self, bot):
        self.bot = bot
        self.paris_tz = pytz.timezone("Europe/Paris")
        self.last_daily_date = None
        self.daily_weather_and_news.start()
        logger.info("[UserCityWeather] Tâche quotidienne météo/actu démarrée")

    # ---------- Helpers normalisation villes ----------
    def _strip_accents(self, s: str) -> str:
        return ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))

    def _clean_spaces(self, s: str) -> str:
        return re.sub(r"\s+", " ", s).strip()

    def _city_query_variants(self, city: str) -> List[str]:
        base = self._clean_spaces(city)
        acc = self._strip_accents(base)

        def hyphen_to_space(s: str) -> str: return self._clean_spaces(s.replace("-", " "))
        def remove_apostrophes(s: str) -> str: return self._clean_spaces(s.replace("’", " ").replace("'", " "))
        def remove_punct(s: str) -> str: return self._clean_spaces(re.sub(r"[^A-Za-z0-9\s]", " ", s))

        variants = {
            base, acc,
            hyphen_to_space(base), hyphen_to_space(acc),
            remove_apostrophes(base), remove_apostrophes(acc),
            remove_punct(base), remove_punct(acc),
        }
        more = set()
        for v in list(variants):
            if "france" not in v.lower():
                more.add(self._clean_spaces(v + " France"))
        variants |= more

        ordered = []
        for cand in [base, acc]:
            if cand and cand not in ordered:
                ordered.append(cand)
        for cand in variants:
            if cand and cand not in ordered:
                ordered.append(cand)
        return ordered[:10]

    # ---------- Résolution WeatherAPI -> lat/lon ----------
    async def _resolve_city_weatherapi(self, city: str) -> Optional[Tuple[str, float, float]]:
        async with aiohttp.ClientSession() as session:
            for q in self._city_query_variants(city):
                url = f"http://api.weatherapi.com/v1/search.json?key={WEATHER_API_KEY}&q={quote(q)}"
                try:
                    async with session.get(url, timeout=12) as resp:
                        data = await resp.json(content_type=None)
                        if resp.status != 200 or not isinstance(data, list) or not data:
                            continue
                        fr = [x for x in data if (x.get("country") == "France")]
                        pick = fr[0] if fr else data[0]
                        name = pick.get("name") or q
                        lat = float(pick["lat"]); lon = float(pick["lon"])
                        return name, lat, lon
                except Exception as e:
                    logger.debug(f"[Meteo] search.json '{q}' -> {e}")
        return None

    # ---------- Persistance ----------
    def load_city_data(self):
        if not os.path.exists(DATA_FILE):
            return {}
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f) or {}
        except Exception:
            logger.warning("[UserCityWeather] user_cities.json corrompu, réinitialisation.")
            try:
                with open(DATA_FILE, "w", encoding="utf-8") as f:
                    json.dump({}, f)
            except Exception:
                pass
            return {}

    def save_city_data(self, data):
        os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ---------- Commandes ----------
    @commands.command(name="ville")
    async def set_city(self, ctx, *, city: str):
        user_id = str(ctx.author.id)
        try:
            await ctx.message.delete()
        except (discord.Forbidden, discord.HTTPException):
            pass

        cities = self.load_city_data()
        cities[user_id] = city.strip()
        self.save_city_data(cities)

        try:
            msg = await ctx.send("✅ Ta ville a bien été enregistrée pour la météo quotidienne !")
            await msg.delete(delay=5)
        except Exception:
            pass

        logger.info(f"[UserCityWeather] Ville enregistrée pour {ctx.author} : {city}")

    @commands.command(name="delville")
    async def delete_city(self, ctx):
        user_id = str(ctx.author.id)
        try:
            await ctx.message.delete()
        except (discord.Forbidden, discord.HTTPException):
            pass

        cities = self.load_city_data()
        if user_id in cities:
            del cities[user_id]
            self.save_city_data(cities)
            txt = "🗑️ Ta ville a bien été supprimée."
        else:
            txt = "❌ Tu n'avais pas encore enregistré de ville."
        try:
            msg = await ctx.send(txt)
            await msg.delete(delay=5)
        except Exception:
            pass

    @commands.command(name="meteo")
    async def meteo_now(self, ctx, *, city: str = None):
        """Envoie la météo en DM (heure par heure 00h→23h du jour) et supprime la commande du salon."""
        try:
            await ctx.message.delete()
        except (discord.Forbidden, discord.HTTPException):
            pass

        if city is None:
            city = self.load_city_data().get(str(ctx.author.id))
        if not city:
            try:
                await ctx.author.send("❌ Aucune ville enregistrée. Utilise `!ville <ta_ville>` ou `!meteo <ville>`.")
            except discord.Forbidden:
                m = await ctx.reply("❌ Aucune ville enregistrée. Utilise `!ville <ta_ville>` ou `!meteo <ville>`.", mention_author=False)
                await m.delete(delay=8)
            return

        try:
            weather_text, icon_url, hourly_blocks = await self.get_weather_with_hourly(city)
            weather_embed = self.build_weather_embed(city, weather_text, icon_url, hourly_blocks)
            news_embed = await self.build_news_embed(city)
            await ctx.author.send(embeds=[weather_embed, news_embed])
        except discord.Forbidden:
            m = await ctx.reply("❌ Impossible d'envoyer un DM. Ouvre tes messages privés pour recevoir la météo.", mention_author=False)
            await m.delete(delay=8)
        except Exception as e:
            logger.error(f"[UserCityWeather] Erreur !meteo pour {city}: {e}")
            try:
                await ctx.author.send("❌ Erreur lors de la récupération des données météo.")
            except discord.Forbidden:
                m = await ctx.reply("❌ Erreur lors de la récupération des données météo.", mention_author=False)
                await m.delete(delay=8)

    # ---------- Tâche quotidienne ----------
    @tasks.loop(minutes=5)
    async def daily_weather_and_news(self):
        now_paris = datetime.now(timezone.utc).astimezone(self.paris_tz)
        if self.last_daily_date == now_paris.date():
            return
        if not (now_paris.hour == SEND_HOUR and now_paris.minute < WINDOW_MINUTES):
            return

        cities = self.load_city_data()
        for user_id, city in list(cities.items()):
            try:
                user = await self.bot.fetch_user(int(user_id))
                if not user:
                    continue
                weather_text, icon_url, hourly_blocks = await self.get_weather_with_hourly(city)
                weather_embed = self.build_weather_embed(city, weather_text, icon_url, hourly_blocks)
                news_embed = await self.build_news_embed(city)
                await user.send(embeds=[weather_embed, news_embed])
                logger.info(f"[UserCityWeather] Météo envoyée à {user} ({city})")
            except discord.Forbidden:
                logger.warning(f"[UserCityWeather] DM refusé par {user_id}")
            except Exception as e:
                logger.warning(f"[UserCityWeather] Envoi échoué pour {user_id} ({city}) : {e}")

        self.last_daily_date = now_paris.date()

    @daily_weather_and_news.before_loop
    async def _before_daily(self):
        await self.bot.wait_until_ready()

    # ---------- Météo & heure par heure (00→23 du jour) ----------
    def _emoji_from_weatherapi_code(self, code: int) -> str:
        if code == 1000: return "☀️"
        if code == 1003: return "⛅"
        if code in (1006, 1009): return "☁️"
        if code in (1030, 1135, 1147): return "🌫️"
        if 1150 <= code <= 1207 or 1240 <= code <= 1246: return "🌧️"
        if 1210 <= code <= 1237 or 1255 <= code <= 1264: return "❄️"
        if 1273 <= code <= 1282: return "⛈️"
        return "🌦️"

    async def get_weather_with_hourly(self, city: str):
        """
        Retourne (weather_text, icon_url, hourly_blocks)
        -> Affiche **toutes les heures du jour local (00h→23h)**, quelle que soit l'heure actuelle.
        """
        resolved = await self._resolve_city_weatherapi(city)
        if not resolved:
            return "Ville introuvable ou erreur météo.", None, []
        _, lat, lon = resolved

        url = (
            "http://api.weatherapi.com/v1/forecast.json"
            f"?key={WEATHER_API_KEY}&lang=fr&q={lat},{lon}"
            "&days=2&aqi=no&alerts=no"
        )

        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=20) as resp:
                try:
                    data = await resp.json(content_type=None)
                except Exception as e:
                    logger.warning(f"[Météo] Erreur JSON pour '{city}' : {e}")
                    return "Erreur de réponse de l'API météo.", None, []
                if resp.status != 200:
                    logger.warning(f"[Météo] {city} — HTTP {resp.status} — {data}")
                    return "Ville introuvable ou erreur météo.", None, []

        if "current" not in data or "location" not in data:
            return "Ville introuvable ou erreur météo.", None, []

        current = data["current"]
        location = data["location"]

        # Conditions actuelles
        temp = round(current.get("temp_c") or 0)
        cond = current.get("condition") or {}
        desc = cond.get("text") or "—"
        icon_url = f"https:{cond.get('icon')}" if cond.get("icon") else None
        code = int(cond.get("code") or 1000)
        emoji = self._emoji_from_weatherapi_code(code)
        weather_text = f"{emoji} {desc}, {temp} °C"

        # Heure locale du lieu → on prend **la date locale** pour choisir le bon forecastday
        tz_id = location.get("tz_id") or "Europe/Paris"
        try:
            tz = pytz.timezone(tz_id)
        except Exception:
            tz = self.paris_tz
        local_date = datetime.now(timezone.utc).astimezone(tz).date()

        # Choisir le forecastday qui correspond à la date locale
        days = data.get("forecast", {}).get("forecastday", []) or []
        hours_today = []
        for d in days:
            try:
                d_date = datetime.strptime(d["date"], "%Y-%m-%d").date()
            except Exception:
                continue
            if d_date == local_date:
                hours_today = d.get("hour", []) or []
                break
        if not hours_today and days:
            hours_today = days[0].get("hour", []) or []

        # Construire les 24 lignes (00h→23h)
        hourly_lines: List[str] = []
        for h in hours_today:
            t_str = h.get("time") or ""  # "YYYY-MM-DD HH:MM" (local)
            hour_txt = t_str[-5:-3] + "h" if len(t_str) >= 16 else "—"

            h_cond = h.get("condition") or {}
            h_code = int(h_cond.get("code") or 1000)
            h_emoji = self._emoji_from_weatherapi_code(h_code)
            h_temp = round(h.get("temp_c") or 0)

            try:
                pop = int(h.get("chance_of_rain"))
            except Exception:
                pop = 0
            try:
                rain_mm = float(h.get("precip_mm") or 0.0)
            except Exception:
                rain_mm = 0.0
            rain_txt = f"{rain_mm:.1f}mm" if rain_mm > 0 else "—"

            hourly_lines.append(f"**{hour_txt}**  {h_emoji}  {h_temp}°C  *(POP {pop}%, pluie {rain_txt})*")

        # Split en blocs (<=1024 chars/field)
        blocks, chunk = [], ""
        for line in hourly_lines:
            if len(chunk) + len(line) + 1 > 1000:
                blocks.append(chunk)
                chunk = line
            else:
                chunk += ("\n" if chunk else "") + line
        if chunk:
            blocks.append(chunk)

        return weather_text, icon_url, blocks

    # ---------- Embeds ----------
    def build_weather_embed(self, city: str, weather_text: str, icon_url: Optional[str], hourly_blocks: List[str]) -> discord.Embed:
        today = datetime.now(timezone.utc).astimezone(self.paris_tz).strftime("%d/%m/%Y")
        embed = discord.Embed(title=f"🌤️ Météo — {city} ({today})", color=discord.Color.teal())
        embed.add_field(name="Conditions", value=weather_text, inline=False)
        for idx, block in enumerate(hourly_blocks, start=1):
            embed.add_field(name="🕒 Heure par heure" if idx == 1 else "🕒 (suite)", value=block, inline=False)
        if icon_url:
            embed.set_thumbnail(url=icon_url)
        embed.set_footer(text="Source: WeatherAPI")
        return embed

    # ---------- Actus (GNews) ----------
    async def build_news_embed(self, city: str) -> discord.Embed:
        today = datetime.now(self.paris_tz).strftime("%d/%m/%Y")
        embed = discord.Embed(title=f"📰 Actus du jour — {today}", color=discord.Color.orange())

        articles = []
        source_label = f"🗞️ Actus près de {city}"
        try:
            async with aiohttp.ClientSession() as session:
                for q_raw in self._city_query_variants(city):
                    q = quote(f"\"{q_raw}\"")
                    url_city = f"https://gnews.io/api/v4/search?q={q}&lang=fr&max=4&token={GNEWS_API_KEY}"
                    async with session.get(url_city, timeout=12) as r1:
                        d1 = await r1.json(content_type=None)
                        if r1.status == 200:
                            articles = d1.get("articles", []) or []
                            if articles:
                                break
                if not articles:
                    source_label = "🇫🇷 À la une en France"
                    url_fr = f"https://gnews.io/api/v4/top-headlines?country=fr&lang=fr&max=4&token={GNEWS_API_KEY}"
                    async with session.get(url_fr, timeout=12) as r2:
                        d2 = await r2.json(content_type=None)
                        if r2.status == 200:
                            articles = d2.get("articles", []) or []
        except Exception as e:
            logger.warning(f"[News] Erreur récupération actus: {e}")

        if not articles:
            news_text = "Aucune actu trouvée."
        else:
            lines = []
            for a in articles:
                title = (a.get("title") or "Sans titre").strip()
                url = a.get("url")
                lines.append(f"• **{title}**\n{url}" if url else f"• **{title}**")
            news_text, cur = "", ""
            for line in lines:
                if len(cur) + len(line) + 1 > 1000:
                    news_text += (("\n" if news_text else "") + cur)
                    cur = line
                else:
                    cur += (("\n" if cur else "") + line)
            if cur:
                news_text += (("\n" if news_text else "") + cur)

        embed.add_field(name=source_label, value=news_text, inline=False)
        embed.set_footer(text="Source: GNews")
        return embed

    # ---------- Lifecycle ----------
    def cog_unload(self):
        self.daily_weather_and_news.cancel()
        logger.info("[UserCityWeather] Tâche arrêtée")


async def setup(bot):
    await bot.add_cog(UserCityWeather(bot))
