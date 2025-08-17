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

# --------- Fichiers & config ----------
DATA_FILE = os.path.join(os.path.dirname(__file__), "../data/user_cities.json")

# Envoi quotidien (heure locale Paris)
SEND_HOUR = int(os.getenv("METEO_SEND_HOUR", "8"))             # 8h par défaut
WINDOW_MINUTES = int(os.getenv("METEO_WINDOW_MINUTES", "10"))  # fenêtre de 10 min
HOURLY_COUNT = int(os.getenv("METEO_HOURLY_COUNT", "12"))      # nb d'heures à afficher


class UserCityWeather(commands.Cog):
    """
    - !ville <ville>     : enregistre la ville de l'utilisateur
    - !delville          : supprime la ville enregistrée
    - !meteo [ville]     : envoie la météo + horaire **en DM** et supprime la commande du salon

    Envoi quotidien en DM à l'heure SEND_HOUR (Paris) avec une fenêtre de WINDOW_MINUTES.
    """

    def __init__(self, bot):
        self.bot = bot
        self.paris_tz = pytz.timezone("Europe/Paris")
        self.last_daily_date = None  # évite les doublons d'envoi quotidien
        self.daily_weather_and_news.start()
        logger.info("[UserCityWeather] Tâche quotidienne météo/actu démarrée")

    # ------------- Persistance villes -------------
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

    # ------------------- Commandes -------------------
    @commands.command(name="ville")
    async def set_city(self, ctx, *, city: str):
        """Enregistre ta ville pour l'envoi quotidien."""
        user_id = str(ctx.author.id)
        try:
            await ctx.message.delete()
        except (discord.Forbidden, discord.HTTPException):
            pass

        cities = self.load_city_data()
        cities[user_id] = city.strip()
        self.save_city_data(cities)

        try:
            confirm = await ctx.send("✅ Ta ville a bien été enregistrée pour la météo quotidienne !")
            await confirm.delete(delay=5)
        except Exception:
            pass

        logger.info(f"[UserCityWeather] Ville enregistrée pour {ctx.author} : {city}")

    @commands.command(name="delville")
    async def delete_city(self, ctx):
        """Supprime ta ville enregistrée."""
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
            confirm = await ctx.send(txt)
            await confirm.delete(delay=5)
        except Exception:
            pass

    @commands.command(name="meteo")
    async def meteo_now(self, ctx, *, city: str = None):
        """Envoie la météo en DM et supprime la commande du salon."""
        # 1) Supprime immédiatement la commande dans le salon
        try:
            await ctx.message.delete()
        except (discord.Forbidden, discord.HTTPException):
            pass

        # 2) Détermine la ville
        if city is None:
            city = self.load_city_data().get(str(ctx.author.id))
        if not city:
            # DM si possible, sinon message bref dans le salon
            try:
                await ctx.author.send("❌ Aucune ville enregistrée. Utilise `!ville <ta_ville>` ou `!meteo <ville>`.")
            except discord.Forbidden:
                msg = await ctx.reply("❌ Aucune ville enregistrée. Utilise `!ville <ta_ville>` ou `!meteo <ville>`.", mention_author=False)
                await msg.delete(delay=8)
            return

        # 3) Récupère météo + heure par heure, construit et envoie en DM (deux embeds : météo puis actus)
        try:
            weather_text, icon_url, hourly_blocks = await self.get_weather_with_hourly(city)
            weather_embed = self.build_weather_embed(city, weather_text, icon_url, hourly_blocks)
            news_embed = await self.build_news_embed(city)

            await ctx.author.send(embeds=[weather_embed, news_embed])

        except discord.Forbidden:
            # DM fermés → message bref dans le salon
            msg = await ctx.reply("❌ Impossible d'envoyer un DM. Ouvre tes messages privés pour recevoir la météo.", mention_author=False)
            await msg.delete(delay=8)

        except Exception as e:
            logger.error(f"[UserCityWeather] Erreur !meteo pour {city}: {e}")
            try:
                await ctx.author.send("❌ Erreur lors de la récupération des données météo.")
            except discord.Forbidden:
                msg = await ctx.reply("❌ Erreur lors de la récupération des données météo.", mention_author=False)
                await msg.delete(delay=8)

    # ------------------ Tâche quotidienne ------------------
    @tasks.loop(minutes=5)
    async def daily_weather_and_news(self):
        """
        Check toutes les 5 min : si on est dans la fenêtre SEND_HOUR:[00..WINDOW_MINUTES-1] (heure Paris)
        et qu'on n'a pas encore envoyé aujourd'hui → envoi en DM à tous les utilisateurs enregistrés.
        """
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

    # ------------------ Météo & horaire (WeatherAPI) ------------------
    def _emoji_from_weatherapi_code(self, code: int) -> str:
        if code == 1000: return "☀️"                # Clear/Sunny
        if code == 1003: return "⛅"                 # Partly cloudy
        if code in (1006, 1009): return "☁️"        # Cloudy/Overcast
        if code in (1030, 1135, 1147): return "🌫️"  # Mist/Fog
        if 1150 <= code <= 1207 or 1240 <= code <= 1246: return "🌧️"  # pluie/bruine
        if 1210 <= code <= 1237 or 1255 <= code <= 1264: return "❄️"   # neige/grésil
        if 1273 <= code <= 1282: return "⛈️"                            # orage
        return "🌦️"

    async def get_weather_with_hourly(self, city: str):
        """
        Retourne (weather_text:str, icon_url:str|None, hourly_blocks:list[str])
        hourly_blocks : 1..n chaînes <= ~1000 caractères chacune (Discord: 1024 max par field).
        """
        encoded_city = quote(city)
        url = (
            f"http://api.weatherapi.com/v1/forecast.json"
            f"?key={WEATHER_API_KEY}&lang=fr&q={encoded_city}"
            f"&days=1&aqi=no&alerts=no"
        )

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                try:
                    data = await resp.json(content_type=None)
                except Exception as e:
                    logger.warning(f"[Météo] Erreur JSON pour '{city}' : {e}")
                    return "Erreur de réponse de l'API météo.", None, []

                if resp.status != 200:
                    logger.warning(f"[Météo] {city} — HTTP {resp.status} — {data}")
                    return "Ville introuvable ou erreur météo.", None, []

        # ---- courant ----
        if "current" not in data or "location" not in data:
            return "Ville introuvable ou erreur météo.", None, []

        current = data["current"]
        location = data["location"]
        temp = round(current.get("temp_c") or 0)
        cond = current.get("condition") or {}
        desc = cond.get("text") or "—"
        icon_url = f"https:{cond.get('icon')}" if cond.get("icon") else None
        code = int(cond.get("code") or 1000)
        emoji = self._emoji_from_weatherapi_code(code)
        weather_text = f"{emoji} {desc}, {temp} °C"

        # ---- heure par heure (prochaines HOURLY_COUNT heures) ----
        hourly_lines = []
        try:
            hours = data["forecast"]["forecastday"][0]["hour"]
        except Exception:
            hours = []

        now_local_epoch = int(location.get("localtime_epoch") or 0)
        count = 0
        for h in hours:
            t_epoch = int(h.get("time_epoch") or 0)
            if t_epoch < now_local_epoch:
                continue

            # Heure locale affichée "HHh"
            t_str = h.get("time") or ""  # format "YYYY-MM-DD HH:MM"
            hour_txt = t_str[-5:-3] + "h" if len(t_str) >= 16 else "—"

            h_cond = h.get("condition") or {}
            h_code = int(h_cond.get("code") or 1000)
            h_emoji = self._emoji_from_weatherapi_code(h_code)
            h_temp = round(h.get("temp_c") or 0)

            # prob pluie %
            pop = h.get("chance_of_rain")
            try:
                pop = int(pop)
            except Exception:
                pop = 0

            # cumul pluie (mm)
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

        # Split en blocs pour respecter la limite de 1024 chars/field
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

    # ------------------ Embeds ------------------
    def build_weather_embed(self, city: str, weather_text: str, icon_url: str | None, hourly_blocks: list[str]) -> discord.Embed:
        now_local = datetime.now(timezone.utc).astimezone(self.paris_tz).strftime("%d/%m/%Y")
        embed = discord.Embed(
            title=f"🌤️ Météo — {city} ({now_local})",
            color=discord.Color.teal()
        )
        embed.add_field(name="Conditions", value=weather_text, inline=False)
        for idx, block in enumerate(hourly_blocks, start=1):
            embed.add_field(
                name="🕒 Heure par heure" if idx == 1 else "🕒 (suite)",
                value=block,
                inline=False
            )
        if icon_url:
            embed.set_thumbnail(url=icon_url)
        embed.set_footer(text="Source: WeatherAPI")
        return embed

    # ---------------------- Actus (GNews) ----------------------
    async def build_news_embed(self, city: str) -> discord.Embed:
        """
        Essaie d'abord une recherche sur la ville (fr).
        Si aucune actu, fallback sur les top headlines France.
        """
        today = datetime.now(self.paris_tz).strftime("%d/%m/%Y")
        embed = discord.Embed(
            title=f"📰 Actus du jour — {today}",
            color=discord.Color.orange()
        )

        articles = []
        source_label = f"🗞️ Actus près de {city}"
        try:
            async with aiohttp.ClientSession() as session:
                # 1) Recherche ciblée ville
                q = quote(f"\"{city}\"")
                url_city = f"https://gnews.io/api/v4/search?q={q}&lang=fr&max=4&token={GNEWS_API_KEY}"
                async with session.get(url_city) as resp1:
                    data1 = await resp1.json(content_type=None)
                    if resp1.status == 200:
                        articles = data1.get("articles", []) or []

                # 2) Fallback top headlines FR si rien
                if not articles:
                    source_label = "🇫🇷 À la une en France"
                    url_fr = f"https://gnews.io/api/v4/top-headlines?country=fr&lang=fr&max=4&token={GNEWS_API_KEY}"
                    async with session.get(url_fr) as resp2:
                        data2 = await resp2.json(content_type=None)
                        if resp2.status == 200:
                            articles = data2.get("articles", []) or []

        except Exception as e:
            logger.warning(f"[News] Erreur récupération actus: {e}")

        # Construire le bloc
        if not articles:
            news_text = "Aucune actu trouvée."
        else:
            lines = []
            for a in articles:
                title = (a.get("title") or "Sans titre").strip()
                url = a.get("url")
                if url:
                    lines.append(f"• **{title}**\n{url}")
                else:
                    lines.append(f"• **{title}**")
            # éviter de dépasser 1024 caractères
            news_text = ""
            for line in lines:
                if len(news_text) + len(line) + 1 > 1000:
                    break
                news_text += (("\n" if news_text else "") + line)

        embed.add_field(name=source_label, value=news_text, inline=False)
        embed.set_footer(text="Source: GNews")
        return embed

    # ---------------------- Lifecycle ----------------------
    def cog_unload(self):
        self.daily_weather_and_news.cancel()
        logger.info("[UserCityWeather] Tâche arrêtée")


async def setup(bot):
    await bot.add_cog(UserCityWeather(bot))
