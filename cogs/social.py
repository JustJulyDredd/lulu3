"""
cogs/social.py — SocialCog
Comandos sociales: /remember, /cumple, /olvidar, /humor, /nivel,
bienvenidas a nuevos miembros y felicitaciones de cumpleaños.
"""

import logging
import math
from datetime import datetime
from typing import Set

import discord
from discord import app_commands
from discord.ext import commands, tasks

import config
import database
import llm
import personality

logger = logging.getLogger("lulu.social")

_birthdays_checked_today: Set[int] = set()


# --- Utilidades de nivel ---

LEVEL_TITLES = [
    (0, "Desconocido", "👤"),
    (1, "Conocido", "🌱"),
    (2, "Amigx", "🌟"),
    (4, "BFF", "💫"),
    (7, "Compa del Alma", "✨"),
    (12, "Hermano Cósmico", "🛸"),
    (18, "Leyenda", "👑"),
]


def get_level_info(interaction_count: int) -> dict:
    """Calcula el nivel, título y progreso de un usuario."""
    level = int(math.sqrt(interaction_count / 2))
    current_threshold = level * level * 2
    next_threshold = (level + 1) * (level + 1) * 2
    xp_in_level = interaction_count - current_threshold
    xp_needed = next_threshold - current_threshold
    progress = xp_in_level / xp_needed if xp_needed > 0 else 1.0

    title, emoji = "Desconocido", "👤"
    for min_level, t, e in reversed(LEVEL_TITLES):
        if level >= min_level:
            title, emoji = t, e
            break

    return {
        "level": level,
        "title": title,
        "emoji": emoji,
        "xp_in_level": xp_in_level,
        "xp_needed": xp_needed,
        "progress": progress,
        "total_interactions": interaction_count,
    }


def make_progress_bar(progress: float, length: int = 10) -> str:
    """Genera una barra de progreso visual con bloques."""
    filled = int(progress * length)
    empty = length - filled
    return "▰" * filled + "▱" * empty


# --- Vista de confirmación para /olvidar ---

