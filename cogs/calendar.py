# cogs/calendar.py
import os
import json
import re
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, time as dtime, timezone
import pytz
import discord
from discord.ext import commands, tasks

from utils.logger import logger

PARIS_TZ = pytz.timezone("Europe/Paris")
DATA_FILE = os.path.join(os.path.dirname(__file__), "../data/calendar_events.json")


# ---------- Modèle ----------
@dataclass
class Reminder:
    time_iso: str   # ISO string with tz
    sent: bool

@dataclass
class Event:
    id: str
    user_id: int
    title: str
    event_iso: str
    tz: str
    prev_evening: Reminder | None
    one_hour: Reminder | None
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
def parse_date(date_str: str, base_tz=PARIS_TZ) -> datetime.date | None:
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
        # si déjà passé cette année, on suppose l’an prochain
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
    s = time_str.strip().lower().replace("h", ":")
    if re.match(r"^\d{1,2}$", s):
        hh = int(s)
        if 0 <= hh <= 23:
            return (hh, 0)
        return None
    m = re.match(r"^\s*(\d{1,2}):(\d{2})\s*$", s)
    if not m:
        return None
    hh, mm = int(m.group(1)), int(m.group(2))
    if 0 <= hh <= 23 and 0 <= mm <= 59:
        return (hh, mm)
    return None


# ---------- Construction rappels ----------
def compute_reminders(event_dt: datetime, tz=PARIS_TZ) -> tuple[Reminder | None, Reminder | None]:
    # veille 21h (si future)
    prev_evening_dt = tz.localize(datetime.combine(event_dt.date() - timedelta(days=1), dtime(21, 0)))
    one_hour_dt = event_dt - timedelta(hours=1)

    now_local = datetime.now(timezone.utc).astimezone(tz)
    prev = Reminder(prev_evening_dt.isoformat(), False) if prev_evening_dt > now_local else None
    oneh = Reminder(one_hour_dt.isoformat(), False) if one_hour_dt > now_local else None
    return prev, oneh


# ---------- UI pour suppression ----------
class DeleteEventView(discord.ui.View):
    def __init__(self, cog_ref: "Calendar", user_id: int, events_for_user: list[dict]):
        super().__init__(timeout=120)
        self.cog_ref = cog_ref
        self.user_id = user_id

        # On limite à 25 options (limite Discord). Si plus, on invitera à utiliser !cal_del <id>.
        options = []
        for e in events_for_user[:25]:
            try:
                evt_dt = datetime.fromisoformat(e["event_iso"]).astimezone(PARIS_TZ)
            except Exception:
                continue
            label = evt_dt.strftime("%d/%m %H:%M")
            desc = e["title"][:90] if e.get("title") else "(sans titre)"
            options.append(discord.SelectOption(label=label, description=desc, value=e["id"]))

        select = discord.ui.Select(
            placeholder="Sélectionne un événement à supprimer…",
            options=options,
            min_values=1,
            max_values=1
        )

        async def _on_select(interaction: discord.Interaction):
            # sécurité : seule la personne concernée peut utiliser ce menu
            if interaction.user.id != self.user_id:
                try:
                    await interaction.response.send_message("❌ Ce menu ne t'est pas destiné.", ephemeral=True)
                except Exception:
                    pass
                return

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


