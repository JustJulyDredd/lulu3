"""
cogs/bump.py — BumpCog
Manejo de bumps de Disboard, recordatorios y comandos relacionados.
"""

import logging
import time
from datetime import datetime
from typing import Dict, List, Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

import config
import database
import llm
import personality

logger = logging.getLogger("lulu.bump")

DISBOARD_BOT_ID = 302050872383242240

BUMP_SUCCESS_PATTERNS = [
    "bump done", "bumped successfully", "bump successful",
    "has been bumped", "server bumped", "publicación actualizada",
    "bump realizado", "servidor bumpeado", "bump exitoso",
    "bump hecho", "bump feito", "publicação atualizada",
    "bump effectué", "bump réussi", "bump erfolgreich",
    "server gebumpt", "범프 완료", "バンプ完了",
    ":thumbsup:", "👍",
]


def _message_contains_bump_pattern(text: str) -> bool:
    lower_text = text.lower()
    return any(pattern in lower_text for pattern in BUMP_SUCCESS_PATTERNS)


def is_disboard_bump_message(message: discord.Message) -> bool:
    """Determina si un mensaje indica un bump exitoso de Disboard."""
    is_from_disboard = message.author.id == DISBOARD_BOT_ID
    is_bump_interaction = False

    interaction_meta = getattr(message, "interaction_metadata", None)
    if interaction_meta is not None:
        meta_name = getattr(interaction_meta, "name", "")
        if meta_name == "bump":
            is_bump_interaction = True
            logger.info("Bump detectado vía interaction_metadata.name == 'bump'")

    if is_from_disboard and is_bump_interaction:
        return True

    if is_from_disboard:
        logger.info(
            "[DISBOARD MSG] contenido='%s' | embeds=%s | interacción=%s | tipo=%s",
            message.content[:100],
            len(message.embeds),
            interaction_meta,
            message.type,
        )

        for index, embed in enumerate(message.embeds):
            logger.info(
                "[DISBOARD EMBED %s] title='%s' | desc='%s' | color=%s | image=%s | footer='%s'",
                index,
                embed.title,
                embed.description[:100] if embed.description else None,
                embed.color,
                embed.image.url if embed.image else None,
                embed.footer.text if embed.footer else None,
            )

        if _message_contains_bump_pattern(message.content):
            logger.info("Bump detectado por coincidencia en el contenido")
            return True

        for embed in message.embeds:
            searchable_parts: List[str] = []
            if embed.title:
                searchable_parts.append(embed.title)
            if embed.description:
                searchable_parts.append(embed.description)
            if embed.footer and embed.footer.text:
                searchable_parts.append(embed.footer.text)
            if embed.author and embed.author.name:
                searchable_parts.append(embed.author.name)
            for field in embed.fields:
                if field.name:
                    searchable_parts.append(field.name)
                if field.value:
                    searchable_parts.append(field.value)

            combined_text = " ".join(searchable_parts).lower()
            if _message_contains_bump_pattern(combined_text):
                logger.info("Bump detectado por coincidencia en el texto del embed")
                return True

        if any(embed.image and embed.image.url for embed in message.embeds):
            logger.info("Bump detectado por embed de Disboard con imagen")
            return True

        if any(embed.color and embed.color.value in (2405303, 2406327, 0x24b7b7) for embed in message.embeds):
            logger.info("Bump detectado por color de embed de Disboard")
            return True

        if message.embeds:
            logger.info("Bump detectado: mensaje de Disboard con embed (fallback)")
            return True

    if is_bump_interaction:
        logger.info("Bump detectado solo por interacción (el ID del autor pudo haber cambiado)")
        return True

    return False


BUMP_REMINDER_TEMPLATES = [
    "¡oigan! ya pasaron las 2 horas, alguien haga /bump por fa 🛸",
    "holaaa, toca hacer /bump al server, no se les olvide 👾",
    "¡hora del bump! 🚀 pongan /bump para subir el server por fis",
    "oigan, ya se puede hacer /bump otra vez, pónganlo please ✨",
    "alguien haga el /bump antes de que me quede dormida y ya no les avise jaja 😴",
    "bump timeee 🍕 pongan /bump para que venga más gente",
]

BUMP_ACK_TEMPLATES = [
    "¡súper! gracias por el bump, ya puse la alarma para dentro de 2 horas ⏰🛸",
    "gracias por el bump, ¡eres lo máximo! pongo el temporizador ✨",
    "¡buenaaa! ya quedó el bump. nos vemos en 2 horas para el siguiente 👾",
    "¡gracias! server bump-eado con éxito. alarma de 2 horas activada 🍕",
    "¡eso! bump realizado. ya guardé el tiempo para avisarles al rato 🚀",
]


