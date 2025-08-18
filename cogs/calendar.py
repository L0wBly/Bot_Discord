# cogs/calendar.py
import os
import json
import re
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, time as dtime, timezone
from typing import Optional

import pytz
import discord
from discord.ext import commands, tasks

from utils.logger import logger

PARIS_TZ = pytz.timezone("Europe/Paris")
DATA_FILE = os.path.join(os.path.dirname(__file__), "../data/calendar_events.json")

# Détecte si la lib a discord.ui (certaines versions anciennes ne l'ont pas)
HAVE_UI = hasattr(discord, "ui") and hasattr(discord.ui, "View")

# ---------- Modèle ----------
@dataclass
class Reminder:
    time_iso: str
    sent: bool

@dataclass
class Event:
    id: str
    user_id: int
    title: str
    event_iso: str
    tz: str
    prev_evening: Optional[Reminder]
    one_hour: Optional[Reminder]
    created_iso: str

# ---------- Utils persistants ----------
def _load_data() -> dict:
    if not os.path.exists(DATA_FILE):
        return {"events": []}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f) or {"events": []}
    except Exception:
        logger.warning("[Calendar] Fichier corrompu -> réinit.")
        return {"events": []}

def _save_data(data: dict):
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ---------- Parsing date/heure ----------
def parse_date(date_str: str, base_tz=PARIS_TZ) -> Optional[datetime.date]:
    s = date_str.strip().lower().replace("-", "/")
    now_local = datetime.now(timezone.utc).astimezone(base_tz)

    if s in ("today", "aujourd'hui", "auj", "ajd"):
        return now_local.date()
    if s in ("demain", "tomorrow"):
        return (now_local + timedelta(days=1)).date()

    m = re.match(r"^\s*(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\s*$", s)
    if not m:
        return None
    d, mo, y = int(m.group(1)), int(m.group(2)), m.group(3)
    if y:
        y = int(y)
        if y < 100:
            y += 2000
    else:
        y = now_local.year
        try:
            test_dt = base_tz.localize(datetime(y, mo, d, 23, 59))
            if test_dt < now_local:
                y += 1
        except Exception:
            return None
    try:
        return datetime(y, mo, d).date()
    except Exception:
        return None

def parse_time(time_str: str) -> tuple[int, int] | None:
    s = time_str.strip().lower()

    # Cas "16h" ou "16" -> minutes = 0
    m = re.match(r"^(\d{1,2})h?$", s)
    if m:
        hh = int(m.group(1))
        return (hh, 0) if 0 <= hh <= 23 else None

    # Cas "9h30" ou "09:30"
    s = s.replace("h", ":")
    m = re.match(r"^(\d{1,2}):(\d{1,2})$", s)
    if not m:
        return None
    hh, mm = int(m.group(1)), int(m.group(2))
    return (hh, mm) if 0 <= hh <= 23 and 0 <= mm <= 59 else None


# ---------- Construction rappels ----------
def compute_reminders(event_dt: datetime, tz=PARIS_TZ) -> tuple[Optional[Reminder], Optional[Reminder]]:
    prev_evening_dt = tz.localize(datetime.combine(event_dt.date() - timedelta(days=1), dtime(21, 0)))
    one_hour_dt = event_dt - timedelta(hours=1)

    now_local = datetime.now(timezone.utc).astimezone(tz)
    prev = Reminder(prev_evening_dt.isoformat(), False) if prev_evening_dt > now_local else None
    oneh = Reminder(one_hour_dt.isoformat(), False) if one_hour_dt > now_local else None
    return prev, oneh

