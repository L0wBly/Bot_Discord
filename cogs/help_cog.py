import discord
from discord.ext import commands, tasks
import asyncio

from config import ADMIN_ROLE_ID, COMMAND_CHANNEL_ID

class HelpCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.auto_clear_command_channel.start()

    def cog_unload(self):
        self.auto_clear_command_channel.cancel()

    @tasks.loop(hours=1)
    async def auto_clear_command_channel(self):
        channel = self.bot.get_channel(COMMAND_CHANNEL_ID)
        if not channel:
            return

        try:
            await channel.purge(limit=1000, check=lambda m: not m.pinned)
        except discord.Forbidden:
            print("Permissions insuffisantes pour nettoyer le salon de commandes.")
            return

        embed = discord.Embed(
            title="📌 Commandes disponibles dans ce salon",
            description="Voici les commandes que tu peux utiliser ici :",
            color=discord.Color.teal()
        )

        embed.add_field(name="❓ `!help`", value="→ Affiche les commandes générales", inline=False)
        embed.add_field(name="🎮 `!helpjeu`", value="→ Affiche les commandes du jeu", inline=False)
        embed.add_field(name="🎂 `!anniv JJ-MM`", value="→ Enregistre ta date d'anniversaire", inline=False)
        embed.add_field(name="📅 `!anniv`", value="→ Affiche ta date actuelle", inline=False)
        embed.add_field(name="🗑️ `!delanniv`", value="→ Supprime ton anniversaire", inline=False)
        embed.add_field(name="🔮 `!annivs`", value="→ Liste les 20 anniversaires à venir", inline=False)
        embed.add_field(name="📊 `!classement`", value="→ Classement du serveur", inline=False)
        embed.add_field(name="🎮 `!guess`", value="→ Devine un personnage d’anime", inline=False)
        embed.add_field(name="🧹 `!clear`", value="→ Supprime tes propres messages", inline=False)

        embed.set_footer(text="Utilise l'une des commandes ci-dessus directement ici 🎉")

        await channel.send(embed=embed)

    @auto_clear_command_channel.before_loop
    async def before_clear(self):
        await self.bot.wait_until_ready()

    @commands.command(name="help")
    async def help_cmd(self, ctx):
        """Affiche les commandes générales du bot (hors jeu)."""
        embed = discord.Embed(
            title="📖 Commandes générales",
            description="Voici la liste des commandes organisées par module (sauf jeu) :",
            color=discord.Color.blurple()
        )

        has_admin_role = any(role.id == ADMIN_ROLE_ID for role in ctx.author.roles)

        for cog_name, cog in self.bot.cogs.items():
            if cog_name.lower() == "jeu":
                continue
            if cog_name.lower() in ["rolestats", "reactionroles"] and not has_admin_role:
                continue

            command_list = []
            for command in cog.get_commands():
                if command.hidden:
                    continue
                name = command.name
                description = command.help or "Aucune description."
                command_list.append(f"**`{name}`** : {description}")
            if command_list:
                embed.add_field(
                    name=f"📂 {cog_name}",
                    value="\n".join(command_list),
                    inline=False
                )

        message = await ctx.send(embed=embed)

        if has_admin_role:
            await asyncio.sleep(180)
            try:
                await ctx.message.delete()
            except discord.Forbidden:
                pass
            try:
                await message.delete()
            except discord.Forbidden:
                pass

    @commands.command(name="helpjeu")
    async def helpjeu_cmd(self, ctx):
        """Affiche les commandes du jeu uniquement."""
        embed = discord.Embed(
            title="🎮 Commandes du jeu",
            description="Voici les commandes disponibles pour les modules de jeu :",
            color=discord.Color.orange()
        )

        jeux_commands_found = False
        for cog_name, cog in self.bot.cogs.items():
            if cog_name.lower() != "jeu":
                continue

            command_list = []
            for command in cog.get_commands():
                if command.hidden:
                    continue
                name = command.name
                description = command.help or "Aucune description."
                command_list.append(f"**`{name}`** : {description}")
            if command_list:
                jeux_commands_found = True
                embed.add_field(
                    name=f"🎮 {cog_name}",
                    value="\n".join(command_list),
                    inline=False
                )

        if not jeux_commands_found:
            embed.description = "Aucune commande de jeu trouvée. Assurez-vous que les cogs de jeu ont `name=\"Jeu\"`."

        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(HelpCog(bot))
