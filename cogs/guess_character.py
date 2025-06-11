import json
import os
import random
import asyncio
from collections import defaultdict

import discord
from discord.ext import commands

from utils.logger import logger
from config import GUESS_CHANNEL_ID, GAME_CATEGORY_ID, EXCLUDED_CHANNEL_IDS

creation_locks = defaultdict(asyncio.Lock)
active_guess_ctx = set()
PLAYER_MARKER = "player_id:"

class GuessCharacter(commands.Cog, name="Jeu"):
    def __init__(self, bot):
        self.bot = bot
        self.json_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "guess_character",
            "data",
            "personnages.json"
        )
        self.personnages = []
        self.load_characters()

    def load_characters(self):
        try:
            with open(self.json_path, "r", encoding="utf-8") as f:
                self.personnages = json.load(f)
            logger.info(f"[GuessCharacter] {len(self.personnages)} personnages chargés depuis {self.json_path}")
        except Exception as e:
            logger.error(f"[GuessCharacter] Erreur lors du chargement : {e}")
            self.personnages = []

    async def delete_message_after(self, message: discord.Message, delay: float):
        await asyncio.sleep(delay)
        try:
            await message.delete()
        except Exception:
            pass

    def find_existing_private_channel(self, guild, user_id):
        for channel in guild.text_channels:
            if (
                channel.category_id == GAME_CATEGORY_ID
                and channel.topic is not None
                and f"{PLAYER_MARKER}{user_id}" in channel.topic
            ):
                return channel
        return None

    @commands.command(
        name="guess",
        help="Lance un jeu pour deviner un personnage d'anime.",
    )
    async def guess_character(self, ctx):
        uniq_id = (ctx.message.id, ctx.author.id)
        if uniq_id in active_guess_ctx:
            return
        active_guess_ctx.add(uniq_id)

        try:
            if ctx.channel.id != GUESS_CHANNEL_ID:
                asyncio.create_task(self.delete_message_after(ctx.message, 0))
                err = await ctx.send(f"⚠️ Cette commande n’est disponible que dans le salon <#{GUESS_CHANNEL_ID}>.")
                asyncio.create_task(self.delete_message_after(err, 5))
                return

            guild = ctx.guild
            category = guild.get_channel(GAME_CATEGORY_ID)
            if not category or not isinstance(category, discord.CategoryChannel):
                err = await ctx.send("⚠️ Impossible de trouver la catégorie de jeu. Contactez un administrateur.")
                asyncio.create_task(self.delete_message_after(err, 5))
                return

            lock = creation_locks[ctx.author.id]
            async with lock:
                existing_channel = self.find_existing_private_channel(guild, ctx.author.id)

                if existing_channel is not None:
                    channel_url = f"https://discord.com/channels/{guild.id}/{existing_channel.id}"
                    class OpenChannelView(discord.ui.View):
                        def __init__(self, url: str):
                            super().__init__(timeout=None)
                            self.add_item(
                                discord.ui.Button(
                                    label="🕹️ Ouvrir le salon privé",
                                    style=discord.ButtonStyle.link,
                                    url=url
                                )
                            )
                    view_invite = OpenChannelView(channel_url)
                    notice = await ctx.send(
                        f"⚠️ {ctx.author.mention}, tu as déjà une partie en cours ici :",
                        view=view_invite
                    )
                    asyncio.create_task(self.delete_message_after(ctx.message, 2))
                    asyncio.create_task(self.delete_message_after(notice, 5))
                    return

                self.load_characters()
                if not self.personnages:
                    warning = await ctx.send("⚠️ Aucun personnage trouvé dans `personnages.json`. Vérifiez le chemin.")
                    logger.warning("[GuessCharacter] Aucune donnée, commande annulée.")
                    asyncio.create_task(self.delete_message_after(ctx.message, 2))
                    asyncio.create_task(self.delete_message_after(warning, 5))
                    return

                asyncio.create_task(self.delete_message_after(ctx.message, 2))

                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(view_channel=False),
                    ctx.author: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_messages=True),
                    guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_messages=True)
                }
                try:
                    game_channel = await guild.create_text_channel(
                        name=f"guess-{ctx.author.name}",
                        category=category,
                        overwrites=overwrites,
                        reason=f"Salon privé GuessCharacter pour {ctx.author}",
                        topic=f"{PLAYER_MARKER}{ctx.author.id}"
                    )
                    if game_channel.id not in EXCLUDED_CHANNEL_IDS:
                        EXCLUDED_CHANNEL_IDS.append(game_channel.id)
                except Exception as e:
                    logger.error(f"[GuessCharacter] Impossible de créer le salon privé pour {ctx.author} : {e}")
                    err = await ctx.send("⚠️ Une erreur est survenue lors de la création du salon privé.")
                    asyncio.create_task(self.delete_message_after(ctx.message, 2))
                    asyncio.create_task(self.delete_message_after(err, 5))
                    return

                channel_url = f"https://discord.com/channels/{guild.id}/{game_channel.id}"
                class OpenChannelView(discord.ui.View):
                    def __init__(self, url: str):
                        super().__init__(timeout=None)
                        self.add_item(
                            discord.ui.Button(
                                label="🕹️ Ouvrir le salon privé",
                                style=discord.ButtonStyle.link,
                                url=url
                            )
                        )
                view_invite = OpenChannelView(channel_url)
                notice = await ctx.send(
                    f"{ctx.author.mention}, votre salon privé est prêt :",
                    view=view_invite
                )
                asyncio.create_task(self.delete_message_after(notice, 10))

                await game_channel.send(f"{ctx.author.mention}, bienvenue dans votre salon ! Laissez vos tentatives ici.")

                # BOUCLE PRINCIPALE DU JEU
                while True:
                    # 1. Sélection du personnage
                    def choose_new_character():
                        perso = random.choice(self.personnages)
                        p_prenom = perso.get("prenom", "").strip()
                        p_nom = perso.get("nom", "").strip()
                        p_anime = perso.get("title", "Inconnu").strip()
                        p_image = perso.get("image", None)
                        p_full = f"{p_prenom} {p_nom}".strip()
                        p_valids = {p_prenom.lower(), p_nom.lower(), p_full.lower()}
                        return {
                            "prenom": p_prenom,
                            "nom": p_nom,
                            "anime": p_anime,
                            "image": p_image,
                            "full_name": p_full,
                            "valids": p_valids
                        }

                    char_data = choose_new_character()
                    prenom = char_data["prenom"]
                    nom = char_data["nom"]
                    anime = char_data["anime"]
                    image_url = char_data["image"]
                    full_name = char_data["full_name"]
                    noms_valides = char_data["valids"]

                    attempts = 0
                    max_attempts = 10
                    found = False
                    abandoned = False
                    hint_level = 0
                    inactivity_task = None

                    async def schedule_inactivity_deletion():
                        await asyncio.sleep(15 * 60)
                        try:
                            await game_channel.delete()
                        except:
                            pass
                    def reset_inactivity_timer():
                        nonlocal inactivity_task
                        if inactivity_task and not inactivity_task.done():
                            inactivity_task.cancel()
                        inactivity_task = asyncio.create_task(schedule_inactivity_deletion())

                    reset_inactivity_timer()

                    timeout_task = None
                    wait_message_task = None

                    async def single_timeout():
                        nonlocal attempts, abandoned, found, timeout_task
                        try:
                            await asyncio.sleep(180)
                            if not found and not abandoned:
                                abandoned = True
                                timeout_embed = discord.Embed(
                                    title="⏲️ Temps écoulé !",
                                    description=(f"Le temps de 3 minutes sans interaction est écoulé.\n"
                                                 f"La réponse était **{full_name}** de *{anime}*."),
                                    color=0xe67e22
                                )
                                if image_url:
                                    timeout_embed.set_thumbnail(url=image_url)
                                timeout_embed.add_field(name="Tentatives utilisées", value=str(attempts), inline=True)
                                view_end = EndGameView()
                                end_msg = await game_channel.send(embed=timeout_embed, view=view_end)
                                try:
                                    if view_skip.main_embed_msg:
                                        await view_skip.main_embed_msg.delete()
                                except:
                                    pass
                                if wait_message_task and not wait_message_task.done():
                                    wait_message_task.cancel()
                        except asyncio.CancelledError:
                            return

                    timeout_task = asyncio.create_task(single_timeout())

                    class EndGameView(discord.ui.View):
                        def __init__(self):
                            super().__init__(timeout=None)
                            self.add_item(
                                discord.ui.Button(
                                    label="🔄 Rejouer",
                                    style=discord.ButtonStyle.primary,
                                    custom_id="replay_game"
                                )
                            )

                    class SkipView(discord.ui.View):
                        def __init__(self):
                            super().__init__(timeout=None)
                            self.main_embed_msg = None

                        def build_hint_embed(self, level: int, remaining: int) -> discord.Embed:
                            if level == 1:
                                première_lettre = prenom[0] if prenom else ""
                                desc = (
                                    f"**Anime :** {anime}\n\n"
                                    f"**Indice n°1 –** Le prénom commence par **{première_lettre}…**"
                                )
                            elif level == 2:
                                moitié_prenom = prenom[: len(prenom)//2] if prenom else ""
                                deux_nom = nom[:2] if len(nom) >= 2 else nom
                                desc = (
                                    f"**Anime :** {anime}\n\n"
                                    f"**Indice n°2 –** La moitié du prénom est **{moitié_prenom}…**\n"
                                    f"Les 2 premières lettres du nom de famille sont **{deux_nom}…**"
                                )
                            else:
                                trois_quarts = prenom[: (len(prenom)*3)//4] if prenom else ""
                                moitié_nom = nom[: len(nom)//2] if nom else ""
                                desc = (
                                    f"**Anime :** {anime}\n\n"
                                    f"**Indice n°3 –** Les 3/4 du prénom sont **{trois_quarts}…**\n"
                                    f"Et la moitié du nom de famille est **{moitié_nom}…**"
                                )
                            embed = discord.Embed(title="💡 Indice", description=desc, color=0xf1c40f)
                            embed.add_field(name="Tentatives restantes", value=str(remaining), inline=False)
                            if image_url:
                                embed.set_image(url=image_url)
                            return embed

                        @discord.ui.button(label="Skip ➡️", style=discord.ButtonStyle.primary, custom_id="guess_skip_button")
                        async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                            nonlocal hint_level, attempts, abandoned, timeout_task
                            reset_inactivity_timer()
                            timeout_task.cancel()
                            timeout_task = asyncio.create_task(single_timeout())
                            if found or abandoned:
                                await interaction.response.defer()
                                return
                            if hint_level == 3:
                                button.disabled = True
                                await interaction.response.edit_message(view=self)
                                return
                            if hint_level == 2:
                                attempts = 9
                                hint_level = 3
                                new_embed = self.build_hint_embed(3, remaining=1)
                                button.disabled = True
                                await interaction.response.edit_message(embed=new_embed, view=self)
                                return
                            if hint_level == 0:
                                attempts = 4
                                hint_level = 1
                            elif hint_level == 1:
                                attempts = 6
                                hint_level = 2
                            restantes = max_attempts - attempts
                            emb = self.build_hint_embed(hint_level, restantes)
                            if hint_level == 3:
                                button.disabled = True
                            await interaction.response.edit_message(embed=emb, view=self)

                        @discord.ui.button(label="Changer 🔄", style=discord.ButtonStyle.secondary, custom_id="guess_change_button")
                        async def change_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                            nonlocal prenom, nom, anime, image_url, full_name, noms_valides
                            nonlocal attempts, hint_level, found, abandoned, timeout_task
                            reset_inactivity_timer()
                            timeout_task.cancel()
                            timeout_task = asyncio.create_task(single_timeout())
                            if found or abandoned:
                                await interaction.response.defer()
                                return
                            new_data = choose_new_character()
                            prenom = new_data["prenom"]
                            nom = new_data["nom"]
                            anime = new_data["anime"]
                            image_url = new_data["image"]
                            full_name = new_data["full_name"]
                            noms_valides = new_data["valids"]
                            attempts = 0
                            hint_level = 0
                            found = False
                            abandoned = False
                            start_embed = discord.Embed(
                                title="🎲 Guess the Anime Character",
                                description=(
                                    "Devinez ce personnage. Si vous êtes bloqué·e, cliquez sur **Skip ➡️** pour un indice, "
                                    "**Changer 🔄** pour un autre personnage, ou **Abandonner 🛑** pour renoncer."
                                ),
                                color=0x3498db
                            )
                            start_embed.add_field(name="Tentatives restantes", value=str(max_attempts), inline=False)
                            if image_url:
                                start_embed.set_image(url=image_url)
                            button.disabled = False
                            view_skip.children[0].disabled = False
                            view_skip.children[1].disabled = False
                            view_skip.children[2].disabled = False
                            await interaction.response.edit_message(embed=start_embed, view=self)

                        @discord.ui.button(label="Abandonner 🛑", style=discord.ButtonStyle.danger, custom_id="guess_abandon_button")
                        async def abandon_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                            nonlocal abandoned, timeout_task, wait_message_task
                            reset_inactivity_timer()
                            timeout_task.cancel()
                            if abandoned:
                                await interaction.response.defer()
                                return
                            abandoned = True
                            if wait_message_task and not wait_message_task.done():
                                wait_message_task.cancel()
                            await interaction.response.defer()

                    view_skip = SkipView()
                    view_end = EndGameView()
                    start_embed = discord.Embed(
                        title="🎲 Guess the Anime Character",
                        description=(
                            "Devinez ce personnage. Si vous êtes bloqué·e, cliquez sur **Skip ➡️** pour un indice, "
                            "**Changer 🔄** pour un autre personnage, ou **Abandonner 🛑** pour renoncer."
                        ),
                        color=0x3498db
                    )
                    start_embed.add_field(name="Tentatives restantes", value=str(max_attempts), inline=False)
                    if image_url:
                        start_embed.set_image(url=image_url)
                    initial_msg = await game_channel.send(embed=start_embed, view=view_skip)
                    view_skip.main_embed_msg = initial_msg

                    def check_msg(m: discord.Message):
                        return m.channel == game_channel and m.author.id == ctx.author.id and not m.author.bot

                    # ---- JEU (phase des tentatives) ----
                    while attempts < max_attempts and not abandoned and not found:
                        try:
                            wait_message_task = asyncio.create_task(self.bot.wait_for("message", check=check_msg))
                            user_msg = await wait_message_task
                            reset_inactivity_timer()
                            timeout_task.cancel()
                            timeout_task = asyncio.create_task(single_timeout())
                            if user_msg.content.strip().lower() == "!guess":
                                asyncio.create_task(self.delete_message_after(user_msg, 0))
                                continue
                            asyncio.create_task(self.delete_message_after(user_msg, 0))
                            contenu = user_msg.content.lower().strip()
                            if contenu in noms_valides:
                                found = True
                                attempts += 1
                                rest = max_attempts - attempts

                                # ==== AJOUT DU SCORE AU CLASSEMENT ! ====
                                try:
                                    classement_cog = self.bot.get_cog("Classement")
                                    if classement_cog:
                                        classement_cog.add_guess_win(ctx.author.id)
                                except Exception as e:
                                    logger.error(f"Erreur en ajoutant le score guess au classement: {e}")

                                success_embed = discord.Embed(
                                    title="✅ Bravo !",
                                    description=f"{user_msg.author.mention}, c’était bien **{full_name}** de *{anime}* !",
                                    color=0x2ecc71
                                )
                                success_embed.set_thumbnail(url=image_url or "")
                                success_embed.add_field(name="Tentatives utilisées", value=str(attempts), inline=True)
                                success_embed.add_field(name="Tentatives restantes", value=str(rest), inline=True)
                                timeout_task.cancel()
                                end_msg = await game_channel.send(embed=success_embed, view=view_end)
                                try:
                                    view_skip.children[0].disabled = True
                                    view_skip.children[1].disabled = True
                                    view_skip.children[2].disabled = True
                                    await view_skip.main_embed_msg.edit(view=view_skip)
                                except:
                                    pass
                                await asyncio.sleep(0.1)
                                try:
                                    if view_skip.main_embed_msg:
                                        await view_skip.main_embed_msg.delete()
                                except:
                                    pass

                                # --------- Attente bouton "Rejouer" ----------
                                restart_game = await self.wait_for_replay_button(game_channel, ctx, end_msg)
                                if restart_game:
                                    break  # Recommencer une partie (sort du while attempts, re-rentre dans while True)
                                else:
                                    # pas de replay, fermeture du salon
                                    await asyncio.sleep(30)
                                    try:
                                        await game_channel.delete()
                                    except:
                                        pass
                                    return
                            attempts += 1
                            rest = max_attempts - attempts
                            if hint_level > 0:
                                emb = view_skip.build_hint_embed(hint_level, rest)
                                await view_skip.main_embed_msg.edit(embed=emb, view=view_skip)
                            else:
                                basic_embed = discord.Embed(
                                    title="🎲 Guess the Anime Character",
                                    description=(
                                        "Devinez ce personnage. Si vous êtes bloqué·e, cliquez sur **Skip ➡️** pour un indice, "
                                        "**Changer 🔄** pour un autre personnage, ou **Abandonner 🛑** pour renoncer."
                                    ),
                                    color=0x3498db
                                )
                                basic_embed.add_field(name="Tentatives restantes", value=str(rest), inline=False)
                                if image_url:
                                    basic_embed.set_image(url=image_url)
                                await view_skip.main_embed_msg.edit(embed=basic_embed, view=view_skip)
                            if attempts in (4, 6, 9) and attempts < max_attempts:
                                if attempts == max_attempts - 1:
                                    hint_embed = view_skip.build_hint_embed(3, rest)
                                    await view_skip.main_embed_msg.edit(embed=hint_embed, view=view_skip)
                                    hint_level = 3
                                else:
                                    if attempts == 4:
                                        hint_level = 1
                                    else:
                                        hint_level = 2
                                    hint_embed = view_skip.build_hint_embed(hint_level, rest)
                                    await view_skip.main_embed_msg.edit(embed=hint_embed, view=view_skip)
                        except asyncio.CancelledError:
                            break

                    timeout_task.cancel()

                    # ----- ABANDON/ECHEC -----
                    if abandoned and not found:
                        abandon_embed = discord.Embed(
                            title="🔚 Partie abandonnée",
                            description=(f"⚠️ Vous avez cliqué sur **Abandonner**.\n"
                                         f"La réponse était **{full_name}** de *{anime}*."),
                            color=0xe67e22
                        )
                        if image_url:
                            abandon_embed.set_thumbnail(url=image_url)
                        abandon_embed.add_field(name="Tentatives utilisées", value=str(attempts), inline=True)
                        end_msg = await game_channel.send(embed=abandon_embed, view=view_end)
                        try:
                            view_skip.children[0].disabled = True
                            view_skip.children[1].disabled = True
                            view_skip.children[2].disabled = True
                            await view_skip.main_embed_msg.edit(view=view_skip)
                        except:
                            pass
                        restart_game = await self.wait_for_replay_button(game_channel, ctx, end_msg)
                        if restart_game:
                            continue
                        else:
                            await asyncio.sleep(30)
                            try:
                                await game_channel.delete()
                            except:
                                pass
                            return

                    elif not found and not abandoned:
                        defeat_embed = discord.Embed(
                            title="🔚 Partie terminée",
                            description=(f"Aucune tentative restante.\nLa réponse était **{full_name}** de *{anime}*."),
                            color=0xe67e22
                        )
                        defeat_embed.set_thumbnail(url=image_url or "")
                        defeat_embed.add_field(name="Tentatives utilisées", value=str(max_attempts), inline=True)
                        end_msg = await game_channel.send(embed=defeat_embed, view=view_end)
                        try:
                            view_skip.children[0].disabled = True
                            view_skip.children[1].disabled = True
                            view_skip.children[2].disabled = True
                            await view_skip.main_embed_msg.edit(view=view_skip)
                        except:
                            pass
                        restart_game = await self.wait_for_replay_button(game_channel, ctx, end_msg)
                        if restart_game:
                            continue
                        else:
                            await asyncio.sleep(30)
                            try:
                                await game_channel.delete()
                            except:
                                pass
                            return

                    # Si la partie a été rejouée, on reboucle sur while True
                    if found:
                        continue
                    break  # si aucune condition de replay

        finally:
            active_guess_ctx.discard(uniq_id)

    async def wait_for_replay_button(self, game_channel, ctx, end_msg):
        # Fonction utilitaire pour attendre le bouton "Rejouer"
        def check_interaction(interaction: discord.Interaction):
            return (
                interaction.user.id == ctx.author.id
                and interaction.message.id == end_msg.id
                and interaction.data.get("custom_id") == "replay_game"
            )
        try:
            interaction = await self.bot.wait_for(
                "interaction", timeout=30.0, check=check_interaction
            )
            if interaction.data.get("custom_id") == "replay_game":
                await interaction.response.defer()
                return True
        except asyncio.TimeoutError:
            return False

    async def cog_unload(self):
        pass

async def setup(bot):
    await bot.add_cog(GuessCharacter(bot))
    logger.info("[GuessCharacter] Cog ajouté au bot")