# ---------- UI pour suppression (si disponible) ----------
if HAVE_UI:
    class DeleteEventView(discord.ui.View):
        def __init__(self, cog_ref: "Calendar", user_id: int, events_for_user: list[dict]):
            super().__init__(timeout=120)
            self.cog_ref = cog_ref
            self.user_id = user_id

            options = []
            for e in events_for_user[:25]:  # limite Discord
                try:
                    evt_dt = datetime.fromisoformat(e["event_iso"]).astimezone(PARIS_TZ)
                except Exception:
                    continue
                label = evt_dt.strftime("%d/%m %H:%M")
                desc = e.get("title", "")[:90] or "(sans titre)"
                options.append(discord.SelectOption(label=label, description=desc, value=e["id"]))

            select = discord.ui.Select(
                placeholder="Sélectionne un événement à supprimer…",
                options=options,
                min_values=1,
                max_values=1
            )

            async def _on_select(interaction: discord.Interaction):
                if interaction.user.id != self.user_id:
                    return await interaction.response.send_message("❌ Ce menu ne t'est pas destiné.", ephemeral=True)

                ev_id = select.values[0]
                data = _load_data()
                before = len(data.get("events", []))
                data["events"] = [x for x in data.get("events", []) if not (x["user_id"] == self.user_id and x["id"] == ev_id)]
                _save_data(data)

                if len(data.get("events", [])) < before:
                    await interaction.response.edit_message(content=f"🗑️ Événement `{ev_id}` supprimé.", view=None)
                else:
                    await interaction.response.send_message("❌ Événement introuvable.", ephemeral=True)

            select.callback = _on_select
            self.add_item(select)
else:
    DeleteEventView = None  # fallback texte uniquement

