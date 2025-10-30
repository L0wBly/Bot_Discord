# cogs/mangadex.py

# ===== Imports =====
import os
import re
import aiohttp
import asyncio
from typing import Any, Dict, List, Optional, Tuple

import discord
from discord.ext import commands

# ===== Config =====
try:
    from config import MANGADEX_TOKEN as CFG_MD_TOKEN  # type: ignore
except Exception:
    CFG_MD_TOKEN = None

# ===== Constants =====
MANGADEX_API = "https://api.mangadex.org"
UPLOADS_BASE = "https://uploads.mangadex.org"
UUID_RE = re.compile(r"(?P<id>[0-9a-fA-F]{8}\-[0-9a-fA-F]{4}\-[0-9a-fA-F]{4}\-[0-9a-fA-F]{4}\-[0-9a-fA-F]{12})")
LANG_RE = re.compile(r"^[a-z]{2}(?:-[a-z]{2})?$")
CH_RE_1 = re.compile(r'^(?:c|ch|chap|chapter)[:=](.+)$', re.I)
CH_RE_2 = re.compile(r'^#(.+)$')

# ===== Utils =====
def env_token() -> Optional[str]:
    return CFG_MD_TOKEN or os.getenv("MANGADEX_TOKEN")

def clean_lang(x: Optional[str]) -> Optional[str]:
    if not x:
        return None
    x = x.strip().lower().replace("_", "-").rstrip(",.;:")
    return x if LANG_RE.match(x) else None

def extract_uuid(text: str) -> Optional[str]:
    m = UUID_RE.search(text)
    return m.group("id") if m else None

def pick_title(attr_title: Dict[str, str]) -> str:
    for k in ("fr", "en", "ja", "ja-ro", "ko", "zh"):
        if k in attr_title and attr_title[k]:
            return attr_title[k]
    return next(iter(attr_title.values())) if attr_title else "Sans titre"

def cover_from_relationships(manga_id: str, relationships: List[Dict[str, Any]]) -> Optional[str]:
    for rel in relationships:
        if rel.get("type") == "cover_art":
            file_name = rel.get("attributes", {}).get("fileName")
            if file_name:
                return f"{UPLOADS_BASE}/covers/{manga_id}/{file_name}.512.jpg"
    return None

def tags_list(tag_objs: List[Dict[str, Any]]) -> List[str]:
    out = []
    for t in tag_objs:
        name = t.get("attributes", {}).get("name", {})
        if isinstance(name, dict):
            out.append(name.get("fr") or name.get("en") or next(iter(name.values()), None))
    return [t for t in out if t]

# ===== HTTP Client =====
class MangaDexHTTP:
    def __init__(self, token: Optional[str] = None):
        self.token = token
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session and not self._session.closed:
            return self._session
        timeout = aiohttp.ClientTimeout(total=20)
        self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def get(self, path: str, params: List[Tuple[str, str]] | Dict[str, Any] | None = None) -> Dict[str, Any]:
        session = await self._get_session()
        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        url = f"{MANGADEX_API}{path}"
        async with session.get(url, headers=headers, params=params) as r:
            if r.status >= 400:
                text = await r.text()
                raise RuntimeError(f"MangaDex GET {path} -> HTTP {r.status}: {text[:300]}")
            return await r.json()

    async def head_ok(self, url: str) -> bool:
        session = await self._get_session()
        try:
            async with session.head(url) as r:
                return r.status < 400
        except Exception:
            return False

# ===== Discord UI =====
class SearchPaginator(discord.ui.View):
    def __init__(self, embeds: List[discord.Embed], author_id: int, timeout: int = 60):
        super().__init__(timeout=timeout)
        self.embeds = embeds
        self.index = 0
        self.author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user and interaction.user.id == self.author_id

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index = (self.index - 1) % len(self.embeds)
        await interaction.response.edit_message(embed=self.embeds[self.index], view=self)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index = (self.index + 1) % len(self.embeds)
        await interaction.response.edit_message(embed=self.embeds[self.index], view=self)

