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

# Estados contextuales basados en eventos
CONTEXTUAL_STATUSES = {
    "active": [
        discord.Activity(type=discord.ActivityType.watching, name="la conversación 👀"),
        discord.Game("respondiendo mensajes 💬"),
        discord.Activity(type=discord.ActivityType.listening, name="historias 🎧"),
    ],
    "chill": [
        discord.Game("relajándose 💫"),
        discord.Activity(type=discord.ActivityType.watching, name="las nubes 🌙"),
        discord.Game("pensando en doritos 🍕"),
    ],
    "gaming": [
        discord.Game("videojuegos 🎮"),
        discord.Game("speedrunning 💨"),
        discord.Game("perdiendo 😭"),
    ],
    "music": [
        discord.Activity(type=discord.ActivityType.listening, name="synth 🎹"),
        discord.Activity(type=discord.ActivityType.listening, name="algo épico 🔥"),
    ],
    "drama": [
        discord.Activity(type=discord.ActivityType.watching, name="el drama 👀"),
        discord.Game("escaneando el chat 🛸"),
    ],
}


class AmbientCog(commands.Cog):
    """Cog para el comportamiento ambiental de Lulu en el servidor."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._last_lurk_global: float = 0.0
        self._last_lurk_per_channel: Dict[int, float] = {}
        self._last_presence_comment: Dict[int, float] = {}  # Para evitar spam de comentarios
        self._last_status_change: float = 0.0
        self._current_context: str = "chill"  # contexto actual del status

    async def cog_load(self):
        self.rotate_status.start()
        self.random_message.start()
        self.update_context.start()

    async def cog_unload(self):
        self.rotate_status.cancel()
        self.random_message.cancel()
        self.update_context.cancel()

    @commands.Cog.listener()
    async def on_ready(self):
        await self.bot.change_presence(activity=discord.Game(name="pasando el rato 🛸"))

    async def set_contextual_status(self, context: str = None) -> None:
        """Cambia el status basado en el contexto actual."""
        if context:
            self._current_context = context
        
        statuses = CONTEXTUAL_STATUSES.get(self._current_context, STATUS_MESSAGES)
        status = random.choice(statuses)
        await self.bot.change_presence(activity=status)
        self._last_status_change = time.time()
        logger.info(f"[PRESENCE] El estado cambió al contexto '{self._current_context}': {status.name}")

    # --- Detección de presencia de otros usuarios ---

    @commands.Cog.listener()
    async def on_presence_update(self, before: discord.Member, after: discord.Member) -> None:
        """Detecta cambios en la actividad de otros usuarios y reacciona."""
        if after == self.bot.user:
            return
        if after.bot:
            return

        before_activity = before.activity
        after_activity = after.activity

        # Si cambió su actividad o es nueva
        if before_activity != after_activity and after_activity is not None:
            activity_name = after_activity.name or "algo"
            activity_type = after_activity.type

            # Evitar spam: solo comentar cada 5 minutos por usuario
            now = time.time()
            user_id = after.id
            if user_id in self._last_presence_comment:
                if now - self._last_presence_comment[user_id] < 300:
                    return
            
            self._last_presence_comment[user_id] = now

            # Buscar un canal para comentar
            channel = None
            if config.LURK_CHANNEL_IDS:
                channel = self.bot.get_channel(random.choice(config.LURK_CHANNEL_IDS))
            
            if not channel and config.ALLOWED_CHANNEL_IDS:
                channel = self.bot.get_channel(config.ALLOWED_CHANNEL_IDS[0])
            
            if not channel:
                return

            # Generar reacción según el tipo de actividad
            reaction_prompt = self._get_presence_reaction_prompt(
                after.name, activity_type, activity_name
            )

            try:
                response = await llm.generate_response(
                    messages=[{"role": "user", "content": reaction_prompt}],
                    system_prompt=personality.LULU_LORE,
                    temperature=0.85,
                )
                
                if response and not response.startswith("*(") and response not in llm.TIRED_RESPONSES:
                    await channel.send(response)
                    logger.info(f"[PRESENCE] Reaccionó a la actividad de {after.name}: {activity_name}")
            except Exception as e:
                logger.error(f"[PRESENCE] Error al reaccionar a la actividad: {e}")

    def _get_presence_reaction_prompt(self, username: str, activity_type, activity_name: str) -> str:
        """Genera un prompt para reaccionar a la actividad de alguien."""
        prompts_by_type = {
            discord.ActivityType.playing: f"@{username} está jugando '{activity_name}'. Haz un comentario corto sobre eso (máximo 1 línea), como si acabaras de verlo en el chat. Puede ser una pregunta, una broma, o un comentario genuino. Nada forzado.",
            discord.ActivityType.streaming: f"@{username} está haciendo stream de '{activity_name}'. Comenta algo corto como si lo vieras (1 línea máximo).",
            discord.ActivityType.listening: f"@{username} está escuchando '{activity_name}'. Reacciona con un comentario corto sobre la música/podcast (1 línea).",
            discord.ActivityType.watching: f"@{username} está viendo '{activity_name}'. Comenta algo sobre eso de forma natural (1 línea máximo).",
        }
        
        prompt = prompts_by_type.get(
            activity_type,
            f"Alguien ({username}) está haciendo algo: {activity_name}. Haz un comentario corto y natural (1 línea)."
        )
        
        return prompt

    @tasks.loop(minutes=5)
    async def update_context(self) -> None:
        """Actualiza el contexto del status cada 5 minutos basado en actividad."""
        try:
            # Contar mensajes recientes
            total_activity = 0
            for channel_id in config.ALLOWED_CHANNEL_IDS:
                channel = self.bot.get_channel(channel_id)
                if channel:
                    try:
                        # Obtener últimos mensajes
                        async for msg in channel.history(limit=20):
                            if time.time() - msg.created_at.timestamp() < 600:  # últimos 10 min
                                total_activity += 1
                    except Exception:
                        pass
            
            # Seleccionar contexto basado en actividad
            if total_activity > 15:
                await self.set_contextual_status("active")
            elif total_activity > 5:
                # Revisar si hay palabras clave de gaming, música, etc.
                context = await self._detect_channel_topic()
                await self.set_contextual_status(context)
            else:
                await self.set_contextual_status("chill")
                
        except Exception as e:
            logger.error(f"[PRESENCE] Error al actualizar el contexto: {e}")

    async def _detect_channel_topic(self) -> str:
        """Detecta de qué hablan en los canales para cambiar el contexto."""
        keywords = {
            "gaming": ["juego", "jugando", "rank", "level", "boss", "gamer", "server", "match"],
            "music": ["canción", "música", "artista", "rola", "playlist", "spotify", "genero"],
            "drama": ["problema", "drama", "odio", "pelea", "arg", "banneado", "tóxico", "mod"],
        }
        
        try:
            recent_msgs = database.get_chat_history(config.ALLOWED_CHANNEL_IDS[0], limit=30) if config.ALLOWED_CHANNEL_IDS else []
            combined_text = " ".join([msg.get("message_content", "").lower() for msg in recent_msgs])
            
            for context, words in keywords.items():
                if any(word in combined_text for word in words):
                    return context
        except Exception:
            pass
        
        return "chill"

    @update_context.before_loop
    async def before_update_context(self) -> None:
        await self.bot.wait_until_ready()

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
        
        content = message.content.strip()
        has_attachments = len(message.attachments) > 0
        has_link = "http://" in content or "https://" in content or "youtube.com" in content or "spotify.com" in content

        # Si el mensaje está muy vacío (sin contenido ni attachments), ignorar
        if len(content) < 5 and not has_attachments and not has_link:
            return

        # Reacciones genuinas usando la IA para cada mensaje
        content_for_emoji = content or ("(imagen/archivo)" if has_attachments else "")
        if content_for_emoji:
            try:
                emoji = await llm.generate_emoji_reaction(content_for_emoji)
                if emoji:
                    await message.add_reaction(emoji)
                    logger.info(f"[LURK] Reaccionó genuinamente a '{content_for_emoji[:20]}' con {emoji}")
            except Exception as e:
                logger.error(f"[LURK] Error al agregar la reacción genuina: {e}")

        # Comentario espontáneo (lurk)
        # Mayor probabilidad si hay algo interesante (imágenes, links, etc)
        lurk_probability = LURK_CHANCE
        if has_attachments or has_link or len(content) > 50:
            lurk_probability = LURK_CHANCE * 3  # Mayor chance de comentar
        
        if random.random() > lurk_probability:
            return
        if now - self._last_lurk_global < LURK_GLOBAL_COOLDOWN:
            return

        last_channel_lurk = self._last_lurk_per_channel.get(message.channel.id, 0)
        if now - last_channel_lurk < LURK_CHANNEL_COOLDOWN:
            return

        logger.info("[LURK] Interviniendo en la conversación en el canal %s", message.channel.id)

        history = database.get_chat_history(message.channel.id, limit=10)
        formatted = personality.format_history_for_llm(history)
        formatted.append({
            "role": "user",
            "content": f"@{message.author.name}: {message.content}",
        })

        # Adaptar el prompt según el tipo de contenido
        lurk_prompt = personality.LULU_LORE + "\n\n"
        if has_attachments:
            lurk_prompt += "Alguien acaba de compartir una imagen/video. Reacciona con un comentario natural sobre eso. "
        elif has_link:
            lurk_prompt += "Alguien compartió un link (video, música, artículo). Comenta sobre eso. "
        else:
            lurk_prompt += "Estás leyendo el chat sin que nadie te haya llamado y viste algo interesante. "
        
        lurk_prompt += (
            "Responde con UN comentario corto y natural (máximo 1-2 líneas). "
            "No saludes ni digas 'hola'. Solo comenta como si estuvieras ahí. "
            "Sé genuina, curiosa o bromista. "
            "Si no tienes nada bueno que decir, responde exactamente: SKIP"
        )
        try:
            response = await llm.generate_response(
                formatted,
                system_prompt=lurk_prompt,
                temperature=0.9,
            )
            if response and not response.startswith("*(") and "SKIP" not in response and response not in llm.TIRED_RESPONSES:
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
                logger.info("[LURK] Respondió en el canal %s", message.channel.id)
        except Exception as error:
            logger.error("[LURK] Error: %s", error)

    # --- Rotación de estado ---

    @tasks.loop(minutes=30)
    async def rotate_status(self) -> None:
        """Cambia el estado de Lulu cada 30 minutos (o mantiene el contextual)."""
        # Si hace poco se cambió por contexto, no cambiar
        if time.time() - self._last_status_change < 300:
            return
        
        # Alternar entre status contextual y aleatorio
        if random.random() > 0.5:
            status = random.choice(STATUS_MESSAGES)
            await self.bot.change_presence(activity=status)
        else:
            await self.set_contextual_status()
        
        logger.info("Estado rotado")

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
            if msg and not msg.startswith("*(") and msg not in llm.TIRED_RESPONSES:
                await channel.send(msg)
                logger.info("[AMBIENT] Mensaje aleatorio enviado al canal %s", channel_id)
        except Exception as error:
            logger.error("Error al enviar mensaje aleatorio: %s", error)

    @random_message.before_loop
    async def before_random_message(self) -> None:
        await self.bot.wait_until_ready()
        await asyncio.sleep(random.randint(600, 3600))


async def setup(bot: commands.Bot):
    await bot.add_cog(AmbientCog(bot))
