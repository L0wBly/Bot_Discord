import discord
from discord.ext import commands
import json
import random
import os
import asyncio
from datetime import timezone

from utils.logger import logger
from config import GUESS_CHANNEL_ID  # Assurez-vous d’avoir défini GUESS_CHANNEL_ID dans config.py


class GuessCharacter(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # On garde la trace des salons où un jeu est en cours
        self.active_channels = set()

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
        # ───────────────────────────────────────────────────────────────────────────
        # 0) Vérifie que la commande est exécutée dans le salon autorisé
        if ctx.channel.id != GUESS_CHANNEL_ID:
            # Supprime instantanément le message de l’utilisateur
            asyncio.create_task(self.delete_message_after(ctx.message, 0))
            # Envoie l’erreur et la supprime après 5 secondes
            err = await ctx.send(f"⚠️ Cette commande n’est disponible que dans le salon <#{GUESS_CHANNEL_ID}>.")
            asyncio.create_task(self.delete_message_after(err, 5))
            return

        # 1) Vérifie qu’il n’y a pas déjà un jeu en cours dans ce canal
        if ctx.channel.id in self.active_channels:
            err = await ctx.send("⚠️ Un jeu est déjà en cours dans ce salon, veuillez patienter…")
            asyncio.create_task(self.delete_message_after(err, 5))
            return

        # 2) Marque ce salon comme “occupé”
        self.active_channels.add(ctx.channel.id)

        # 3) Recharge la liste des personnages
        self.load_characters()
        if not self.personnages:
            warning = await ctx.send("⚠️ Aucun personnage trouvé dans `personnages.json`. Vérifiez le chemin.")
            logger.warning("[GuessCharacter] Aucune donnée, commande annulée.")
            self.active_channels.discard(ctx.channel.id)
            asyncio.create_task(self.delete_message_after(warning, 5))
            return

        # 4) Enregistre l’heure de lancement du jeu (T0)
        t0 = ctx.message.created_at.replace(tzinfo=timezone.utc)

        # 5) Supprime la commande !guess après 2 secondes
        asyncio.create_task(self.delete_message_after(ctx.message, 2))

        # 6) Fonction interne pour choisir un nouveau personnage aléatoire
        def choose_new_character():
            perso = random.choice(self.personnages)
            p_prenom = perso.get("prenom", "").strip()
            p_nom = perso.get("nom", "").strip()
            p_anime = perso.get("anime", "Inconnu").strip()
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

        # Initialise le premier personnage
        char_data = choose_new_character()
        prenom = char_data["prenom"]
        nom = char_data["nom"]
        anime = char_data["anime"]
        image_url = char_data["image"]
        full_name = char_data["full_name"]
        noms_valides = char_data["valids"]

        logger.info(f"[GuessCharacter] {ctx.author} → personnage choisi : {full_name} ({anime})")

        # 7) Variables de suivi du jeu
        attempts = 0
        max_attempts = 10
        found = False
        hint_level = 0       # 0 = pas d’indice, 1 = 1er indice, 2 = 2ᵉ indice, 3 = 3ᵉ indice
        ended_by_skip = False

        # Pour appeler delete_message_after depuis les views
        cog = self

        # ───────────────────────────────────────────────────────────────────────────
        # 8) View pour les boutons « Skip ➡️ » et « Changer 🔄 »
        class SkipView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=None)
                self.main_embed_msg: discord.Message = None

            def build_hint_embed(self, level: int, remaining: int) -> discord.Embed:
                # Reconstruit l’embed d’indice en fonction du level et du nombre de tentatives restantes
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

                embed = discord.Embed(
                    title="💡 Indice",
                    description=desc,
                    color=0xf1c40f
                )
                embed.add_field(name="Tentatives restantes", value=str(remaining), inline=False)
                if image_url:
                    embed.set_image(url=image_url)
                return embed

            @discord.ui.button(label="Skip ➡️", style=discord.ButtonStyle.primary, custom_id="guess_skip_button")
            async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                nonlocal hint_level, attempts, ended_by_skip

                # Si la partie est déjà terminée (victoire/abandon/timeout), on ignore
                if found or ended_by_skip:
                    await interaction.response.defer()
                    return

                # Si on était déjà au 3ᵉ indice, on désactive le bouton
                if hint_level == 3:
                    button.disabled = True
                    await interaction.response.edit_message(view=self)
                    return

                # Si on était au 2ᵉ indice ET qu’on reclique sur Skip → 3ᵉ indice + EndGameView
                if hint_level == 2:
                    attempts = 9
                    hint_level = 3
                    new_embed = self.build_hint_embed(3, remaining=1)
                    await interaction.response.edit_message(embed=new_embed, view=view_end)
                    return

                # Sinon, on passe au palier suivant
                if hint_level == 0:
                    attempts = 4
                    hint_level = 1
                elif hint_level == 1:
                    attempts = 6
                    hint_level = 2
                else:
                    # Cas improbable : on désactive Skip
                    button.disabled = True
                    await interaction.response.edit_message(view=self)
                    return

                restantes = max_attempts - attempts
                emb = self.build_hint_embed(hint_level, restantes)
                if hint_level == 3:
                    button.disabled = True

                await interaction.response.edit_message(embed=emb, view=self)

            @discord.ui.button(label="Changer 🔄", style=discord.ButtonStyle.secondary, custom_id="guess_change_button")
            async def change_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                nonlocal prenom, nom, anime, image_url, full_name, noms_valides
                nonlocal attempts, hint_level, found

                # Si la partie est déjà terminée, on ignore
                if found or ended_by_skip:
                    await interaction.response.defer()
                    return

                # On remplace par un nouveau personnage aléatoire
                new_data = choose_new_character()
                prenom = new_data["prenom"]
                nom = new_data["nom"]
                anime = new_data["anime"]
                image_url = new_data["image"]
                full_name = new_data["full_name"]
                noms_valides = new_data["valids"]

                # Réinitialise l’état de la partie
                attempts = 0
                hint_level = 0
                found = False

                # Re-crée l’embed de départ
                start_embed = discord.Embed(
                    title="🎲 Guess the Anime Character",
                    description="Devinez ce personnage. Si vous êtes bloqué·e, cliquez sur **Skip ➡️** pour un indice, ou sur **Changer 🔄** pour un autre personnage.",
                    color=0x3498db
                )
                start_embed.add_field(name="Tentatives restantes", value=str(max_attempts), inline=False)
                if image_url:
                    start_embed.set_image(url=image_url)

                # Réactive les boutons et édite le message principal
                button.disabled = False
                view_skip.children[0].disabled = False  # le bouton Skip
                await interaction.response.edit_message(embed=start_embed, view=self)

        # ───────────────────────────────────────────────────────────────────────────
        # 9) View pour le bouton “Fin du jeu 🚫”
        class EndGameView(discord.ui.View):
            @discord.ui.button(label="Fin du jeu 🚫", style=discord.ButtonStyle.danger, custom_id="guess_end_button")
            async def end_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                nonlocal ended_by_skip

                if ended_by_skip:
                    await interaction.response.defer()
                    return

                ended_by_skip = True

                # Embed final d’abandon
                end_embed = discord.Embed(
                    title="🔚 Partie terminée (Abandon)",
                    description=(
                        f"⚠️ Vous avez cliqué sur **Fin du jeu** à la dernière tentative.\n"
                        f"La réponse était **{full_name}** de *{anime}*."
                    ),
                    color=0xe67e22
                )
                if image_url:
                    end_embed.set_thumbnail(url=image_url)
                end_embed.add_field(name="Tentatives utilisées", value=str(max_attempts), inline=True)

                # Envoie l’embed d’abandon
                await interaction.response.send_message(embed=end_embed)

                # Supprime très rapidement l’embed initial (celui avec SkipView)
                await asyncio.sleep(0.1)
                try:
                    await view_skip.main_embed_msg.delete()
                except:
                    pass

                # 🕒 On attend 7 secondes, puis purge tout le salon (sauf épinglés)
                async def delayed_clear():
                    await asyncio.sleep(7)
                    async for m in ctx.channel.history(limit=None):
                        if not m.pinned:
                            try:
                                await m.delete()
                            except:
                                pass

                asyncio.create_task(delayed_clear())

                # Supprime le message d’abandon au bout de 5 secondes
                final_msg = await interaction.original_response()
                asyncio.create_task(cog.delete_message_after(final_msg, 5))

                # Libère immédiatement le salon
                cog.active_channels.discard(ctx.channel.id)

        # Instancie les vues
        view_skip = SkipView()
        view_end = EndGameView()

        # ───────────────────────────────────────────────────────────────────────────
        # 10) Envoie l’embed initial (compteur + image + boutons Skip/Changer)
        start_embed = discord.Embed(
            title="🎲 Guess the Anime Character",
            description="Devinez ce personnage. Si vous êtes bloqué·e, cliquez sur **Skip ➡️** pour un indice, ou sur **Changer 🔄** pour un autre personnage.",
            color=0x3498db
        )
        start_embed.add_field(name="Tentatives restantes", value=str(max_attempts), inline=False)
        if image_url:
            start_embed.set_image(url=image_url)

        initial_msg = await ctx.send(embed=start_embed, view=view_skip)
        view_skip.main_embed_msg = initial_msg

        # ───────────────────────────────────────────────────────────────────────────
        # 11) On démarre la tâche « timeout » de 3 minutes
        async def game_timeout():
            await asyncio.sleep(180)  # 3 minutes
            nonlocal ended_by_skip, found

            # Si le jeu n’est pas terminé et le salon toujours actif
            if (not found) and (not ended_by_skip) and (ctx.channel.id in cog.active_channels):
                ended_by_skip = True

                # ** AJOUT DE LOG DANS LA CONSOLE **
                logger.info(f"[GuessCharacter] Temps écoulé pour le jeu dans le salon {ctx.channel.id}. Aucune action pendant 180 secondes.")

                # Embed final « Temps écoulé »
                timeout_embed = discord.Embed(
                    title="⏲️ Temps écoulé !",
                    description=(
                        f"Le temps de 3 minutes est écoulé.\n"
                        f"La réponse était **{full_name}** de *{anime}*."
                    ),
                    color=0xe67e22
                )
                if image_url:
                    timeout_embed.set_thumbnail(url=image_url)
                timeout_embed.add_field(name="Tentatives utilisées", value=str(attempts), inline=True)

                await ctx.send(embed=timeout_embed)

                # Supprime très rapidement l’embed initial (celui avec SkipView) s’il existe encore
                await asyncio.sleep(0.1)
                try:
                    await view_skip.main_embed_msg.delete()
                except:
                    pass

                # 🕒 On attend 7 secondes, puis on purge tout le salon (sauf épinglés)
                async def delayed_clear_timeout():
                    await asyncio.sleep(7)
                    async for m in ctx.channel.history(limit=None):
                        if not m.pinned:
                            try:
                                await m.delete()
                            except:
                                pass

                asyncio.create_task(delayed_clear_timeout())

                # Libère le salon
                cog.active_channels.discard(ctx.channel.id)

        timeout_task = asyncio.create_task(game_timeout())

        # ───────────────────────────────────────────────────────────────────────────
        # 12) Boucle principale pour recevoir les tentatives de l’utilisateur
        def check(m: discord.Message):
            return m.channel == ctx.channel and not m.author.bot

        while attempts < max_attempts:
            try:
                user_msg = await self.bot.wait_for("message", check=check)
                # Si le joueur retape « !guess » en cours de partie, on l’ignore (pas comptabilisé)
                if user_msg.content.strip().lower() == "!guess":
                    asyncio.create_task(cog.delete_message_after(user_msg, 0))
                    continue

                asyncio.create_task(cog.delete_message_after(user_msg, 0))

                # Si on a déjà abandonné via “Fin du jeu 🚫” ou timeout, on arrête tout
                if ended_by_skip:
                    return

                contenu = user_msg.content.lower().strip()

                # 12.a) Réponse correcte
                if contenu in noms_valides:
                    found = True
                    attempts += 1
                    rest = max_attempts - attempts

                    success_embed = discord.Embed(
                        title="✅ Bravo !",
                        description=f"{user_msg.author.mention}, c'était bien **{full_name}** de *{anime}* !",
                        color=0x2ecc71
                    )
                    success_embed.set_thumbnail(url=image_url or "")
                    success_embed.add_field(name="Tentatives utilisées", value=str(attempts), inline=True)
                    success_embed.add_field(name="Tentatives restantes", value=str(rest), inline=True)

                    final_msg = await ctx.send(embed=success_embed)
                    logger.info(f"[GuessCharacter] {user_msg.author} a trouvé {full_name} en {attempts} tentative(s).")

                    # Désactive le bouton Skip si présent
                    try:
                        view_skip.children[0].disabled = True
                        await view_skip.main_embed_msg.edit(view=view_skip)
                    except:
                        pass

                    # Supprime très rapidement l’embed initial (SkipView)
                    await asyncio.sleep(0.1)
                    try:
                        await view_skip.main_embed_msg.delete()
                    except:
                        pass

                    # 🕒 On attend 7 secondes, puis on purge tout le salon (sauf épinglés)
                    async def delayed_clear_victory():
                        await asyncio.sleep(7)
                        async for m in ctx.channel.history(limit=None):
                            if not m.pinned:
                                try:
                                    await m.delete()
                                except:
                                    pass

                    asyncio.create_task(delayed_clear_victory())
                    asyncio.create_task(cog.delete_message_after(final_msg, 5))

                    # On annule la tâche timeout pour éviter d’interférer
                    timeout_task.cancel()

                    cog.active_channels.discard(ctx.channel.id)
                    return

                # 12.b) Réponse incorrecte
                attempts += 1
                rest = max_attempts - attempts

                # Si un indice a déjà été dévoilé, on reconstruit l’embed via build_hint_embed
                if hint_level > 0:
                    emb = view_skip.build_hint_embed(hint_level, rest)
                    await view_skip.main_embed_msg.edit(embed=emb, view=view_skip)
                else:
                    basic_embed = discord.Embed(
                        title="🎲 Guess the Anime Character",
                        description="Devinez ce personnage. Si vous êtes bloqué·e, cliquez sur **Skip ➡️** pour un indice ou **Changer 🔄** pour un autre personnage.",
                        color=0x3498db
                    )
                    basic_embed.add_field(name="Tentatives restantes", value=str(rest), inline=False)
                    if image_url:
                        basic_embed.set_image(url=image_url)
                    await view_skip.main_embed_msg.edit(embed=basic_embed, view=view_skip)

                # Gestion automatique des indices
                if attempts in (4, 6, 9):
                    if attempts == max_attempts - 1:
                        # 9ᵉ tentative → indice n°3 puis passage à EndGameView
                        hint_embed = view_skip.build_hint_embed(3, rest)
                        await view_skip.main_embed_msg.edit(embed=hint_embed, view=view_end)
                        hint_level = 3
                    else:
                        # 4ᵉ ou 6ᵉ tentative → on dévoile 1ᵉᵒ ou 2ᵉ indice
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

        # ───────────────────────────────────────────────────────────────────────────
        # 13) Défaite “classique” si l’on est sorti de la boucle sans found ni abandon
        if not found and not ended_by_skip:
            end_embed = discord.Embed(
                title="🔚 Partie terminée",
                description=f"Aucune tentative restante.\nLa réponse était **{full_name}** de *{anime}*.",
                color=0xe67e22
            )
            end_embed.set_thumbnail(url=image_url or "")
            end_embed.add_field(name="Tentatives utilisées", value=str(max_attempts), inline=True)

            final_msg = await ctx.send(embed=end_embed)
            logger.info(f"[GuessCharacter] Échec du jeu pour {full_name} après 10 tentatives.")

            # Désactive Skip si présent
            try:
                view_skip.children[0].disabled = True
                await view_skip.main_embed_msg.edit(view=view_skip)
            except:
                pass

            # Supprime très rapidement l’embed initial (SkipView)
            await asyncio.sleep(0.1)
            try:
                await view_skip.main_embed_msg.delete()
            except:
                pass

            # 🕒 On attend 7 secondes, puis on purge tout le salon (sauf épinglés)
            async def delayed_clear_defeat():
                await asyncio.sleep(7)
                async for m in ctx.channel.history(limit=None):
                    if not m.pinned:
                        try:
                            await m.delete()
                        except:
                            pass

            asyncio.create_task(delayed_clear_defeat())
            asyncio.create_task(cog.delete_message_after(final_msg, 10))

            # On annule la tâche timeout (au cas où)
            timeout_task.cancel()

            cog.active_channels.discard(ctx.channel.id)


async def setup(bot):
    await bot.add_cog(GuessCharacter(bot))
    logger.info("[GuessCharacter] Cog ajouté au bot")
