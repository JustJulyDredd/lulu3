"""
cogs/minigames.py — GamesCog
Slash commands para los minijuegos: RPS, Gato, Trivia y rankings.
"""

import logging
from typing import List

import discord
from discord import app_commands
from discord.ext import commands

import bot.database as database

logger = logging.getLogger("lulu.minigames")


class GamesCog(commands.Cog):
    """Cog para los minijuegos interactivos de Lulu."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="rps", description="Juega piedra papel o tijera con Lulu o con un amigo")
    @app_commands.describe(oponente="Si quieres jugar contra un amigo, etiquétalo aquí")
    async def slash_rps(self, interaction: discord.Interaction, oponente: discord.Member = None) -> None:
        import bot.games as games

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
        import bot.games as games

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
        import bot.games as games

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

    @app_commands.command(name="---", description="idea de low")
    async def slash_bad_apple(self, interaction: discord.Interaction) -> None:
        from bot.cogs.bad_apple_data import FRAMES
        import asyncio

        # Check voice channel and connect
        voice_client = None
        if interaction.user.voice and interaction.user.voice.channel:
            vc_channel = interaction.user.voice.channel
            try:
                voice_client = await vc_channel.connect()
            except Exception:
                voice_client = discord.utils.get(self.bot.voice_clients, guild=interaction.guild)
                if voice_client and voice_client.channel != vc_channel:
                    try:
                        await voice_client.move_to(vc_channel)
                    except Exception:
                        pass
        
        if voice_client:
            try:
                if voice_client.is_playing():
                    voice_client.stop()
                voice_client.play(discord.FFmpegPCMAudio("bad_apple.mp4"))
            except Exception as e:
                logger.error(f"Error playing voice audio: {e}")

        # Send the first frame to respond to the interaction
        content = f"```\n{FRAMES[0]}\n```"
        await interaction.response.send_message(content)
        
        # Get the original response object to edit it
        message = await interaction.original_response()
        
        try:
            # Edit the message frame-by-frame with a delay
            for frame in FRAMES[1:]:
                try:
                    await message.edit(content=f"```\n{frame}\n```")
                    await asyncio.sleep(0.8)
                except discord.HTTPException:
                    break
        finally:
            # Disconnect from voice channel when done
            if voice_client and voice_client.is_connected():
                try:
                    await voice_client.disconnect()
                except Exception:
                    pass


async def setup(bot: commands.Bot):
    await bot.add_cog(GamesCog(bot))