async def get_bump_reminder_text() -> str:
    """Genera un recordatorio de bump prerenderizado en el estilo de Lulu."""
    import random
    return random.choice(BUMP_REMINDER_TEMPLATES)


async def get_bump_ack_text() -> str:
    """Genera un mensaje de agradecimiento prerenderizado cuando el bump fue exitoso."""
    import random
    return random.choice(BUMP_ACK_TEMPLATES)


class BumpCog(commands.Cog):
    """Cog para manejar bumps de Disboard y recordatorios."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        self.check_bump_reminders.start()

    async def cog_unload(self):
        self.check_bump_reminders.cancel()

    @commands.Cog.listener()
    async def on_ready(self):
        if config.BUMP_CHANNEL_ID:
            await self._scan_bump_channel_history()

        now = time.time()
        pending = database.get_pending_reminders(now)
        if pending:
            logger.info("Se encontraron %s recordatorio(s) de bump pendientes mientras estuve offline.", len(pending))
            for record in pending:
                channel_id = record["channel_id"]
                try:
                    channel = self.bot.get_channel(channel_id) or await self.bot.fetch_channel(channel_id)
                    if channel:
                        reminder_msg = await get_bump_reminder_text()
                        await channel.send(f"@here {reminder_msg}")
                    database.mark_reminder_sent(channel_id)
                    logger.info("Recordatorio de bump perdido enviado al canal %s", channel_id)
                except Exception as error:
                    logger.error("Error al enviar el recordatorio de bump perdido a %s: %s", channel_id, error)
                    database.mark_reminder_sent(channel_id)

    async def _scan_bump_channel_history(self) -> None:
        """Busca en el historial reciente del canal de bump el último bump válido."""
        logger.info("Escaneando el canal de bump %s en busca de bumps recientes...", config.BUMP_CHANNEL_ID)

        try:
            channel = self.bot.get_channel(config.BUMP_CHANNEL_ID)
            if not channel:
                channel = await self.bot.fetch_channel(config.BUMP_CHANNEL_ID)

            if not channel:
                logger.error("No se encontró el canal de bump %s", config.BUMP_CHANNEL_ID)
                return

            last_bump_time: Optional[float] = None
            async for msg in channel.history(limit=50):
                if is_disboard_bump_message(msg):
                    last_bump_time = msg.created_at.timestamp()
                    logger.info(
                        "Encontrado bump en el historial de %s por interacción/Disboard",
                        msg.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                    )
                    break

            if last_bump_time:
                now = time.time()
                bump_interval = config.BUMP_INTERVAL_MINUTES * 60
                next_bump = last_bump_time + bump_interval
                time_since_bump = now - last_bump_time

                if next_bump > now:
                    remaining = int(next_bump - now)
                    minutes, seconds = divmod(remaining, 60)
                    hours, minutes = divmod(minutes, 60)
                    logger.info(
                        "⏰ Temporizador de bump recuperado! El último bump fue hace %ss. Próximo recordatorio en %sh %sm %ss",
                        int(time_since_bump), hours, minutes, seconds,
                    )
                    database.set_bump_time(config.BUMP_CHANNEL_ID, next_bump)
                else:
                    logger.info(
                        "⏰ El último bump fue hace %ss — el temporizador ya expiró. Enviando recordatorio ahora.",
                        int(time_since_bump),
                    )
                    database.set_bump_time(config.BUMP_CHANNEL_ID, now - 1)
            else:
                logger.info("No se encontraron bumps recientes en el historial del canal.")
        except Exception as error:
            logger.error("Error al escanear el historial del canal de bump: %s", error)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author == self.bot.user:
            return

        # Log de mensajes de otros bots
        if message.author.bot:
            interaction_meta = getattr(message, "interaction_metadata", None)
            logger.info(
                "[BOT MSG] author='%s' (ID: %s) | content='%s' | embeds=%s | channel=%s | interaction=%s",
                message.author.name, message.author.id,
                message.content[:80], len(message.embeds),
                message.channel.id, interaction_meta,
            )

        # Solo procesar si es un bump de Disboard
        if not is_disboard_bump_message(message):
            return

        bump_channel_id = config.BUMP_CHANNEL_ID or message.channel.id
        next_bump = time.time() + (config.BUMP_INTERVAL_MINUTES * 60)
        database.set_bump_time(bump_channel_id, next_bump)
        logger.info(
            "✅ BUMP REGISTRADO: canal %s -> recordatorio en canal %s. Próximo bump a las %s",
            message.channel.id, bump_channel_id,
            datetime.fromtimestamp(next_bump).strftime("%H:%M:%S"),
        )

        interaction_meta = getattr(message, "interaction_metadata", None)
        if interaction_meta:
            bumper = getattr(interaction_meta, "user", None)
            if bumper:
                database.record_bump(bumper.id, bumper.name)
                logger.info("Bump registrado para @%s", bumper.name)

        ack_msg = await get_bump_ack_text()
        await message.channel.send(ack_msg)

    @tasks.loop(seconds=10.0)
    async def check_bump_reminders(self):
        """Verifica si hay recordatorios de bump pendientes."""
        now = time.time()
        pending = database.get_pending_reminders(now)

        for record in pending:
            channel_id = record["channel_id"]
            channel = self.bot.get_channel(channel_id)

            if not channel:
                try:
                    channel = await self.bot.fetch_channel(channel_id)
                except Exception as error:
                    logger.error("No se pudo obtener el canal %s: %s", channel_id, error)
                    database.mark_reminder_sent(channel_id)
                    continue

            try:
                reminder_msg = await get_bump_reminder_text()
                await channel.send(f"@here {reminder_msg}")
                database.mark_reminder_sent(channel_id)
                logger.info("Recordatorio de bump enviado al canal %s", channel_id)
            except Exception as error:
                logger.error("Error al enviar el recordatorio de bump a %s: %s", channel_id, error)
    @check_bump_reminders.before_loop
    async def before_check_bump_reminders(self):
        await self.bot.wait_until_ready()

    @app_commands.command(name="status", description="Ver cuánto falta para el próximo bump")
    async def slash_status(self, interaction: discord.Interaction) -> None:
        info = database.get_last_bump_info(interaction.channel.id)
        if not info and config.BUMP_CHANNEL_ID:
            info = database.get_last_bump_info(config.BUMP_CHANNEL_ID)

        if not info:
            await interaction.response.send_message("🛸 No tengo registros de bumps. Usen `/bump` para activarme 👾")
            return

        diff = info["next_bump_time"] - time.time()
        if diff <= 0:
            await interaction.response.send_message("⏰ ¡Ya es hora de hacer `/bump`!")
            return

        minutes, seconds = divmod(int(diff), 60)
        hours, minutes = divmod(minutes, 60)
        time_str = f"{hours}h {minutes}m {seconds}s" if hours else f"{minutes}m {seconds}s"
        await interaction.response.send_message(f"⏰ Faltan **{time_str}** para el próximo bump.")

    @app_commands.command(name="ranking", description="Ver el ranking de bumps del server")
    async def slash_ranking(self, interaction: discord.Interaction) -> None:
        leaderboard = database.get_bump_leaderboard(10)

        if not leaderboard:
            await interaction.response.send_message("Todavía no hay bumps registrados 🤷")
            return

        embed = discord.Embed(title="🏆 Ranking de Bumps", color=discord.Color.gold())
        medals = ["🥇", "🥈", "🥉"]
        lines: List[str] = []

        for index, entry in enumerate(leaderboard):
            medal = medals[index] if index < 3 else f"**{index + 1}.**"
            lines.append(f"{medal} @{entry['username']} — **{entry['bump_count']}** bumps")

        embed.description = "\n".join(lines)
        embed.set_footer(text="¡Sigan bumpeando! 🛸")
        await interaction.response.send_message(embed=embed)

    @commands.command(name="mockbump")
    async def mock_bump_command(self, ctx: commands.Context, seconds: int = None) -> None:
        """Simula un bump exitoso para pruebas."""
        if seconds is None:
            next_bump = time.time() + (config.BUMP_INTERVAL_MINUTES * 60)
            time_msg = f"{config.BUMP_INTERVAL_MINUTES} minutos"
        else:
            next_bump = time.time() + seconds
            time_msg = f"{seconds} segundos"

        bump_channel_id = config.BUMP_CHANNEL_ID or ctx.channel.id
        database.set_bump_time(bump_channel_id, next_bump)
        logger.info("Bump simulado programado para %s", time_msg)

        ack_msg = await get_bump_ack_text()
        if seconds is not None:
            ack_msg += f" (Modo simulación: sonará en {seconds} segundos)"
        await ctx.send(ack_msg)


async def setup(bot: commands.Bot):
    await bot.add_cog(BumpCog(bot))