# ---------- Cog ----------
class Calendar(commands.Cog):
    """
    !cal [date] [heure] [texte…] -> crée un événement + rappels (veille 21h, -1h)
    !cal_list -> DM la liste des événements à venir
    !cal_del [id] -> sans id : menu en DM (si disponible) ; sinon liste texte + suppression par id
    Purge quotidienne à 23:30 (Heure de Paris) des évènements du jour.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.last_daily_cleanup_date = None
        self._tick.start()
        logger.info("[Calendar] Tick de rappel démarré (60s).")

    def cog_unload(self):
        self._tick.cancel()
        logger.info("[Calendar] Tick arrêté.")

    # ------- Commandes -------
    @commands.command(name="cal")
async def add_event(self, ctx, date: str = None, heure: str = None, *, title: str = None):
    """!cal [date] [heure] [texte...] (utilisable en DM ou en salon)"""
    # Supprimer la commande en SALON si possible
    if ctx.guild:
        try:
            perms = ctx.channel.permissions_for(ctx.guild.me)
            if perms.manage_messages:
                await ctx.message.delete()
        except Exception:
            pass

    # Vérifs arguments
    if not (date and heure and title):
        msg = ("❌ Usage : `!cal [date] [heure] [texte]`\n"
               "Exemples : `!cal 18/08 16h Rendez-vous dentiste` | `!cal demain 9:30 Réu`")
        try:
            await ctx.author.send(msg)
        except discord.Forbidden:
            await ctx.reply(msg, mention_author=False, delete_after=10)
        return

    evt_date = parse_date(date)
    hm = parse_time(heure)
    if not evt_date or not hm:
        txt = "❌ Date/heure invalides. Ex : `17/08`, `17/08/2025`, `demain`, `16h`, `09:30`."
        try:
            await ctx.author.send(txt)
        except discord.Forbidden:
            await ctx.reply(txt, mention_author=False, delete_after=10)
        return

    hh, mm = hm
    try:
        naive = datetime(evt_date.year, evt_date.month, evt_date.day, hh, mm, 0)
        event_dt = PARIS_TZ.localize(naive)
    except Exception:
        try:
            await ctx.author.send("❌ Date impossible.")
        except discord.Forbidden:
            await ctx.reply("❌ Date impossible.", mention_author=False, delete_after=10)
        return

    now_local = datetime.now(timezone.utc).astimezone(PARIS_TZ)
    if event_dt <= now_local:
        txt = "❌ Cette date est déjà passée. Merci d'indiquer un rendez-vous futur."
        try:
            await ctx.author.send(txt)
        except discord.Forbidden:
            await ctx.reply(txt, mention_author=False, delete_after=10)
        return

    # Rappels (veille 21h & -1h si encore futurs)
    prev, oneh = compute_reminders(event_dt, PARIS_TZ)

    # Enregistrement
    ev = Event(
        id=uuid.uuid4().hex[:8],           # ID long (on affichera une version courte)
        user_id=ctx.author.id,
        title=title.strip(),
        event_iso=event_dt.isoformat(),
        tz="Europe/Paris",
        prev_evening=prev,
        one_hour=oneh,
        created_iso=now_local.isoformat(),
    )
    data = _load_data()
    data["events"].append(asdict(ev))
    _save_data(data)

    # ---- Confirmation plus lisible en DM ----
    fmt = "%d/%m/%Y %H:%M"
    prev_dt_str = (
        datetime.fromisoformat(prev.time_iso).astimezone(PARIS_TZ).strftime(fmt)
        if prev else "— (déjà passée)"
    )
    oneh_dt_str = (
        datetime.fromisoformat(oneh.time_iso).astimezone(PARIS_TZ).strftime(fmt)
        if oneh else "— (déjà passée)"
    )
    simple_id = ev.id[:6].upper()  # ID court

    confirm = (
        "✅ **Événement enregistré**\n"
        f"🗓️ **Quand :** {event_dt.strftime(fmt)} (Europe/Paris)\n"
        f"✍️ **Quoi :** {ev.title}\n"
        "🔔 **Rappels :**\n"
        f"• Veille 21h : {prev_dt_str}\n"
        f"• 1h avant : {oneh_dt_str}\n"
        f"🆔 **Réf :** {simple_id}"
    )

    try:
        await ctx.author.send(confirm)
    except discord.Forbidden:
        await ctx.reply(
            "✅ Événement enregistré (DM fermé : impossible d’envoyer la confirmation).",
            mention_author=False,
            delete_after=8
        )

    @commands.command(name="cal_list")
    async def list_events(self, ctx):
        """DM la liste de tes événements à venir"""
        data = _load_data()
        now_paris = datetime.now(timezone.utc).astimezone(PARIS_TZ)
        events = []
        for e in data.get("events", []):
            if e["user_id"] != ctx.author.id:
                continue
            try:
                evt_dt = datetime.fromisoformat(e["event_iso"]).astimezone(PARIS_TZ)
            except Exception:
                continue
            if evt_dt >= now_paris - timedelta(days=1):
                events.append((evt_dt, e))

        events.sort(key=lambda t: t[0])
        if not events:
            txt = "📭 Aucun événement à venir."
        else:
            lines = [f"• `{e['id']}` — {dt.strftime('%d/%m/%Y %H:%M')} — {e['title']}" for dt, e in events[:50]]
            txt = "**Tes événements à venir :**\n" + "\n".join(lines)

        try:
            await ctx.author.send(txt)
        except discord.Forbidden:
            await ctx.reply("✉️ Ouvre tes DM pour recevoir la liste.", mention_author=False, delete_after=8)

    @commands.command(name="cal_del")
    async def delete_event(self, ctx, event_id: str = None):
        """
        !cal_del <id>  -> suppression directe
        !cal_del       -> si UI dispo : menu en DM ; sinon liste + instructions
        """
        data = _load_data()

        # Avec ID -> suppression directe
        if event_id:
            before = len(data.get("events", []))
            data["events"] = [e for e in data.get("events", []) if not (e["user_id"] == ctx.author.id and e["id"] == event_id)]
            _save_data(data)
            msg = "🗑️ Événement supprimé." if len(data.get("events", [])) < before else "❌ Aucun événement trouvé avec cet ID."
            try:
                await ctx.author.send(msg)
            except discord.Forbidden:
                await ctx.reply(msg, mention_author=False, delete_after=6)
            return

        # Sans ID -> proposer un menu si possible, sinon fallback texte
        now_paris = datetime.now(timezone.utc).astimezone(PARIS_TZ)
        user_events = []
        for e in data.get("events", []):
            if e["user_id"] != ctx.author.id:
                continue
            try:
                evt_dt = datetime.fromisoformat(e["event_iso"]).astimezone(PARIS_TZ)
            except Exception:
                continue
            if evt_dt >= now_paris - timedelta(days=1):
                user_events.append(e)

        if not user_events:
            try:
                await ctx.author.send("📭 Tu n’as aucun événement à supprimer.")
            except discord.Forbidden:
                await ctx.reply("📭 Tu n’as aucun événement à supprimer.", mention_author=False, delete_after=6)
            return

        user_events.sort(key=lambda e: datetime.fromisoformat(e["event_iso"]))

        if HAVE_UI and DeleteEventView is not None:
            header = "**Sélectionne un événement à supprimer :**\n" + "\n".join(
                f"• `{e['id']}` — {datetime.fromisoformat(e['event_iso']).astimezone(PARIS_TZ).strftime('%d/%m/%Y %H:%M')} — {e['title']}"
                for e in user_events[:50]
            )
            view = DeleteEventView(self, ctx.author.id, user_events)
            try:
                await ctx.author.send(header, view=view)
            except discord.Forbidden:
                await ctx.reply("❌ Ouvre tes DM pour choisir l’événement à supprimer.", mention_author=False, delete_after=8)
            else:
                if len(user_events) > 25:
                    try:
                        await ctx.author.send("ℹ️ Tu as plus de 25 évènements : utilise `!cal_del <id>` pour ceux non listés.")
                    except Exception:
                        pass
        else:
            # Fallback texte si discord.ui indisponible
            lines = [f"• `{e['id']}` — {datetime.fromisoformat(e['event_iso']).astimezone(PARIS_TZ).strftime('%d/%m/%Y %H:%M')} — {e['title']}" for e in user_events]
            body = "**Environnement sans menus Discord — supprime avec `!cal_del <id>` :**\n" + "\n".join(lines)
            try:
                await ctx.author.send(body)
            except discord.Forbidden:
                await ctx.reply("❌ Ouvre tes DM pour voir la liste et l’ID à supprimer.", mention_author=False, delete_after=8)

    # ------- Tâche de rappel + purge 23:30 -------
    @tasks.loop(seconds=60)
    async def _tick(self):
        await self.bot.wait_until_ready()
        data = _load_data()
        changed = False
        now_paris = datetime.now(timezone.utc).astimezone(PARIS_TZ)
        today_local = now_paris.date()

        keep_events = []
        for e in data.get("events", []):
            try:
                evt_dt = datetime.fromisoformat(e["event_iso"]).astimezone(PARIS_TZ)
            except Exception:
                continue

            # Rappels
            for key in ("prev_evening", "one_hour"):
                r = e.get(key)
                if not r:
                    continue
                try:
                    r_time = datetime.fromisoformat(r["time_iso"]).astimezone(PARIS_TZ)
                except Exception:
                    continue
                if not r.get("sent") and now_paris >= r_time:
                    user = self.bot.get_user(e["user_id"]) or await self.bot.fetch_user(e["user_id"])
                    if user:
                        try:
                            label = "la veille (21h)" if key == "prev_evening" else "1h avant"
                            await user.send(
                                f"⏰ **Rappel {label}**\n"
                                f"• Quand : {evt_dt.strftime('%d/%m/%Y %H:%M')}\n"
                                f"• Quoi  : {e['title']}\n"
                                f"• ID : `{e['id']}`"
                            )
                            e[key]["sent"] = True
                            changed = True
                        except discord.Forbidden:
                            pass

            keep_events.append(e)

        # Purge quotidienne à 23:30 (Heure de Paris) : supprime les évènements du jour écoulé
        if (self.last_daily_cleanup_date != today_local) and (now_paris.hour == 23 and now_paris.minute >= 30):
            new_keep = []
            for e in keep_events:
                try:
                    evt_dt = datetime.fromisoformat(e["event_iso"]).astimezone(PARIS_TZ)
                except Exception:
                    continue
                if evt_dt.date() == today_local and evt_dt <= now_paris:
                    changed = True
                    continue
                new_keep.append(e)
            keep_events = new_keep
            self.last_daily_cleanup_date = today_local
            logger.info("[Calendar] Purge quotidienne 23:30 exécutée.")

        # Fallback au cas où le bot a raté des purges (offline) : on nettoie > 2 jours
        new_keep2 = []
        for e in keep_events:
            try:
                evt_dt = datetime.fromisoformat(e["event_iso"]).astimezone(PARIS_TZ)
            except Exception:
                continue
            if evt_dt < now_paris - timedelta(days=2):
                changed = True
                continue
            new_keep2.append(e)
        keep_events = new_keep2

        if changed or len(keep_events) != len(data.get("events", [])):
            data["events"] = keep_events
            _save_data(data)

    @_tick.before_loop
    async def _before_tick(self):
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    await bot.add_cog(Calendar(bot))