# ---------- Cog ----------
class Calendar(commands.Cog):
    """
    !cal [date] [heure] [texte…] -> crée un événement + rappels (veille 21h, -1h)
      - date : 17/08/2025, 17/08, demain, aujourd'hui
      - heure : 16h, 16:00, 9, 09:30
    (Confirmation + rappels en DM ; message de commande supprimé en salon si possible.)

    !cal_list -> DM la liste des événements à venir
    !cal_del [id] -> sans id : menu en DM pour choisir ; avec id : suppression directe
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.last_daily_cleanup_date = None  # pour 23h30
        self._tick.start()
        logger.info("[Calendar] Tick de rappel démarré (60s).")

    def cog_unload(self):
        self._tick.cancel()
        logger.info("[Calendar] Tick arrêté.")

    # ------- Commandes -------
    @commands.command(name="cal")
    async def add_event(self, ctx, date: str = None, heure: str = None, *, title: str = None):
        """!cal [date] [heure] [texte...] (utilisable en DM ou en salon)"""
        # Supprimer la commande si possible (en salon uniquement)
        if ctx.guild:
            try:
                perms = ctx.channel.permissions_for(ctx.guild.me)
                if perms.manage_messages:
                    await ctx.message.delete()
            except Exception:
                pass

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
            txt = "❌ Date/heure invalides. Exemples : `17/08`, `17/08/2025`, `demain` et `16h`, `09:30`."
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

        prev, oneh = compute_reminders(event_dt, PARIS_TZ)

        ev = Event(
            id=uuid.uuid4().hex[:8],
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

        # Confirmation en DM
        prev_txt = f"Veille 21h : {prev.time_iso}" if prev else "Veille 21h : (déjà passée, non planifiée)"
        oneh_txt = f"-1h : {oneh.time_iso}" if oneh else "-1h : (déjà passée, non planifiée)"
        confirm = (f"✅ **Événement enregistré**\n"
                   f"• Quand : {event_dt.strftime('%d/%m/%Y %H:%M')} (Europe/Paris)\n"
                   f"• Quoi  : {ev.title}\n"
                   f"• Rappels → {prev_txt} | {oneh_txt}\n"
                   f"• ID : `{ev.id}`")
        try:
            await ctx.author.send(confirm)
        except discord.Forbidden:
            await ctx.reply("✅ Événement enregistré (DM fermé : impossible d’envoyer la confirmation).", mention_author=False, delete_after=8)

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
            lines = []
            for evt_dt, e in events[:50]:
                lines.append(f"• `{e['id']}` — {evt_dt.strftime('%d/%m/%Y %H:%M')} — {e['title']}")
            txt = "**Tes événements à venir :**\n" + "\n".join(lines)

        try:
            await ctx.author.send(txt)
        except discord.Forbidden:
            await ctx.reply("✉️ Ouvre tes DM pour recevoir la liste.", mention_author=False, delete_after=8)

    @commands.command(name="cal_del")
    async def delete_event(self, ctx, event_id: str = None):
        """
        !cal_del <id>  -> suppression directe
        !cal_del       -> en DM : menu déroulant pour choisir l'évènement à supprimer
        """
        data = _load_data()
        # Si ID fourni -> suppression directe
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

        # Sinon : construire une vue avec Select en DM
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

        # Trier par date
        user_events.sort(key=lambda e: datetime.fromisoformat(e["event_iso"]))

        # Message récap + menu
        header_lines = []
        for e in user_events[:50]:  # recap textuel complet
            dt = datetime.fromisoformat(e["event_iso"]).astimezone(PARIS_TZ)
            header_lines.append(f"• `{e['id']}` — {dt.strftime('%d/%m/%Y %H:%M')} — {e['title']}")
        header = "**Sélectionne un événement à supprimer :**\n" + "\n".join(header_lines)
        view = DeleteEventView(self, ctx.author.id, user_events)

        try:
            await ctx.author.send(header, view=view)
        except discord.Forbidden:
            await ctx.reply("❌ Ouvre tes DM pour choisir l’événement à supprimer.", mention_author=False, delete_after=8)
        else:
            # S'il y a plus de 25 évènements, on le dit (Select max 25)
            if len(user_events) > 25:
                try:
                    await ctx.author.send("ℹ️ Tu as plus de 25 évènements : utilise `!cal_del <id>` pour ceux non listés dans le menu.")
                except Exception:
                    pass

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

            # Envoi des rappels si non envoyés
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

        # Purge quotidienne à 23:30 (heure de Paris) : supprimer tous les évènements du jour qui sont passés
        if (self.last_daily_cleanup_date != today_local) and (now_paris.hour == 23 and now_paris.minute >= 30):
            new_keep = []
            for e in keep_events:
                try:
                    evt_dt = datetime.fromisoformat(e["event_iso"]).astimezone(PARIS_TZ)
                except Exception:
                    continue
                # si l'événement est aujourd'hui ET déjà terminé, on le supprime
                if evt_dt.date() == today_local and evt_dt <= now_paris:
                    changed = True
                    continue
                new_keep.append(e)
            keep_events = new_keep
            self.last_daily_cleanup_date = today_local
            logger.info("[Calendar] Purge quotidienne 23:30 exécutée.")

        # Fallback : si le bot a raté la purge (offline), on supprime les évènements de plus de 2 jours
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
