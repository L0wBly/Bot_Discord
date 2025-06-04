# cogs/guess_character.py

import discord
from discord.ext import commands
import json
import random
import os
import asyncio
from datetime import timezone

from utils.logger import logger  # Importer le logger configuré dans utils/logger.py

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
        # (Re)charger la liste des personnages
        self.load_characters()
        if not self.personnages:
            await ctx.send("⚠️ Aucun personnage trouvé dans `personnages.json`. Vérifiez le chemin.")
            logger.warning("[GuessCharacter] Aucune donnée, commande annulée.")
            return

        # Enregistrer l’heure de lancement du jeu
        t0 = ctx.message.created_at.replace(tzinfo=timezone.utc)

        # Supprimer la commande !guess au bout de 2 secondes
        asyncio.create_task(self.delete_message_after(ctx.message, 2))

        # Choisir un personnage au hasard
        perso = random.choice(self.personnages)
        prenom = perso.get("prenom", "").strip()
        nom = perso.get("nom", "").strip()
        anime = perso.get("anime", "Inconnu").strip()
        image_url = perso.get("image", None)
        full_name = f"{prenom} {nom}".strip()

        logger.info(f"[GuessCharacter] {ctx.author} → personnage choisi : {full_name} ({anime})")

        noms_valides = {prenom.lower(), nom.lower(), full_name.lower()}

        attempts = 0
        max_attempts = 10
        found = False
        hint_level = 0        # 0 = pas d’indice, 1 = 1er indice, 2 = 2e indice, 3 = 3e indice
        ended_by_skip = False # On ne mettra ce drapeau à True que si l’utilisateur clique réellement "Fin du jeu 🚫"

        # --- Classe pour afficher l’indice & bouton Skip ➡️ ---
        class SkipView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=None)
                # On stocke ici le message principal (contenant l’embed + les boutons)
                self.main_embed_msg: discord.Message = None

            def build_hint_embed(self, level: int, remaining: int) -> discord.Embed:
                """
                Crée l'embed d'indice selon le niveau (1, 2 ou 3)
                et le nombre de tentatives restantes.
                """
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
                else:  # level == 3
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

                # Si la partie est déjà terminée (victoire ou abandon par bouton), on ignore.
                if found or ended_by_skip:
                    await interaction.response.defer()
                    return

                # Si on était déjà au 3ᵉ indice (hint_level == 3), on désactive simplement le bouton
                if hint_level == 3:
                    button.disabled = True
                    await interaction.response.edit_message(view=self)
                    return

                # Si on clique sur Skip alors qu’on était déjà au 2ᵉ indice (hint_level == 2),
                # on saute directement au 3ᵉ indice ET on doit passer à EndGameView.
                if hint_level == 2:
                    attempts = 9
                    hint_level = 3
                    # **Ne PAS mettre `ended_by_skip = True` ici !**  
                    # On ne l’activera que lorsque l’utilisateur cliquera réellement sur "Fin du jeu 🚫".

                    # Construire l’embed d’indice n°3
                    new_embed = self.build_hint_embed(3, 1)
                    # Échanger la vue : passer au bouton "Fin du jeu 🚫"
                    await interaction.response.edit_message(embed=new_embed, view=view_end)
                    return

                # Sinon, on passe au palier d’indice suivant (4ᵉ -> indice 1, 6ᵉ -> indice 2)
                if hint_level == 0:
                    attempts = 4
                    hint_level = 1
                elif hint_level == 1:
                    attempts = 6
                    hint_level = 2
                else:
                    # Ce cas ne devrait pas se produire
                    button.disabled = True
                    await interaction.response.edit_message(view=self)
                    return

                restantes = max_attempts - attempts
                emb = self.build_hint_embed(hint_level, restantes)

                # Si jamais on devait arriver à hint_level == 3 ici (logique…), on désactiverait Skip.
                if hint_level == 3:
                    button.disabled = True

                await interaction.response.edit_message(embed=emb, view=self)

        # --- Classe pour afficher le bouton "Fin du jeu 🚫" à la 9ᵉ tentative (ou après Skip x2) ---
        class EndGameView(discord.ui.View):
            @discord.ui.button(label="Fin du jeu 🚫", style=discord.ButtonStyle.danger, custom_id="guess_end_button")
            async def end_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                nonlocal ended_by_skip

                # Si on a déjà cliqué une première fois sur "Fin du jeu", on ignore.
                if ended_by_skip:
                    await interaction.response.defer()
                    return

                # À présent, on valide vraiment l’abandon
                ended_by_skip = True

                # Construire l’embed final de défaite
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

                # ► Envoyer immédiatement l’embed final
                await interaction.response.send_message(embed=end_embed)

                # Récupérer l’objet Message tout de suite après
                final_msg = await interaction.original_response()
                t1 = final_msg.created_at.replace(tzinfo=timezone.utc)

                # ► Supprimer l’embed initial (celui qui portait SkipView)
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

                # ► Clear All : supprimer tous les messages non épinglés dans le canal
                async for m in ctx.channel.history(limit=None):
                    if not m.pinned:
                        try:
                            await m.delete()
                        except:
                            pass

                # ► Supprimer le message final (embed de défaite) après 5 secondes
                asyncio.create_task(self.delete_message_after(final_msg, 5))

        # Instancier les vues
        view_skip = SkipView()
        view_end = EndGameView()

        # --- 1) Envoyer l’embed initial (compteur + image + Skip ➡️) ---
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

        # --- 2) Boucle principale pour recevoir les tentatives de l’utilisateur ---
        def check(m: discord.Message):
            return m.channel == ctx.channel and not m.author.bot

        while attempts < max_attempts:
            try:
                user_msg = await self.bot.wait_for("message", check=check)
                # Supprimer immédiatement la tentative de l’utilisateur
                asyncio.create_task(self.delete_message_after(user_msg, 0))

                # Si la partie a déjà été terminée par abandon, on arrête tout
                if ended_by_skip:
                    return

                contenu = user_msg.content.lower().strip()

                # --- 2.a) Réponse correcte ---
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

                    # Désactiver le bouton Skip
                    view_skip.children[0].disabled = True
                    await view_skip.main_embed_msg.edit(view=view_skip)

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

                    # ► Clear All : supprimer tout message non épinglé dans le canal
                    async for m in ctx.channel.history(limit=None):
                        if not m.pinned:
                            try:
                                await m.delete()
                            except:
                                pass

                    # Supprimer le message de victoire après 5 secondes
                    asyncio.create_task(self.delete_message_after(final_msg, 5))
                    return

                # --- 2.b) Réponse incorrecte ---
                attempts += 1
                rest = max_attempts - attempts

                # Préparer l’embed mis à jour (simple compteur si pas d’indice)
                basic_embed = discord.Embed(
                    title="🎲 Guess the Anime Character",
                    description="Devinez ce personnage. Si vous êtes bloqué·e, cliquez sur **Skip ➡️** pour un indice.",
                    color=0x3498db
                )
                basic_embed.add_field(name="Tentatives restantes", value=str(rest), inline=False)
                if image_url:
                    basic_embed.set_image(url=image_url)

                # Si on atteint la 4ᵉ, 6ᵉ ou 9ᵉ tentative, on affiche l’indice
                if attempts in (4, 6, 9):
                    # Cas 9ᵉ tentative  
                    if attempts == max_attempts - 1:
                        # Construire l’embed d’indice n°3
                        hint_embed = view_skip.build_hint_embed(3, rest)
                        # Passer à la vue EndGameView                                 
                        await view_skip.main_embed_msg.edit(embed=hint_embed, view=view_end)
                        # On sort de la boucle, l’utilisateur doit cliquer sur “Fin du jeu 🚫”
                        return

                    # Cas 4ᵉ ou 6ᵉ tentative  
                    if attempts == 4:
                        hint_level = 1
                    else:
                        hint_level = 2

                    hint_embed = view_skip.build_hint_embed(hint_level, rest)
                    await view_skip.main_embed_msg.edit(embed=hint_embed, view=view_skip)
                else:
                    # Sinon, on met à jour seulement le compteur
                    await view_skip.main_embed_msg.edit(embed=basic_embed, view=view_skip)

                logger.info(f"[GuessCharacter] {user_msg.author} a tenté «{user_msg.content}», incorrect ({attempts}/10).")

                # Si on atteint 10 tentatives, on sort de la boucle (défaite classique)
                if attempts >= max_attempts:
                    break

            except asyncio.CancelledError:
                break

        # --- 3) Défaite “classique” (10 tentatives épuisées sans click “Fin du jeu”) ---
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

            # Désactiver Skip
            view_skip.children[0].disabled = True
            await view_skip.main_embed_msg.edit(view=view_skip)

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

            # ► Clear All : supprimer tout message non épinglé dans le canal
            async for m in ctx.channel.history(limit=None):
                if not m.pinned:
                    try:
                        await m.delete()
                    except:
                        pass

            # Supprimer le message de défaite après 5 secondes
            asyncio.create_task(self.delete_message_after(final_msg, 5))


# Fonction setup asynchrone compatible discord.py v2.x
async def setup(bot):
    await bot.add_cog(GuessCharacter(bot))
    logger.info("[GuessCharacter] Cog ajouté au bot")
