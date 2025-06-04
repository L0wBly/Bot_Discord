# cogs/guess_character.py

import discord
from discord.ext import commands
import json
import random
import os
import asyncio

from utils.logger import logger  # Importer le logger configuré dans utils/logger.py

class GuessCharacter(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        # Chemin vers le JSON (création_list_personnage/data/personnages.json)
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

        # Supprimer la commande utilisateur (!) après 2 secondes
        asyncio.create_task(self.delete_message_after(ctx.message, 2))

        # On conservera un seul message d'embed initial (avec l'image), puis un seul "indice" à la fois
        initial_embed: discord.Message = None
        feedback_messages = []   # Liste des messages "Tentative #n" ou retour
        hint_message: discord.Message = None
        final_message: discord.Message = None

        # Sélection aléatoire du personnage
        personnage = random.choice(self.personnages)
        prenom = personnage.get("prenom", "").strip()
        nom = personnage.get("nom", "").strip()
        anime = personnage.get("anime", "Inconnu").strip()
        image_url = personnage.get("image", None)
        full_name = f"{prenom} {nom}".strip()

        logger.info(f"[GuessCharacter] {ctx.author} a lancé !guess → personnage choisi : {full_name} ({anime})")

        # Ensemble des réponses acceptées (prénom, nom, ou "Prénom Nom")
        noms_valides = {prenom.lower(), nom.lower(), full_name.lower()}

        # --- 1) Embed initial (avec l'image du personnage) ---
        embed_start = discord.Embed(
            title="🎲 Guess the Anime Character",
            description="Vous avez 10 tentatives pour deviner ce personnage !",
            color=0x3498db
        )
        embed_start.add_field(name="Tentatives restantes", value="10", inline=False)
        if image_url:
            embed_start.set_image(url=image_url)
        initial_embed = await ctx.send(embed=embed_start)

        attempts = 0
        max_attempts = 10
        found = False

        def check(m: discord.Message):
            return m.channel == ctx.channel and not m.author.bot

        while attempts < max_attempts:
            try:
                msg = await self.bot.wait_for('message', check=check)
                feedback_messages.append(msg)

                answer = msg.content.lower().strip()
                attempts += 1
                restantes = max_attempts - attempts

                # --- 2) Si la réponse est correcte ---
                if answer in noms_valides:
                    success_embed = discord.Embed(
                        title="✅ Bravo !",
                        description=f"{msg.author.mention}, c'était bien **{full_name}** de *{anime}* !",
                        color=0x2ecc71
                    )
                    success_embed.set_thumbnail(url=image_url or "")
                    success_embed.add_field(name="Tentatives utilisées", value=str(attempts), inline=True)
                    success_embed.add_field(name="Tentatives restantes", value=str(restantes), inline=True)

                    final_message = await ctx.send(embed=success_embed)
                    feedback_messages.append(final_message)
                    logger.info(f"[GuessCharacter] {msg.author} a trouvé {full_name} en {attempts} tentative(s).")
                    found = True
                    break

                # --- 3) Si la réponse est incorrecte : on envoie un embed plus aéré ---
                feedback_embed = discord.Embed(
                    title=f"❌ Tentative #{attempts}",
                    color=0xe74c3c
                )
                feedback_embed.add_field(
                    name="Votre réponse",
                    value=f"`{msg.content}` est incorrecte.",
                    inline=False
                )
                feedback_embed.add_field(
                    name="Tentatives restantes",
                    value=str(restantes),
                    inline=False
                )
                if image_url:
                    feedback_embed.set_image(url=image_url)
                retour = await ctx.send(embed=feedback_embed)
                feedback_messages.append(retour)

                logger.info(f"[GuessCharacter] {msg.author} a tenté «{msg.content}», incorrect ({attempts}/10).")

                # --- 4) Déterminer si on affiche un indice complet (avec nom d'anime + fragment de prénom) ---
                hint_text = None

                if attempts == 4:
                    # Premier indice : anime + moitié du prénom
                    moitié = prenom[: len(prenom)//2 ] if prenom else ""
                    hint_text = f"**Anime :** {anime}\n\n"
                elif attempts == 6:
                    # Deuxième indice : anime + 3/4 du prénom
                    trois_quarts = prenom[: (len(prenom)*3)//4 ] if prenom else ""
                    hint_text = f"**Anime :** {anime}\n\n**La moitié du prénom est :** {moitié}…"
                elif attempts == 9:
                    # Troisième indice : anime + première lettre du prénom (= 1/ len)
                    première = prenom[0] if prenom else ""
                    hint_text = f"**Anime :** {anime}\n\n**Les 3/4 du prénom sont :** {trois_quarts}…"

                if hint_text:
                    # a) Supprimer l'embed initial s'il existe
                    # b) Supprimer tous les feedback_messages (tentatives précédentes)
                    # c) Supprimer l'ancien hint_message s'il existe
                    a_supprimer = []
                    if initial_embed:
                        a_supprimer.append(initial_embed)
                    a_supprimer.extend(feedback_messages)
                    if hint_message:
                        a_supprimer.append(hint_message)

                    for old in a_supprimer:
                        try:
                            await old.delete()
                        except discord.NotFound:
                            pass
                        except discord.Forbidden:
                            logger.warning(f"[GuessCharacter] Impossible de supprimer {old.id}")
                        except Exception as e:
                            logger.error(f"[GuessCharacter] Erreur lors de la suppression du message {old.id} : {e}")

                    # On nettoie les listes / références
                    initial_embed = None
                    feedback_messages.clear()
                    hint_message = None

                    # On renvoie le nouvel embed d'indice (avec image + texte complet)
                    indice_embed = discord.Embed(
                        title="💡 Indice",
                        description=hint_text,
                        color=0xf1c40f
                    )
                    if image_url:
                        indice_embed.set_image(url=image_url)
                    hint_message = await ctx.send(embed=indice_embed)

            except asyncio.CancelledError:
                break

        # --- 5) Si on n'a toujours pas trouvé après 10 tentatives ---
        if not found:
            end_embed = discord.Embed(
                title="🔚 Partie terminée",
                description=f"Aucune tentative restante.\nLa réponse était **{full_name}** de *{anime}*.",
                color=0xe67e22
            )
            end_embed.set_thumbnail(url=image_url or "")
            end_embed.add_field(name="Tentatives utilisées", value=str(max_attempts), inline=True)

            final_message = await ctx.send(embed=end_embed)
            feedback_messages.append(final_message)
            logger.info(f"[GuessCharacter] Échec du jeu pour {full_name} après 10 tentatives.")

        # --- 6) Suppression immédiate des messages intermédiaires ---
        to_delete = []
        if initial_embed:
            to_delete.append(initial_embed)
        if feedback_messages and not found:
            # Si défaite, on garde le dernier (final_message), on supprime le reste
            to_delete.extend(feedback_messages[:-1])
        else:
            to_delete.extend(feedback_messages)
        if hint_message:
            to_delete.append(hint_message)

        for m in to_delete:
            try:
                await m.delete()
            except discord.NotFound:
                pass
            except discord.Forbidden:
                logger.warning(f"[GuessCharacter] Impossible de supprimer le message {m.id}")
            except Exception as e:
                logger.error(f"[GuessCharacter] Erreur lors de la suppression du message {m.id} : {e}")

        # --- 7) Le message final (victoire ou défaite) reste 5 secondes ---
        if final_message:
            asyncio.create_task(self.delete_message_after(final_message, 5))

# Setup asynchrone pour discord.py v2.x
async def setup(bot):
    await bot.add_cog(GuessCharacter(bot))
    logger.info("[GuessCharacter] Cog ajouté au bot")
