import discord
from discord.ext import commands
import json
import random
import os
import asyncio

from utils.logger import logger
from config import GUESS_CHANNEL_ID, GAME_CATEGORY_ID  # Assurez-vous que ces IDs sont corrects dans config.py


class GuessCharacter(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Pour empêcher un même utilisateur de lancer plusieurs parties simultanément
        self.active_users = set()

        # Chemin vers le JSON des personnages
        self.json_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "création_list_personnage",
            "data",
            "personnages.json"
        )
        self.personnages = []
        self.load_characters()

    def load_characters(self):
        """Charge ou recharge la liste des personnages depuis le JSON."""
        try:
            with open(self.json_path, "r", encoding="utf-8") as f:
                self.personnages = json.load(f)
            logger.info(f"[GuessCharacter] {len(self.personnages)} personnages chargés depuis {self.json_path}")
        except FileNotFoundError:
            logger.error(f"[GuessCharacter] Le fichier {self.json_path} est introuvable.")
            self.personnages = []
        except json.JSONDecodeError as e:
            logger.error(f"[GuessCharacter] Erreur JSON dans {self.json_path} : {e}")
            self.personnages = []

    async def delete_message_after(self, message: discord.Message, delay: float):
        """Supprime un message après un délai (en secondes)."""
        await asyncio.sleep(delay)
        try:
            await message.delete()
        except (discord.Forbidden, discord.NotFound):
            pass
        except Exception as e:
            logger.error(f"[GuessCharacter] Erreur lors de la suppression du message {message.id} : {e}")

    @commands.command(name="guess", help="Lance un jeu pour deviner un personnage d'anime.")
    async def guess_character(self, ctx):
        # ────────────────────────────────────────────────────────────
        # 0) La commande ne fonctionne que dans le salon public “jeu”
        if ctx.channel.id != GUESS_CHANNEL_ID:
            asyncio.create_task(self.delete_message_after(ctx.message, 0))
            err = await ctx.send(f"⚠️ Cette commande n’est disponible que dans le salon <#{GUESS_CHANNEL_ID}>.")
            asyncio.create_task(self.delete_message_after(err, 5))
            return

        # 1) On empêche l’utilisateur d’avoir plusieurs parties ouvertes en même temps
        if ctx.author.id in self.active_users:
            err = await ctx.send("⚠️ Vous avez déjà une partie en cours. Terminez-la avant d'en lancer une nouvelle.")
            asyncio.create_task(self.delete_message_after(err, 5))
            return

        # 2) Vérifie que la catégorie de jeu existe
        guild = ctx.guild
        category = guild.get_channel(GAME_CATEGORY_ID)
        if category is None or not isinstance(category, discord.CategoryChannel):
            err = await ctx.send("⚠️ Impossible de trouver la catégorie de jeu. Contactez un administrateur.")
            asyncio.create_task(self.delete_message_after(err, 5))
            return

        # 3) On marque l’utilisateur comme “en partie”
        self.active_users.add(ctx.author.id)

        # 4) Recharge la liste des personnages
        self.load_characters()
        if not self.personnages:
            warning = await ctx.send("⚠️ Aucun personnage trouvé dans `personnages.json`. Vérifiez le chemin.")
            logger.warning("[GuessCharacter] Aucune donnée, commande annulée.")
            self.active_users.discard(ctx.author.id)
            asyncio.create_task(self.delete_message_after(warning, 5))
            return

        # 5) On supprime la commande originale après 2 secondes
        asyncio.create_task(self.delete_message_after(ctx.message, 2))

        # 6) Création du salon privé pour l’utilisateur
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
                reason=f"Salon privé GuessCharacter pour {ctx.author}"
            )
        except Exception as e:
            logger.error(f"[GuessCharacter] Impossible de créer le salon privé pour {ctx.author} : {e}")
            self.active_users.discard(ctx.author.id)
            err = await ctx.send("⚠️ Une erreur est survenue lors de la création du salon privé.")
            asyncio.create_task(self.delete_message_after(err, 5))
            return

        # ────────────────────────────────────────────────────────────
        # 7) Dans le salon public, on propose un bouton “Ouvrir le salon”
        channel_url = f"https://discord.com/channels/{guild.id}/{game_channel.id}"

        class OpenChannelView(discord.ui.View):
            def __init__(self, url: str):
                super().__init__(timeout=None)
                self.add_item(
                    discord.ui.Button(
                        label="🕹️ Ouvrir le salon de jeu",
                        style=discord.ButtonStyle.link,
                        url=url
                    )
                )

        view_invite = OpenChannelView(channel_url)
        notice = await ctx.send(
            f"{ctx.author.mention}, votre salon privé de jeu est prêt :",
            view=view_invite
        )
        asyncio.create_task(self.delete_message_after(notice, 10))

        # 8) Message de bienvenue dans le salon privé
        await game_channel.send(f"{ctx.author.mention}, bienvenue dans votre salon de jeu ! Lancez vos tentatives ici.")

        # ────────────────────────────────────────────────────────────
        # Fonction interne pour choisir un nouveau personnage aléatoire
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

        # ────────────────────────────────────────────────────────────
        # Vue avec les boutons “Retour au salon public” + “Rejouer 🔄”
        class EndGameView(discord.ui.View):
            def __init__(self, public_url: str):
                super().__init__(timeout=None)
                # Bouton “Retour au salon public” (lien)
                self.add_item(
                    discord.ui.Button(
                        label="↩️ Retour au salon public",
                        style=discord.ButtonStyle.link,
                        url=public_url
                    )
                )
                # Bouton “Rejouer”
                self.add_item(
                    discord.ui.Button(
                        label="🔄 Rejouer",
                        style=discord.ButtonStyle.primary,
                        custom_id="replay_game"
                    )
                )

        # ────────────────────────────────────────────────────────────
        # Mise en place d’une suppression automatique si 15 minutes d’inactivité
        inactivity_task = None

        async def schedule_inactivity_deletion():
            await asyncio.sleep(15 * 60)  # 15 minutes
            if ctx.author.id in self.active_users:
                self.active_users.discard(ctx.author.id)
                try:
                    await game_channel.delete()
                except:
                    pass

        def reset_inactivity_timer():
            nonlocal inactivity_task
            if inactivity_task and not inactivity_task.done():
                inactivity_task.cancel()
            inactivity_task = asyncio.create_task(schedule_inactivity_deletion())

        # Dès qu’on a créé le salon, on lance le timer d’inactivité de 15 minutes
        reset_inactivity_timer()

        # ────────────────────────────────────────────────────────────
        # Boucle principale pour gérer plusieurs parties dans le même salon
        while True:
            # À chaque nouvelle partie, on charge un personnage
            char_data = choose_new_character()
            prenom = char_data["prenom"]
            nom = char_data["nom"]
            anime = char_data["anime"]
            image_url = char_data["image"]
            full_name = char_data["full_name"]
            noms_valides = char_data["valids"]

            logger.info(f"[GuessCharacter] {ctx.author} → personnage choisi : {full_name} ({anime})")

            # Variables de suivi du jeu
            attempts = 0
            max_attempts = 10
            found = False
            hint_level = 0   # Indice 0,1,2,3
            ended_by_skip = False

            # Tâche de timeout de 3 minutes
            timeout_task = None

            # ────────────────────────────────────────────────────────────
            # Fonction “single_timeout” (3 minutes sans interaction)
            async def single_timeout():
                nonlocal attempts, ended_by_skip, found, timeout_task
                try:
                    await asyncio.sleep(180)  # 3 minutes
                    if not found and not ended_by_skip and (ctx.author.id in self.active_users):
                        ended_by_skip = True
                        logger.info(
                            f"[GuessCharacter] Temps écoulé (3m sans action) pour {ctx.author} dans le salon {game_channel.id}."
                        )

                        # Embed final “Temps écoulé”
                        timeout_embed = discord.Embed(
                            title="⏲️ Temps écoulé !",
                            description=(
                                f"Le temps de 3 minutes sans interaction est écoulé.\n"
                                f"La réponse était **{full_name}** de *{anime}*."
                            ),
                            color=0xe67e22
                        )
                        if image_url:
                            timeout_embed.set_thumbnail(url=image_url)
                        timeout_embed.add_field(name="Tentatives utilisées", value=str(attempts), inline=True)

                        public_url = f"https://discord.com/channels/{guild.id}/{GUESS_CHANNEL_ID}"
                        view_end = EndGameView(public_url)
                        end_msg = await game_channel.send(embed=timeout_embed, view=view_end)

                        # Supprime l’embed initial (SkipView) s’il existe
                        await asyncio.sleep(0.1)
                        try:
                            if view_skip.main_embed_msg:
                                await view_skip.main_embed_msg.delete()
                        except:
                            pass

                        # ────────────────────────────────────────────────────────
                        # Maintenant : je n’utilise PAS de callback “OnClick” pour “Rejouer”.
                        # Je vais simplement *quitter* la coroutine single_timeout et laisser la boucle
                        # principale faire un "wait_for(interaction)" sur le bouton "replay_game".
                        # Dès qu’un nouveau cycle commence, on aura un nouveau personnage.

                        return  # On sort de single_timeout → on revient à la boucle principale

                except asyncio.CancelledError:
                    return  # Timer annulé (gagné ou abandonné)

            # On démarre le timer de 3 minutes
            timeout_task = asyncio.create_task(single_timeout())

            # ────────────────────────────────────────────────────────────
            # Vue pour les boutons “Skip ➡️” et “Changer 🔄”
            class SkipView(discord.ui.View):
                def __init__(self):
                    super().__init__(timeout=None)
                    self.main_embed_msg: discord.Message = None

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
                    nonlocal hint_level, attempts, ended_by_skip, timeout_task

                    # Toute interaction reset le timer d’inactivité 15 min
                    reset_inactivity_timer()

                    # Annule l’ancien timer de 3 minutes et en recrée un nouveau
                    timeout_task.cancel()
                    timeout_task = asyncio.create_task(single_timeout())

                    if found or ended_by_skip:
                        await interaction.response.defer()
                        return

                    # Si on est déjà au 3ᵉ indice → on désactive “Skip”
                    if hint_level == 3:
                        button.disabled = True
                        await interaction.response.edit_message(view=self)
                        return

                    # Si on était au 2ᵉ indice et qu’on reclique → passe au 3ᵉ indice + EndGameView
                    if hint_level == 2:
                        attempts = 9
                        hint_level = 3
                        new_embed = self.build_hint_embed(3, remaining=1)
                        await interaction.response.edit_message(embed=new_embed, view=view_end)
                        return

                    # Sinon, on monte d’un palier d’indice
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
                    nonlocal attempts, hint_level, found, timeout_task

                    # Toute interaction reset le timer d’inactivité 15 min
                    reset_inactivity_timer()

                    # Annule l’ancien timer de 3 minutes et en crée un nouveau
                    timeout_task.cancel()
                    timeout_task = asyncio.create_task(single_timeout())

                    if found or ended_by_skip:
                        await interaction.response.defer()
                        return

                    # On sélectionne un nouveau personnage aléatoire
                    new_data = choose_new_character()
                    prenom = new_data["prenom"]
                    nom = new_data["nom"]
                    anime = new_data["anime"]
                    image_url = new_data["image"]
                    full_name = new_data["full_name"]
                    noms_valides = new_data["valids"]

                    # Réinitialise l’état du jeu
                    attempts = 0
                    hint_level = 0
                    found = False

                    # Re-crée l’embed de départ
                    start_embed = discord.Embed(
                        title="🎲 Guess the Anime Character",
                        description=(
                            "Devinez ce personnage. Si vous êtes bloqué·e, cliquez sur **Skip ➡️** "
                            "pour un indice, ou sur **Changer 🔄** pour un autre personnage."
                        ),
                        color=0x3498db
                    )
                    start_embed.add_field(name="Tentatives restantes", value=str(max_attempts), inline=False)
                    if image_url:
                        start_embed.set_image(url=image_url)

                    # Réactive les boutons Skip/Changer et on édite le message principal
                    button.disabled = False
                    view_skip.children[0].disabled = False  # réactive “Skip”
                    await interaction.response.edit_message(embed=start_embed, view=self)

            # ────────────────────────────────────────────────────────────
            # Instanciation des vues pour cette partie
            view_skip = SkipView()
            # Pour EndGame (fin de partie), on enverra une instance de EndGameView(...) plus loin
            view_end = EndGameView(f"https://discord.com/channels/{guild.id}/{GUESS_CHANNEL_ID}")

            # ────────────────────────────────────────────────────────────
            # Envoi de l’embed initial (tentatives restantes + image + boutons) dans le salon privé
            start_embed = discord.Embed(
                title="🎲 Guess the Anime Character",
                description=(
                    "Devinez ce personnage. Si vous êtes bloqué·e, cliquez sur **Skip ➡️** "
                    "pour un indice, ou sur **Changer 🔄** pour un autre personnage."
                ),
                color=0x3498db
            )
            start_embed.add_field(name="Tentatives restantes", value=str(max_attempts), inline=False)
            if image_url:
                start_embed.set_image(url=image_url)

            initial_msg = await game_channel.send(embed=start_embed, view=view_skip)
            view_skip.main_embed_msg = initial_msg

            # ────────────────────────────────────────────────────────────
            # Boucle principale pour recevoir les tentatives de l’utilisateur
            def check_msg(m: discord.Message):
                return m.channel == game_channel and m.author.id == ctx.author.id and not m.author.bot

            while attempts < max_attempts:
                try:
                    user_msg = await self.bot.wait_for("message", check=check_msg)

                    # Toute interaction (envoi de message) reset le timer d’inactivité 15 min
                    reset_inactivity_timer()

                    # À chaque message (tentative), on annule l’ancien timer de 3 minutes et on en relance un nouveau
                    timeout_task.cancel()
                    timeout_task = asyncio.create_task(single_timeout())

                    # Si l’utilisateur retape “!guess” dans le salon privé, on l’ignore
                    if user_msg.content.strip().lower() == "!guess":
                        asyncio.create_task(self.delete_message_after(user_msg, 0))
                        continue

                    # On supprime immédiatement la tentative pour garder le salon propre
                    asyncio.create_task(self.delete_message_after(user_msg, 0))

                    # Si la partie est déjà terminée (timeout ou abandon), on arrête
                    if ended_by_skip:
                        break

                    contenu = user_msg.content.lower().strip()

                    # 17.a) Réponse correcte
                    if contenu in noms_valides:
                        found = True
                        attempts += 1
                        rest = max_attempts - attempts

                        success_embed = discord.Embed(
                            title="✅ Bravo !",
                            description=f"{user_msg.author.mention}, c’était bien **{full_name}** de *{anime}* !",
                            color=0x2ecc71
                        )
                        success_embed.set_thumbnail(url=image_url or "")
                        success_embed.add_field(name="Tentatives utilisées", value=str(attempts), inline=True)
                        success_embed.add_field(name="Tentatives restantes", value=str(rest), inline=True)

                        # Annule le timer de 3 minutes avant d’envoyer
                        timeout_task.cancel()

                        public_url = f"https://discord.com/channels/{guild.id}/{GUESS_CHANNEL_ID}"
                        view_end = EndGameView(public_url)
                        end_msg = await game_channel.send(embed=success_embed, view=view_end)
                        logger.info(f"[GuessCharacter] {user_msg.author} a trouvé {full_name} en {attempts} tentative(s).")

                        # Désactive le bouton Skip s’il reste actif
                        try:
                            view_skip.children[0].disabled = True
                            await view_skip.main_embed_msg.edit(view=view_skip)
                        except:
                            pass

                        # Supprime l’embed initial (SkipView)
                        await asyncio.sleep(0.1)
                        try:
                            if view_skip.main_embed_msg:
                                await view_skip.main_embed_msg.delete()
                        except:
                            pass

                        # ────────────────────────────────────────────────────────
                        # ICI : on stoppe la boucle de guesses et on attend l’interaction “Rejouer”
                        # Création d’une tâche qui supprime le salon au bout de 30 s, si pas de replay
                        async def delete_after_30s():
                            await asyncio.sleep(30.0)
                            if ctx.author.id in self.active_users:
                                self.active_users.discard(ctx.author.id)
                                try:
                                    await game_channel.delete()
                                except:
                                    pass

                        deletion_task = asyncio.create_task(delete_after_30s())

                        # On attend un clic sur “Rejouer” (custom_id="replay_game") dans les 30 s
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
                            # Si l’utilisateur clique sur “Rejouer” :
                            if interaction.data.get("custom_id") == "replay_game":
                                await interaction.response.defer()
                                deletion_task.cancel()       # On annule la suppression du salon
                                reset_inactivity_timer()    # Et on remet 15 min d’inactivité
                                break  # On sort du while attempts<max_attempts → relance la boucle principale
                        except asyncio.TimeoutError:
                            # Si 30 s s’écoulent sans clic, deletion_task aura supprimé le salon
                            return  # On quitte la commande car le salon n’existe plus

                        # Si on a break pour “Rejouer”, on revient à la boucle principale
                        continue

                    # 17.b) Réponse incorrecte
                    attempts += 1
                    rest = max_attempts - attempts

                    # Si un indice a déjà été dévoilé, on met à jour via build_hint_embed
                    if hint_level > 0:
                        emb = view_skip.build_hint_embed(hint_level, rest)
                        await view_skip.main_embed_msg.edit(embed=emb, view=view_skip)
                    else:
                        basic_embed = discord.Embed(
                            title="🎲 Guess the Anime Character",
                            description=(
                                "Devinez ce personnage. Si vous êtes bloqué·e, cliquez sur **Skip ➡️** pour un indice "
                                "ou sur **Changer 🔄** pour un autre personnage."
                            ),
                            color=0x3498db
                        )
                        basic_embed.add_field(name="Tentatives restantes", value=str(rest), inline=False)
                        if image_url:
                            basic_embed.set_image(url=image_url)
                        await view_skip.main_embed_msg.edit(embed=basic_embed, view=view_skip)

                    # Gestion des indices automatiques à 4, 6 et 9 tentatives
                    if attempts in (4, 6, 9) and attempts < max_attempts:
                        if attempts == max_attempts - 1:
                            # À la 9ᵉ tentative → indice n°3 puis EndGameView
                            hint_embed = view_skip.build_hint_embed(3, rest)
                            await view_skip.main_embed_msg.edit(embed=hint_embed, view=view_end)
                            hint_level = 3
                        else:
                            # À la 4ᵉ ou 6ᵉ tentative → 1ᵉ ou 2ᵉ indice
                            if attempts == 4:
                                hint_level = 1
                            else:  # attempts == 6
                                hint_level = 2
                            hint_embed = view_skip.build_hint_embed(hint_level, rest)
                            await view_skip.main_embed_msg.edit(embed=hint_embed, view=view_skip)

                    logger.info(f"[GuessCharacter] {user_msg.author} a tenté «{user_msg.content}», incorrect ({attempts}/10).")

                    if attempts >= max_attempts:
                        break

                except asyncio.CancelledError:
                    break

            # ────────────────────────────────────────────────────────────
            # 18) Défaite “classique” si on sort de la boucle sans found ni ended_by_skip
            if not found and not ended_by_skip:
                timeout_task.cancel()
                end_embed = discord.Embed(
                    title="🔚 Partie terminée",
                    description=(f"Aucune tentative restante.\nLa réponse était **{full_name}** de *{anime}*."),
                    color=0xe67e22
                )
                end_embed.set_thumbnail(url=image_url or "")
                end_embed.add_field(name="Tentatives utilisées", value=str(max_attempts), inline=True)

                public_url = f"https://discord.com/channels/{guild.id}/{GUESS_CHANNEL_ID}"
                view_end = EndGameView(public_url)
                end_msg = await game_channel.send(embed=end_embed, view=view_end)
                logger.info(f"[GuessCharacter] Échec du jeu pour {full_name} après 10 tentatives.")

                # Désactive “Skip” si présent
                try:
                    view_skip.children[0].disabled = True
                    await view_skip.main_embed_msg.edit(view=view_skip)
                except:
                    pass

                # Supprime l’embed initial (SkipView)
                await asyncio.sleep(0.1)
                try:
                    if view_skip.main_embed_msg:
                        await view_skip.main_embed_msg.delete()
                except:
                    pass

                # ────────────────────────────────────────────────────────────
                # Création d’une tâche de suppression automatique dans 30 s
                async def delete_after_30s():
                    await asyncio.sleep(30.0)
                    if ctx.author.id in self.active_users:
                        self.active_users.discard(ctx.author.id)
                        try:
                            await game_channel.delete()
                        except:
                            pass

                deletion_task_defeat = asyncio.create_task(delete_after_30s())

                # On attend 30 s pour “Rejouer”
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
                    # Si l’utilisateur clique sur “Rejouer”
                    if interaction.data.get("custom_id") == "replay_game":
                        await interaction.response.defer()
                        deletion_task_defeat.cancel()  # On annule la suppression après 30 s
                        reset_inactivity_timer()       # On remet 15 min d’inactivité
                        continue  # Retour à la boucle principale pour créer une nouvelle partie
                except asyncio.TimeoutError:
                    # Si 30 s passent sans clic, delete_after_30s() supprime le salon
                    return

            # ────────────────────────────────────────────────────────────
            # Si on atteint ici, c’est qu’on a demandé “Rejouer” dans l’une des conditions
            # Annule le timer de 3 minutes en cours et on relance la boucle principale
            try:
                timeout_task.cancel()
            except:
                pass
            # La boucle while True repart automatiquement pour une nouvelle partie

        # FIN DE LA MÉCANIQUE DE JEU

    async def cog_unload(self):
        # Si le bot redémarre, on s'assure de libérer tous les utilisateurs actifs
        self.active_users.clear()


async def setup(bot):
    await bot.add_cog(GuessCharacter(bot))
    logger.info("[GuessCharacter] Cog ajouté au bot")