class ForgetConfirmView(discord.ui.View):
    """Vista con botones de confirmación para borrar datos de usuario."""

    def __init__(self, user_id: int, *, timeout: float = 30.0):
        super().__init__(timeout=timeout)
        self.user_id = user_id

    @discord.ui.button(label="Sí, borrar todo", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("no es tu botón metiche 😒", ephemeral=True)
            return

        database.delete_user_data(self.user_id)

        for child in self.children:
            child.disabled = True  # type: ignore

        embed = discord.Embed(
            title="🗑️ Datos borrados",
            description="Listo, borré todo lo que sabía de ti. Es como si empezáramos de cero 🫧",
            color=discord.Color.dark_grey(),
        )
        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()

    @discord.ui.button(label="No, cancelar", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("no es tu botón metiche 😒", ephemeral=True)
            return

        for child in self.children:
            child.disabled = True  # type: ignore

        embed = discord.Embed(
            title="❌ Cancelado",
            description="ok, no borro nada 👍 tus recuerdos están a salvo",
            color=discord.Color.green(),
        )
        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True  # type: ignore


class SocialCog(commands.Cog):
    """Cog para funciones sociales, memoria y comandos de comunidad."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        self.check_birthdays.start()

    async def cog_unload(self):
        self.check_birthdays.cancel()

    # --- /remember ---

    @app_commands.command(name="remember", description="Ver qué recuerda Lulu de ti")
    async def slash_remember(self, interaction: discord.Interaction) -> None:
        profile = database.get_user_profile(interaction.user.id, interaction.user.name)
        embed = discord.Embed(
            title=f"🛸 Archivo de memoria: @{interaction.user.name}",
            description=profile["personality_summary"],
            color=discord.Color.purple(),
        )
        embed.add_field(name="Interacciones", value=str(profile["interaction_count"]), inline=True)
        embed.add_field(
            name="Última vez",
            value=datetime.fromtimestamp(profile["last_seen"]).strftime("%Y-%m-%d %H:%M"),
            inline=True,
        )
        embed.set_footer(text="Me acuerdo de lo que platicamos cada 3 mensajitos ✨")
        await interaction.response.send_message(embed=embed)

    # --- /cumple ---

    @app_commands.command(name="cumple", description="Registra tu cumpleaños para que Lulu te felicite")
    @app_commands.describe(dia="Día de tu cumpleaños (1-31)", mes="Mes de tu cumpleaños (1-12)")
    async def slash_cumple(self, interaction: discord.Interaction, dia: int, mes: int) -> None:
        if not (1 <= mes <= 12 and 1 <= dia <= 31):
            await interaction.response.send_message("eso no es una fecha real 😒", ephemeral=True)
            return

        meses = [
            "", "enero", "febrero", "marzo", "abril", "mayo", "junio",
            "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
        ]

        database.set_birthday(interaction.user.id, interaction.user.name, mes, dia)
        await interaction.response.send_message(
            f"Listo! Ya me apunté tu cumple: **{dia} de {meses[mes]}** 🎂✨ te voy a felicitar ese día!"
        )

    # --- /olvidar (NUEVO) ---

    @app_commands.command(name="olvidar", description="Pide a Lulu que borre todo lo que sabe de ti")
    async def slash_olvidar(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(
            title="⚠️ ¿Estás segurx?",
            description=(
                "Esto va a borrar **TODO** lo que sé de ti:\n"
                "• Mi memoria y recuerdos sobre ti\n"
                "• Tu cumpleaños registrado\n"
                "• Tus stats de juegos (trivia, RPS, gato)\n"
                "• Tu historial de conversaciones\n"
                "• Tus bumps registrados\n\n"
                "**No se puede deshacer.**"
            ),
            color=discord.Color.orange(),
        )
        view = ForgetConfirmView(interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    # --- /humor (NUEVO) ---

    @app_commands.command(name="humor", description="Pregúntale a Lulu cómo se siente ahorita")
    async def slash_humor(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()

        recent = database.get_recent_server_activity(limit=20)

        if not recent:
            await interaction.followup.send("no sé la verdad, nadie ha hablado conmigo últimamente 😴")
            return

        dialogue_lines = []
        for msg in recent:
            speaker = "Lulu" if msg["is_bot"] else f"@{msg['username']}"
            dialogue_lines.append(f"{speaker}: {msg['message_content'][:100]}")

        prompt = (
            "Basándote en estas conversaciones recientes del server, describe brevemente cómo te sientes ahorita como Lulu. "
            "¿Estás contenta? ¿Aburrida? ¿La gente ha sido buena onda o pesada? "
            "Responde en primera persona, máximo 3-4 líneas, con tu estilo adolescente de siempre. "
            "No listes las conversaciones, solo di cómo te sientes.\n\n"
            f"Conversaciones recientes:\n{chr(10).join(dialogue_lines)}"
        )

        try:
            mood = await llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=personality.LULU_LORE,
                temperature=0.9,
            )
        except Exception as error:
            logger.error("Error generating mood response: %s", error)
            mood = "la verdad ni yo sé cómo me siento ahorita jaja 🤷"

        embed = discord.Embed(
            title="💭 ¿Cómo se siente Lulu?",
            description=mood,
            color=discord.Color.magenta(),
        )
        embed.set_footer(text="esto es lo que siento ahorita ✨")
        await interaction.followup.send(embed=embed)

    # --- /nivel (NUEVO) ---

    @app_commands.command(name="nivel", description="Ver tu nivel de amistad con Lulu")
    async def slash_nivel(self, interaction: discord.Interaction) -> None:
        profile = database.get_user_profile(interaction.user.id, interaction.user.name)
        info = get_level_info(profile["interaction_count"])
        bar = make_progress_bar(info["progress"])

        embed = discord.Embed(
            title=f"{info['emoji']} Nivel {info['level']} — {info['title']}",
            color=discord.Color.teal(),
        )
        embed.set_author(name=f"@{interaction.user.name}", icon_url=interaction.user.display_avatar.url)
        embed.add_field(
            name="Progreso",
            value=f"{bar} ({info['xp_in_level']}/{info['xp_needed']})",
            inline=False,
        )
        embed.add_field(name="Interacciones totales", value=str(info["total_interactions"]), inline=True)
        embed.add_field(name="Siguiente nivel", value=f"Nivel {info['level'] + 1}", inline=True)
        embed.set_footer(text="Habla más conmigo para subir de nivel 💫")
        await interaction.response.send_message(embed=embed)

    # --- Bienvenidas ---

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """Da la bienvenida a nuevos miembros con un mensaje personalizado."""
        if not config.WELCOME_CHANNEL_ID:
            return

        channel = self.bot.get_channel(config.WELCOME_CHANNEL_ID)
        if not channel:
            try:
                channel = await self.bot.fetch_channel(config.WELCOME_CHANNEL_ID)
            except Exception:
                return

        prompt = (
            f"Alguien nuevo acaba de entrar al server. Se llama {member.display_name} "
            f"(username: @{member.name}). Dale la bienvenida de forma corta y natural, "
            f"como lo haría una adolescente que ya está en el server. "
            f"Máximo 2-3 líneas. No seas formal ni exagerada."
        )
        try:
            welcome_msg = await llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=personality.LULU_LORE,
                temperature=0.9,
            )
            if welcome_msg and not welcome_msg.startswith("*("):
                await channel.send(f"{member.mention} {welcome_msg}")
            else:
                await channel.send(f"Bienvenid@ {member.mention}! 👾✨")
        except Exception as error:
            logger.error("Error sending welcome message: %s", error)
            await channel.send(f"Bienvenid@ {member.mention}! 👾✨")

    # --- Cumpleaños (task loop) ---

    @tasks.loop(hours=1)
    async def check_birthdays(self) -> None:
        """Revisa cumpleaños y envía felicitaciones."""
        if not config.WELCOME_CHANNEL_ID:
            return

        now = datetime.now()

        if now.hour == 0:
            _birthdays_checked_today.clear()

        birthdays = database.get_todays_birthdays(now.month, now.day)
        channel = self.bot.get_channel(config.WELCOME_CHANNEL_ID)
        if not channel:
            return

        for birthday in birthdays:
            user_id = birthday["user_id"]
            if user_id in _birthdays_checked_today:
                continue

            _birthdays_checked_today.add(user_id)
            username = birthday["username"]
            prompt = (
                f"Hoy es el cumpleaños de {username}! Felicítalo de forma natural y divertida. "
                f"Máximo 2-3 líneas. Usa emojis de fiesta. No seas formal."
            )
            try:
                msg = await llm.generate_response(
                    messages=[{"role": "user", "content": prompt}],
                    system_prompt=personality.LULU_LORE,
                    temperature=0.9,
                )
                if msg and not msg.startswith("*("):
                    await channel.send(f"<@{user_id}> {msg}")
                else:
                    await channel.send(f"<@{user_id}> Feliz cumpleaños!! 🎂🎉🛸")
            except Exception as error:
                logger.error("Error sending birthday message: %s", error)
                await channel.send(f"<@{user_id}> Feliz cumpleaños!! 🎂🎉🛸")

            logger.info("Sent birthday message for @%s", username)

    @check_birthdays.before_loop
    async def before_check_birthdays(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(SocialCog(bot))
