"""
cogs/minigames.py — GamesCog
Slash commands para los minijuegos: RPS, Gato, Trivia y rankings.
"""

import logging
from typing import List

import discord
from discord import app_commands
from discord.ext import commands

import database

logger = logging.getLogger("lulu.minigames")


class GamesCog(commands.Cog):
    """Cog para los minijuegos interactivos de Lulu."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="rps", description="Juega piedra papel o tijera con Lulu o con un amigo")
    @app_commands.describe(oponente="Si quieres jugar contra un amigo, etiquétalo aquí")
    async def slash_rps(self, interaction: discord.Interaction, oponente: discord.Member = None) -> None:
        import games

        if oponente:
            if oponente.id == interaction.user.id:
                await interaction.response.send_message("no puedes jugar contra ti mismo 😒", ephemeral=True)
                return
            if oponente.bot:
                await interaction.response.send_message("los otros bots son re aburridos para jugar esto 🥱", ephemeral=True)
                return
            embed, view = games.get_rps_multiplayer_view(interaction.user, oponente)
        else:
            embed, view = games.get_rps_view()

        await interaction.response.send_message(embed=embed, view=view)
        view.message = await interaction.original_response()

    @app_commands.command(name="gato", description="Juega Tres en Raya (Tic Tac Toe) contra Lulu o un amigo")
    @app_commands.describe(oponente="Opcional: Etiqueta al amigo contra el que quieres jugar")
    async def slash_gato(self, interaction: discord.Interaction, oponente: discord.Member = None) -> None:
        import games

        if oponente is None:
            oponente = self.bot.user

        if oponente.id == interaction.user.id:
            await interaction.response.send_message("no puedes jugar contra ti mismo 😒", ephemeral=True)
            return
        if oponente.bot and oponente.id != self.bot.user.id:
            await interaction.response.send_message("solo yo sé jugar al gato, los demás bots no tienen cerebro 💅", ephemeral=True)
            return

        embed, view = games.get_tictactoe_view(interaction.user, oponente)
        await interaction.response.send_message(embed=embed, view=view)
        view.message = await interaction.original_response()

    @app_commands.command(name="trivia", description="Lulu te hace una pregunta de trivia")
    async def slash_trivia(self, interaction: discord.Interaction) -> None:
        import games

        await interaction.response.defer()
        embed, view = await games.get_trivia_question()

        message = await interaction.followup.send(embed=embed, view=view, wait=True)
        view.message = message

    @app_commands.command(name="ranking_juegos", description="Ver quién manda en los minijuegos")
    @app_commands.describe(juego="Elige qué ranking quieres ver")
    @app_commands.choices(
        juego=[
            app_commands.Choice(name="🧠 Trivia", value="trivia"),
            app_commands.Choice(name="🪨✂️📄 Piedra Papel Tijera", value="rps"),
            app_commands.Choice(name="❌⭕ Gato (Tres en raya)", value="gato"),
        ]
    )
    async def slash_ranking_juegos(self, interaction: discord.Interaction, juego: app_commands.Choice[str]) -> None:
        medals = ["🥇", "🥈", "🥉"]
        lines: List[str] = []

        if juego.value == "trivia":
            leaderboard = database.get_trivia_leaderboard(10)
            if not leaderboard:
                await interaction.response.send_message("Todavía nadie ha jugado trivia 🤷")
                return
            embed = discord.Embed(title="🧠 Top Genios de Trivia", color=discord.Color.blue())
            for index, entry in enumerate(leaderboard):
                medal = medals[index] if index < 3 else f"**{index + 1}.**"
                wins = entry["wins"]
                wins_str = f"{wins} victorias" if wins != 1 else "1 victoria"
                lines.append(f"{medal} @{entry['username']} — **{entry['points']} puntos** ({wins_str})")
            embed.set_footer(text="Cada 10 puntos = 1 victoria oficial 🏆")

        elif juego.value == "rps":
            leaderboard = database.get_rps_leaderboard(10)
            if not leaderboard:
                await interaction.response.send_message("Todavía nadie ha ganado al Piedra, Papel o Tijera 🤷")
                return
            embed = discord.Embed(title="🪨✂️📄 Maestros del RPS", color=discord.Color.purple())
            for index, entry in enumerate(leaderboard):
                medal = medals[index] if index < 3 else f"**{index + 1}.**"
                wins = entry["wins"]
                wins_str = f"{wins} victorias" if wins != 1 else "1 victoria"
                lines.append(f"{medal} @{entry['username']} — **{wins_str}**")

        else:
            leaderboard = database.get_tictactoe_leaderboard(10)
            if not leaderboard:
                await interaction.response.send_message("Todavía nadie ha ganado al Gato 🤷")
                return
            embed = discord.Embed(title="❌⭕ Dioses del Tres en Raya", color=discord.Color.red())
            for index, entry in enumerate(leaderboard):
                medal = medals[index] if index < 3 else f"**{index + 1}.**"
                wins = entry["wins"]
                wins_str = f"{wins} victorias" if wins != 1 else "1 victoria"
                lines.append(f"{medal} @{entry['username']} — **{wins_str}**")

        embed.description = "\n".join(lines)
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(GamesCog(bot))
