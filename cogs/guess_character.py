# cogs/guess_character.py

import discord
from discord.ext import commands
import json
import random
import os
import asyncio
from datetime import timezone

from utils.logger import logger  # Votre logger perso, dans utils/logger.py

class GuessCharacter(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        # Chemin vers le JSON des personnages
        self.json_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),  # <racine>/BOT_DISCORD
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
        except discord.Forbidden:
            logger.warning(f"[GuessCharacter] Impossible de supprimer le message {message.id}")
        except discord.NotFound:
            pass
        except Exception as e:
            logger.error(f"[GuessCharacter] Erreur lors de la suppression du message {message.id} : {e}")

    @commands.command(name="guess", help="Lance un jeu pour deviner un personnage d'anime.")
    async def guess_character(self, ctx):
        # 1️⃣ Recharge la liste des personnages
        self.load_characters()
        if not self.personnages:
            await ctx.send("⚠️ Aucun personnage trouvé dans `personnages.json`. Vérifiez le chemin.")
            logger.warning("[GuessCharacter] Aucune donnée, commande annulée.")
            return

        # 2️⃣ Enregistre l’heure de lancement du jeu (T0)
        t0 = ctx.message.created_at.replace(tzinfo=timezone.utc)

        # 3️⃣ Supprime la commande !guess après 2 secondes
        asyncio.create_task(self.delete_message_after(ctx.message, 2))

        # 4️⃣ Choisit un personnage au hasard
        perso = random.choice(self.personnages)
        prenom = perso.get("prenom", "").strip()
        nom = perso.get("nom", "").strip()
        anime = perso.get("anime", "Inconnu").strip()
        image_url = perso.get("image", None)
        full_name = f"{prenom} {nom}".strip()

        logger.info(f"[GuessCharacter] {ctx.author} → personnage choisi : {full_name} ({anime})")
        noms_valides = {prenom.lower(), nom.lower(), full_name.lower()}

        # 5️⃣ Variables de suivi
        attempts = 0
        max_attempts = 10
        found = False
        hint_level = 0        # 0 = pas d’indice, 1 = 1er indice, 2 = 2ᵉ indice, 3 = 3ᵉ indice
        ended_by_skip = False # Se mettra à True si l’utilisateur clique “Fin du jeu 🚫”

        # --- Classe pour afficher l’indice & bouton "Skip ➡️" ---
        class SkipView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=None)
                self.main_embed_msg: discord.Message = None

            def build_hint_embed(self, level: int, remaining: int) -> discord.Embed:
                """
                Crée l'embed d'indice selon le niveau (1, 2 ou 3)
                et ajoute le compteur 'Tentatives restantes'.
                """
                if level == 1:
                    # 1er indice : anime + première lettre du prénom
                    première_lettre = prenom[0] if prenom else ""
                    desc = (
                        f"**Anime :** {anime}\n\n"
                        f"**Indice n°1 –** Le prénom commence par **{première_lettre}…**"
                    )
                elif level == 2:
                    # 2e indice : anime + moitié du prénom + 2 premières lettres du nom
                    moitié_prenom = prenom[: len(prenom)//2] if prenom else ""
                    deux_nom = nom[:2] if len(nom) >= 2 else nom
                    desc = (
                        f"**Anime :** {anime}\n\n"
                        f"**Indice n°2 –** La moitié du prénom est **{moitié_prenom}…**\n"
                        f"Les 2 premières lettres du nom de famille sont **{deux_nom}…**"
                    )
                else:
                    # 3e indice : anime + 3/4 du prénom + moitié du nom
                    trois_quarts = prenom[: (len(prenom)*3)//4] if prenom else ""
                    moitié_nom = nom[: len(nom)//2] if nom else ""
                    desc = (
                        f"**Anime :** {anime}\n\n"
                        f"**Indice n°3 –** Les 3/4 du prénom sont **{trois_quarts}…**\n"
                        f"Et la moitié du nom de famille est **{moitié_nom}…**"
                    )

                emb = discord.Embed(
                    title="💡 Indice",
                    description=desc,
                    color=0xf1c40f
                )
                emb.add_field(name="Tentatives restantes", value=str(remaining), inline=False)
                if image_url:
                    emb.set_image(url=image_url)
                return emb

            @discord.ui.button(label="Skip ➡️", style=discord.ButtonStyle.primary, custom_id="guess_skip_button")
            async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                nonlocal hint_level, attempts, ended_by_skip

                # Si la partie est déjà terminée (victoire ou abandon), on ignore
                if found or ended_by_skip:
                    await interaction.response.defer()
                    return

                # Si déjà au 3e indice, on bloque le bouton
                if hint_level == 3:
                    button.disabled = True
                    await interaction.response.edit_message(view=self)
                    return

                # Si on était au 2e indice ET qu’on reclique sur Skip → 3e indice + EndGameView
                if hint_level == 2:
                    attempts = 9
                    hint_level = 3
                    new_embed = self.build_hint_embed(3, 1)
                    # on bascule sur EndGameView (bouton “Fin du jeu 🚫”)
                    await interaction.response.edit_message(embed=new_embed, view=view_end)
                    return

                # Sinon, on passe au palier d’indice suivant
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

                # Si on venait d’atteindre 3e indice, on bloque Skip
                if hint_level == 3:
                    button.disabled = True

                await interaction.response.edit_message(embed=emb, view=self)

        # --- Classe pour afficher le bouton "Fin du jeu 🚫" ---
        class EndGameView(discord.ui.View):
            @discord.ui.button(label="Fin du jeu 🚫", style=discord.ButtonStyle.danger, custom_id="guess_end_button")
            async def end_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                nonlocal ended_by_skip

                # Si on a déjà cliqué sur “Fin du jeu”, on ignore
                if ended_by_skip:
                    await interaction.response.defer()
                    return

                # On marque l’abandon
                ended_by_skip = True

                # Crée l’embed de défaite “abandon”
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

                # Envoyer immédiatement ce nouvel embed
                await interaction.response.send_message(embed=end_embed)
                final_msg = await interaction.original_response()
                t1 = final_msg.created_at.replace(tzinfo=timezone.utc)

                # 4a) Supprime l’embed initial avec SkipView
                await asyncio.sleep(0.1)
                try:
                    await view_skip.main_embed_msg.delete()
                except:
                    pass

                # 4b) Supprime tous les messages entre t0 et t1
                async for m in ctx.channel.history(limit=None, after=t0, before=t1):
                    try:
                        await m.delete()
                    except:
                        pass

                # 4c) “Clear all” : supprimer TOUT message non épinglé
                async for m in ctx.channel.history(limit=None):
                    if not m.pinned:
                        try:
                            await m.delete()
                        except:
                            pass

                # 4d) Supprimer le message d’abandon après 5 secondes
                asyncio.create_task(self.delete_message_after(final_msg, 5))

        # Instancie les deux vues
        view_skip = SkipView()
        view_end = EndGameView()

        # --- 6️⃣) Envoie l’embed initial (compteur + image + Skip) ---
        start_embed = discord.Embed(
            title="🎲 Guess the Anime Character",
            description="Devinez ce personnage. Si vous êtes bloqué·e, cliquez sur **Skip ➡️** pour un indice.",
            color=0x3498db
        )
        start_embed.add_field(name="Tentatives restantes", value=str(max_attempts), inline=False)
        if image_url:
            start_embed.set_image(url=image_url)

        initial_msg = await ctx.send(embed=start_embed, view=view_skip)
        view_skip.main_embed_msg = initial_msg

        # --- 7️⃣) Boucle principale pour recevoir les tentatives utilisateur ---
        def check(m: discord.Message):
            return m.channel == ctx.channel and not m.author.bot

        while attempts < max_attempts:
            try:
                user_msg = await self.bot.wait_for("message", check=check)
                # Supprimer immédiatement la tentative de l’utilisateur
                asyncio.create_task(self.delete_message_after(user_msg, 0))

                # Si on a déjà abandonné via “Fin du jeu 🚫”, on arrête tout
                if ended_by_skip:
                    return

                contenu = user_msg.content.lower().strip()

                # 7.a) Réponse correcte
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
                    t1 = final_msg.created_at.replace(tzinfo=timezone.utc)
                    logger.info(f"[GuessCharacter] {user_msg.author} a trouvé {full_name} en {attempts} tentative(s).")

                    # Désactive le bouton Skip (s’il existe encore)
                    try:
                        view_skip.children[0].disabled = True
                        await view_skip.main_embed_msg.edit(view=view_skip)
                    except:
                        pass

                    # Supprime l’embed initial (SkipView) rapidement
                    await asyncio.sleep(0.1)
                    try:
                        await view_skip.main_embed_msg.delete()
                    except:
                        pass

                    # ► Supprime tous les messages entre t0 et t1
                    async for m in ctx.channel.history(limit=None, after=t0, before=t1):
                        try:
                            await m.delete()
                        except:
                            pass

                    # ► “Clear all” : supprimer tout message non épinglé
                    async for m in ctx.channel.history(limit=None):
                        if not m.pinned:
                            try:
                                await m.delete()
                            except:
                                pass

                    # ► Supprimer le message de victoire après 5 secondes
                    asyncio.create_task(self.delete_message_after(final_msg, 5))
                    return

                # 7.b) Réponse incorrecte
                attempts += 1
                rest = max_attempts - attempts

                # Préparer l’embed “compteur simple” (pas d’indice)
                basic_embed = discord.Embed(
                    title="🎲 Guess the Anime Character",
                    description="Devinez ce personnage. Si vous êtes bloqué·e, cliquez sur **Skip ➡️** pour un indice.",
                    color=0x3498db
                )
                basic_embed.add_field(name="Tentatives restantes", value=str(rest), inline=False)
                if image_url:
                    basic_embed.set_image(url=image_url)

                # Si on atteint la 4e, 6e ou 9e tentative, afficher automatiquement l’indice
                if attempts in (4, 6, 9):
                    # Cas 9e tentative → indice n°3 puis passage à EndGameView
                    if attempts == max_attempts - 1:
                        hint_embed = view_skip.build_hint_embed(3, rest)
                        await view_skip.main_embed_msg.edit(embed=hint_embed, view=view_end)
                        return

                    # Sinon (4ᵉ ou 6ᵉ), afficher 1er ou 2e indice
                    if attempts == 4:
                        hint_level = 1
                    else:  # attempts == 6
                        hint_level = 2

                    hint_embed = view_skip.build_hint_embed(hint_level, rest)
                    await view_skip.main_embed_msg.edit(embed=hint_embed, view=view_skip)
                else:
                    # Simple mise à jour du compteur
                    await view_skip.main_embed_msg.edit(embed=basic_embed, view=view_skip)

                logger.info(f"[GuessCharacter] {user_msg.author} a tenté «{user_msg.content}», incorrect ({attempts}/10).")

                if attempts >= max_attempts:
                    break

            except asyncio.CancelledError:
                break

        # --- 8️⃣) Défaite “classique” (10 tentatives épuisées sans cliquer “Fin du jeu”) ---
        if not found and not ended_by_skip:
            end_embed = discord.Embed(
                title="🔚 Partie terminée",
                description=f"Aucune tentative restante.\nLa réponse était **{full_name}** de *{anime}*.",
                color=0xe67e22
            )
            end_embed.set_thumbnail(url=image_url or "")
            end_embed.add_field(name="Tentatives utilisées", value=str(max_attempts), inline=True)

            final_msg = await ctx.send(embed=end_embed)
            t1 = final_msg.created_at.replace(tzinfo=timezone.utc)
            logger.info(f"[GuessCharacter] Échec du jeu pour {full_name} après 10 tentatives.")

            # Désactiver Skip s’il n’a pas déjà été désactivé
            try:
                view_skip.children[0].disabled = True
                await view_skip.main_embed_msg.edit(view=view_skip)
            except:
                pass

            # Supprimer l’embed initial (SkipView) rapidement
            await asyncio.sleep(0.1)
            try:
                await view_skip.main_embed_msg.delete()
            except:
                pass

            # ► Supprimer tous les messages entre t0 et t1
            async for m in ctx.channel.history(limit=None, after=t0, before=t1):
                try:
                    await m.delete()
                except:
                    pass

            # ► “Clear all” : supprimer tout message non épinglé dans le canal
            async for m in ctx.channel.history(limit=None):
                if not m.pinned:
                    try:
                        await m.delete()
                    except:
                        pass

            # ► Supprimer le message de défaite après 10 secondes
            asyncio.create_task(self.delete_message_after(final_msg, 10))


# ⚠️ Il ne doit y avoir qu’UNE SEULE fonction setup dans ce fichier ⚠️
async def setup(bot):
    await bot.add_cog(GuessCharacter(bot))
    logger.info("[GuessCharacter] Cog ajouté au bot")
