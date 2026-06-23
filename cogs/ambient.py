"""
cogs/ambient.py — AmbientCog
Comportamiento ambiental de Lulu: lurking, mensajes random y rotación de estado.
"""

import asyncio
import logging
import random
import time
from typing import Dict, List

import discord
from discord.ext import commands, tasks

import config
import database
import llm
import personality

logger = logging.getLogger("lulu.ambient")

LURK_CHANCE = 0.02
LURK_GLOBAL_COOLDOWN = 3600
LURK_CHANNEL_COOLDOWN = 5400
REACT_CHANCE = 0.08

LULU_REACTIONS = [
    "😂", "💀", "✨", "👀", "🔥", "💫", "👾",
    "🛸", "😭", "🫶", "💀", "🤣", "❤️", "🍕",
]

STATUS_MESSAGES = [
    discord.Game("pasando el rato 🛸"),
    discord.Game("videojuegos 🎮"),
    discord.Activity(type=discord.ActivityType.listening, name="synth music 🎹"),
    discord.Activity(type=discord.ActivityType.watching, name="series 📺"),
    discord.Game("comiendo doritos 🍕"),
    discord.Activity(type=discord.ActivityType.watching, name="memes 👾"),
    discord.Game("cálculo galáctico 😩"),
    discord.Activity(type=discord.ActivityType.listening, name="lo-fi beats 🌙"),
    discord.Game("escondite hiperespacial 💫"),
    discord.Activity(type=discord.ActivityType.watching, name="el chat 👀"),
]


class AmbientCog(commands.Cog):
    """Cog para el comportamiento ambiental de Lulu en el servidor."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._last_lurk_global: float = 0.0
        self._last_lurk_per_channel: Dict[int, float] = {}

    async def cog_load(self):
        self.rotate_status.start()
        self.random_message.start()

    async def cog_unload(self):
        self.rotate_status.cancel()
        self.random_message.cancel()

    @commands.Cog.listener()
    async def on_ready(self):
        await self.bot.change_presence(activity=discord.Game(name="pasando el rato 🛸"))

    # --- Lurking ---

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Maneja el lurking: reacciones y comentarios espontáneos."""
        if message.author == self.bot.user:
            return
        if message.author.bot:
            return
        if message.channel.id not in config.LURK_CHANNEL_IDS:
            return
        # No interferir con canales donde Lulu responde directamente
        if message.channel.id in config.ALLOWED_CHANNEL_IDS:
            return
        if len(message.content) < 15:
            return

        # Reacciones aleatorias
        now = time.time()
        if random.random() < REACT_CHANCE:
            try:
                emoji = random.choice(LULU_REACTIONS)
                await message.add_reaction(emoji)
            except Exception:
                pass

        # Comentario espontáneo (lurk)
        if random.random() > LURK_CHANCE:
            return
        if now - self._last_lurk_global < LURK_GLOBAL_COOLDOWN:
            return

        last_channel_lurk = self._last_lurk_per_channel.get(message.channel.id, 0)
        if now - last_channel_lurk < LURK_CHANNEL_COOLDOWN:
            return

        logger.info("[LURK] Jumping into conversation in channel %s", message.channel.id)

        history = database.get_chat_history(message.channel.id, limit=10)
        formatted = personality.format_history_for_llm(history)
        formatted.append({
            "role": "user",
            "content": f"@{message.author.name}: {message.content}",
        })

        lurk_prompt = personality.LULU_LORE + (
            "\n\nEstás leyendo el chat sin que nadie te haya llamado. "
            "Viste algo interesante y quieres comentar algo. "
            "Responde con UN comentario corto y natural (máximo 1-2 líneas). "
            "No saludes ni digas 'hola'. Solo comenta como si estuvieras ahí. "
            "Si no tienes nada bueno que decir, responde exactamente: SKIP"
        )
        try:
            response = await llm.generate_response(
                formatted,
                system_prompt=lurk_prompt,
                temperature=0.9,
            )
            if response and not response.startswith("*(") and "SKIP" not in response:
                await message.reply(response, mention_author=False)
                self._last_lurk_global = now
                self._last_lurk_per_channel[message.channel.id] = now

                database.add_chat_message(
                    message.channel.id,
                    message.author.id,
                    message.author.name,
                    message.content,
                    is_bot=False,
                )
                database.add_chat_message(
                    message.channel.id,
                    self.bot.user.id,
                    self.bot.user.name,
                    response,
                    is_bot=True,
                )
                logger.info("[LURK] Responded in channel %s", message.channel.id)
        except Exception as error:
            logger.error("[LURK] Error: %s", error)

    # --- Rotación de estado ---

    @tasks.loop(minutes=30)
    async def rotate_status(self) -> None:
        """Cambia el estado de Lulu cada 30 minutos."""
        status = random.choice(STATUS_MESSAGES)
        await self.bot.change_presence(activity=status)
        logger.info("Status rotated to: %s", status)

    @rotate_status.before_loop
    async def before_rotate_status(self) -> None:
        await self.bot.wait_until_ready()

    # --- Mensajes random ---

    @tasks.loop(hours=3)
    async def random_message(self) -> None:
        """Envía un mensaje casual en los canales de lurk para mantener presencia."""
        if not config.LURK_CHANNEL_IDS:
            return

        channel_id = random.choice(config.LURK_CHANNEL_IDS)
        channel = self.bot.get_channel(channel_id)
        if not channel:
            return

        prompts = [
            "Manda un mensaje random corto como si estuvieras aburrida en Discord. Máximo 1-2 líneas. Puede ser sobre videojuegos, comida, música, algo que viste, o una queja de tu tarea.",
            "Manda un pensamiento random de adolescente en Discord. Algo como 'alguien más tiene hambre o solo yo?' o 'acabo de descubrir una canción buenísima'. Máximo 1 línea.",
            "Haz un comentario casual como si estuvieras pasando el rato. Puede ser una pregunta al aire o un pensamiento. Máximo 1 línea, nada forzado.",
        ]
        try:
            msg = await llm.generate_response(
                messages=[{"role": "user", "content": random.choice(prompts)}],
                system_prompt=personality.LULU_LORE,
                temperature=0.95,
            )
            if msg and not msg.startswith("*("):
                await channel.send(msg)
                logger.info("[AMBIENT] Random message sent to channel %s", channel_id)
        except Exception as error:
            logger.error("Error sending random message: %s", error)

    @random_message.before_loop
    async def before_random_message(self) -> None:
        await self.bot.wait_until_ready()
        await asyncio.sleep(random.randint(600, 3600))


async def setup(bot: commands.Bot):
    await bot.add_cog(AmbientCog(bot))