# ===== Cog =====
class MangaDex(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.http = MangaDexHTTP(token=env_token())

    def cog_unload(self):
        asyncio.create_task(self.http.close())

    @commands.group(name="manga", invoke_without_command=True)
    async def manga_root(self, ctx: commands.Context):
        prefix = ctx.prefix or "!"
        embed = discord.Embed(
            title="📚 Commandes MangaDex",
            description=(
                f"`{prefix}manga search <titre>`\n"
                f"`{prefix}manga info <id|url|titre>`\n"
                f"`{prefix}manga chapters <id|url|titre> <lang> [limit] [c:10|#10]`"
            ),
            color=discord.Color.orange(),
        )
        await ctx.reply(embed=embed, mention_author=False)

    @manga_root.command(name="search")
    async def manga_search(self, ctx: commands.Context, *, query: str):
        params: List[Tuple[str, str]] = [
            ("title", query),
            ("limit", "10"),
            ("includes[]", "cover_art"),
            ("includes[]", "author"),
            ("includes[]", "artist"),
            ("contentRating[]", "safe"),
            ("contentRating[]", "suggestive"),
        ]
        data = await self.http.get("/manga", params)
        results = data.get("data", [])
        if not results:
            await ctx.reply("Aucun résultat.", mention_author=False)
            return

        embeds: List[discord.Embed] = []
        for item in results:
            manga_id = item.get("id")
            attr = item.get("attributes", {})
            rels = item.get("relationships", [])
            title = pick_title(attr.get("title", {}))
            alt_titles = [pick_title(x) for x in attr.get("altTitles", []) if isinstance(x, dict)]
            year = attr.get("year")
            status = attr.get("status")
            tgs = tags_list(attr.get("tags", []))
            cover_url = cover_from_relationships(manga_id, rels)

            desc_parts = []
            if alt_titles:
                desc_parts.append("• Titres alternatifs : " + ", ".join(alt_titles[:3]))
            if year:
                desc_parts.append(f"• Année : {year}")
            if status:
                desc_parts.append(f"• Statut : {status}")
            if tgs:
                desc_parts.append("• Tags : " + ", ".join(tgs[:8]))
            desc_parts.append(f"• Lien : https://mangadex.org/title/{manga_id}")

            embed = discord.Embed(
                title=f"{title}",
                description="\n".join(desc_parts),
                color=discord.Color.blurple(),
            )
            if cover_url and await self.http.head_ok(cover_url):
                embed.set_thumbnail(url=cover_url)
            embed.set_footer(text=f"ID: {manga_id}")
            embeds.append(embed)

        if len(embeds) == 1:
            await ctx.reply(embed=embeds[0], mention_author=False)
        else:
            view = SearchPaginator(embeds, author_id=ctx.author.id)
            await ctx.reply(embed=embeds[0], view=view, mention_author=False)

    @manga_root.command(name="info")
    async def manga_info(self, ctx: commands.Context, *, ref: str):
        manga_id = extract_uuid(ref)
        if not manga_id:
            params: List[Tuple[str, str]] = [
                ("title", ref),
                ("limit", "1"),
                ("includes[]", "cover_art"),
            ]
            data = await self.http.get("/manga", params)
            items = data.get("data", [])
            if not items:
                await ctx.reply("Introuvable.", mention_author=False)
                return
            manga_id = items[0]["id"]

        data = await self.http.get(
            f"/manga/{manga_id}",
            [("includes[]", "cover_art"), ("includes[]", "author"), ("includes[]", "artist")],
        )
        obj = data.get("data")
        if not obj:
            await ctx.reply("Introuvable.", mention_author=False)
            return

        attr = obj.get("attributes", {})
        rels = obj.get("relationships", [])
        title = pick_title(attr.get("title", {}))
        alt_titles = [pick_title(x) for x in attr.get("altTitles", []) if isinstance(x, dict)]
        desc = attr.get("description", {})
        desc_text = desc.get("fr") or desc.get("en") or next(iter(desc.values()), "")
        desc_text = (desc_text or "").strip()
        if len(desc_text) > 900:
            desc_text = desc_text[:900] + "…"
        year = attr.get("year")
        status = attr.get("status")
        tgs = tags_list(attr.get("tags", []))
        author_names = [r.get("attributes", {}).get("name") for r in rels if r.get("type") in ("author", "artist")]
        cover_url = cover_from_relationships(manga_id, rels)

        embed = discord.Embed(
            title=f"{title}",
            url=f"https://mangadex.org/title/{manga_id}",
            description=desc_text or "—",
            color=discord.Color.green(),
        )
        if cover_url and await self.http.head_ok(cover_url):
            embed.set_thumbnail(url=cover_url)
        fields = [
            ("Année", str(year) if year else "—", True),
            ("Statut", status or "—", True),
            ("Auteurs/Artistes", ", ".join([a for a in author_names if a]) or "—", False),
            ("Tags", ", ".join(tgs[:12]) or "—", False),
            ("ID", manga_id, False),
        ]
        for n, v, inline in fields:
            embed.add_field(name=n, value=v, inline=inline)

        await ctx.reply(embed=embed, mention_author=False)

    @manga_root.command(name="chapters")
    async def manga_chapters(self, ctx: commands.Context, *, args: str):
        parts = args.split()
        if len(parts) < 2:
            await ctx.reply(
                "❌ Langue requise.\n"
                "Usage : `!manga chapters <id|url|titre> <lang> [limit] [c:10|#10]`",
                mention_author=False,
            )
            return

        ref = parts[0]
        lang: Optional[str] = None
        limit = 10
        chapter: Optional[str] = None

        for p in parts[1:]:
            cand = clean_lang(p)
            if cand and not lang:
                lang = cand
                continue
            m = CH_RE_1.match(p) or CH_RE_2.match(p)
            if m:
                chapter = m.group(1).strip()
                continue
            if p.isdigit():
                limit = max(1, min(30, int(p)))
                continue

        if not lang:
            await ctx.reply(
                "❌ Langue invalide ou manquante. Utilise un code comme `fr`, `en`, `pt-br`.\n"
                "Usage : `!manga chapters <id|url|titre> <lang> [limit] [c:10|#10]`",
                mention_author=False,
            )
            return

        manga_id = extract_uuid(ref)
        if not manga_id:
            sdata = await self.http.get("/manga", [("title", ref), ("limit", "1")])
            items = sdata.get("data", [])
            if not items:
                await ctx.reply("Manga introuvable.", mention_author=False)
                return
            manga_id = items[0]["id"]

        params: List[Tuple[str, str]] = [
            ("manga", manga_id),
            ("translatedLanguage[]", lang),
            ("limit", str(limit)),
            ("includes[]", "scanlation_group"),
            ("includes[]", "manga"),
            ("includeFutureUpdates", "0"),
        ]
        if chapter:
            params.append(("chapter", chapter))
            params.append(("order[chapter]", "asc"))
        else:
            params.append(("order[chapter]", "desc"))

        try:
            cdata = await self.http.get("/chapter", params)
        except Exception as e:
            await ctx.reply(f"Erreur API MangaDex: {e}", mention_author=False)
            return

        chs = cdata.get("data", [])
        if not chs:
            if chapter:
                await ctx.reply(f"Aucun chapitre `{chapter}` trouvé en `{lang}`.", mention_author=False)
            else:
                await ctx.reply(f"Aucun chapitre trouvé pour la langue `{lang}`.", mention_author=False)
            return

        lines = []
        for c in chs:
            cid = c.get("id")
            a = c.get("attributes", {})
            ch_no = a.get("chapter") or "—"
            vol = a.get("volume") or "—"
            title = a.get("title") or ""
            title = title if len(title) <= 80 else title[:77] + "…"
            link = f"https://mangadex.org/chapter/{cid}"
            lines.append(f"• Ch. **{ch_no}** (Vol. {vol}) — {title or '_sans titre_'} — [Lire]({link})")

        head = f"Chapitre {chapter} • {lang.upper()}" if chapter else f"Derniers chapitres • {lang.upper()}"
        embed = discord.Embed(
            title=head,
            url=f"https://mangadex.org/title/{manga_id}",
            description="\n".join(lines)[:4000],
            color=discord.Color.purple(),
        )
        await ctx.reply(embed=embed, mention_author=False)

# ===== Setup =====
async def setup(bot: commands.Bot):
    await bot.add_cog(MangaDex(bot))
