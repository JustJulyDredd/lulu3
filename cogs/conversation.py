"""
cogs/conversation.py — ConversationCog
Lógica principal de conversación: respuestas, agrupado de mensajes,
detección de spam, procesamiento de imágenes, búsqueda web y consolidación de memoria.
"""

import asyncio
import base64
import logging
import re
import time
from typing import Dict, List, Optional, Tuple

import httpx
import discord
from discord.ext import commands

import config
import database
import llm
import personality
import search

logger = logging.getLogger("lulu.conversation")

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}

# Regex para capturar emoji Unicode comunes
EMOJI_REGEX = re.compile(
    "[\U0001F300-\U0001F5FF\U0001F600-\U0001F64F\U0001F680-\U0001F6FF\u2600-\u26FF\u2700-\u27BF]+",
    flags=re.UNICODE,
)

# Regex para capturar emojis de servidor (custom emojis)
DISCORD_EMOJI_REGEX = re.compile(r"<a?:\w+:\d+>", re.UNICODE)

# Triggers de búsqueda web
SEARCH_TRIGGERS = [
    "busca ", "búsca ", "investiga ", "qué es ", "que es ",
    "quién es ", "quien es ", "dime sobre ", "qué significa ",
    "que significa ", "search ", "googlea ", "averigua ",
    "que paso con ", "qué pasó con ", "noticias de ", "noticias sobre ",
]


# --- Funciones auxiliares ---

def split_message(text: str, limit: int = 1900) -> List[str]:
    """Divide un texto en fragmentos que caben en Discord."""
    if len(text) <= limit:
        return [text]

    chunks: List[str] = []
    while len(text) > limit:
        split_at = text.rfind("\n", 0, limit)
        if split_at == -1 or split_at < limit // 2:
            split_at = text.rfind(" ", 0, limit)
        if split_at == -1 or split_at < limit // 2:
            split_at = limit

        chunks.append(text[:split_at])
        text = text[split_at:].lstrip()

    if text:
        chunks.append(text)

    return chunks


async def download_image(url: str) -> Optional[dict[str, str]]:
    """Descarga una imagen y devuelve su contenido en base64."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url)
            if response.status_code == 200:
                content_type = response.headers.get("content-type", "image/png")
                if "image" not in content_type:
                    content_type = "image/png"
                b64 = base64.b64encode(response.content).decode("utf-8")
                return {"base64": b64, "media_type": content_type}
    except Exception as error:
        logger.error("Failed to download image from %s: %s", url, error)
    return None


def has_images(message: discord.Message) -> bool:
    """Verifica si un mensaje tiene adjuntos de imagen."""
    for attachment in message.attachments:
        ext = "." + attachment.filename.rsplit(".", 1)[-1].lower() if "." in attachment.filename else ""
        if ext in IMAGE_EXTENSIONS:
            return True
    return False


async def extract_images(message: discord.Message) -> List[dict[str, str]]:
    """Descarga todas las imágenes adjuntas del mensaje."""
    images: List[dict[str, str]] = []
    for attachment in message.attachments:
        ext = "." + attachment.filename.rsplit(".", 1)[-1].lower() if "." in attachment.filename else ""
        if ext in IMAGE_EXTENSIONS:
            image_data = await download_image(attachment.url)
            if image_data:
                images.append(image_data)
                logger.info("Downloaded image: %s (%s bytes)", attachment.filename, attachment.size)
    return images


async def send_response(channel: discord.TextChannel, text: str) -> None:
    """Envía un texto dividiéndolo si excede el límite de Discord."""
    for chunk in split_message(text):
        await channel.send(chunk)


async def send_reply(message: discord.Message, text: str) -> None:
    """Responde al mensaje original con quote y fragmenta el texto si es necesario."""
    chunks = split_message(text)
    await message.reply(chunks[0], mention_author=False)
    for chunk in chunks[1:]:
        await message.channel.send(chunk)


def extract_search_query(text: str) -> Optional[str]:
    """Devuelve un query de búsqueda si el mensaje contiene un trigger, si no None."""
    lower = text.lower().strip()
    for trigger in SEARCH_TRIGGERS:
        if trigger in lower:
            idx = lower.index(trigger)
            query = text[idx + len(trigger):].strip()
            # Limpiar signos de interrogación y puntuación final
            query = query.rstrip("?¿!.,;:")
            if query and len(query) > 3:
                return query
    return None


# --- Spam ---

_spam_tracker: Dict[int, List[float]] = {}
_spam_cooldown: Dict[int, float] = {}
SPAM_WINDOW = 10.0
SPAM_MAX_MESSAGES = 5
SPAM_COOLDOWN_DURATION = 120.0


def check_spam(user_id: int) -> bool:
    """Detecta si un usuario está enviando mensajes demasiado rápido."""
    now = time.time()

    if user_id in _spam_cooldown:
        if now < _spam_cooldown[user_id]:
            return True
        del _spam_cooldown[user_id]

    if user_id not in _spam_tracker:
        _spam_tracker[user_id] = []

    _spam_tracker[user_id] = [timestamp for timestamp in _spam_tracker[user_id] if now - timestamp < SPAM_WINDOW]
    _spam_tracker[user_id].append(now)

    if len(_spam_tracker[user_id]) > SPAM_MAX_MESSAGES:
        _spam_cooldown[user_id] = now + SPAM_COOLDOWN_DURATION
        _spam_tracker[user_id] = []
        return True

    return False


async def handle_spam_response(message: discord.Message) -> None:
    """Responde con un aviso cuando alguien está en cooldown de spam."""
    user_id = message.author.id

    if user_id in _spam_cooldown:
        remaining = int(_spam_cooldown[user_id] - time.time())
        if remaining > SPAM_COOLDOWN_DURATION - 5:
            await message.reply("ya wey, tranquilo 😒 espera un rato va?", mention_author=False)


# --- Buffer de mensajes ---

_pending_messages: Dict[Tuple[int, int], List[discord.Message]] = {}
_pending_tasks: Dict[Tuple[int, int], asyncio.Task] = {}
BUFFER_WAIT_SECONDS = 2.5


class ConversationCog(commands.Cog):
    """Cog principal de conversación de Lulu."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author == self.bot.user:
            return
        if message.author.bot:
            return

        # No procesar comandos de prefijo (los maneja el bot)
        ctx = await self.bot.get_context(message)
        if ctx.valid:
            return

        is_dm = isinstance(message.channel, discord.DMChannel)
        is_mentioned = self.bot.user in message.mentions
        is_name_called = "lulu" in message.content.lower()
        is_reply_to_bot = (
            message.reference is not None
            and message.reference.resolved is not None
            and isinstance(message.reference.resolved, discord.Message)
            and message.reference.resolved.author == self.bot.user
        )
        is_in_allowed_channel = message.channel.id in config.ALLOWED_CHANNEL_IDS

        should_respond = (
            is_dm
            or is_mentioned
            or is_name_called
            or is_reply_to_bot
            or (len(config.ALLOWED_CHANNEL_IDS) > 0 and is_in_allowed_channel)
        )

        if should_respond:
            if check_spam(message.author.id):
                await handle_spam_response(message)
                return
            await self._handle_conversation(message)

    async def _handle_conversation(self, message: discord.Message) -> None:
        """Agrupa mensajes del mismo usuario antes de responder."""
        key = (message.channel.id, message.author.id)

        if key not in _pending_messages:
            _pending_messages[key] = []
        _pending_messages[key].append(message)

        if key in _pending_tasks and not _pending_tasks[key].done():
            _pending_tasks[key].cancel()

        _pending_tasks[key] = asyncio.create_task(self._process_after_delay(key))

    async def _process_after_delay(self, key: Tuple[int, int]) -> None:
        await asyncio.sleep(BUFFER_WAIT_SECONDS)

        messages = _pending_messages.pop(key, [])
        _pending_tasks.pop(key, None)

        if not messages:
            return

        last_message = messages[-1]
        channel_id = last_message.channel.id
        author = last_message.author

        profile = database.get_user_profile(author.id, author.name)
        database.increment_user_interactions(author.id)

        all_parts: List[str] = []
        all_images: List[dict[str, str]] = []

        for msg in messages:
            content = msg.content
            if self.bot.user in msg.mentions:
                content = content.replace(f"<@{self.bot.user.id}>", "").replace(f"<@!{self.bot.user.id}>", "")
            content = content.strip()
            if content:
                all_parts.append(content)

            if has_images(msg):
                extracted = await extract_images(msg)
                all_images.extend(extracted)

        clean_content = " ".join(all_parts)

        if not clean_content and not all_images:
            await last_message.reply("🛸 ¿Sí? ¡Aquí estoy! Dime qué onda 👾", mention_author=False)
            return

        first_message = messages[0]
        if (
            first_message.reference is not None
            and first_message.reference.resolved is not None
            and isinstance(first_message.reference.resolved, discord.Message)
            and first_message.reference.resolved.author == self.bot.user
        ):
            quoted_content = first_message.reference.resolved.content
            if quoted_content:
                clean_content = f'[Respondiendo a tu mensaje: "{quoted_content[:200]}"] {clean_content}'

        history_content = clean_content or "(envió una imagen)"
        database.add_chat_message(
            channel_id,
            user_id=author.id,
            username=author.name,
            content=history_content,
            is_bot=False,
        )

        history = database.get_chat_history(channel_id, limit=25)
        participating_user_ids = {msg["user_id"] for msg in history if not msg["is_bot"]}

        participating_profiles: List[dict[str, object]] = []
        for uid in participating_user_ids:
            username = next((msg["username"] for msg in history if msg["user_id"] == uid), "Alguien")
            participating_profiles.append(database.get_user_profile(uid, username))

        system_prompt = personality.build_system_prompt(participating_profiles)
        formatted_messages = personality.format_history_for_llm(history)

        # --- Búsqueda web ---
        search_query = extract_search_query(clean_content)
        if search_query:
            logger.info("[SEARCH] Triggered web search for: %s", search_query)
            try:
                search_results = await search.search_web(search_query, max_results=3)
                system_prompt += (
                    "\n\n--- Resultados de búsqueda web ---\n"
                    f"{search_results}\n"
                    "---\n"
                    "Usa esta información para responder de forma natural. "
                    "No copies textualmente, parafrasea con tu estilo. "
                    "Menciona las fuentes solo si el usuario lo pide."
                )
            except Exception as error:
                logger.error("[SEARCH] Error during web search: %s", error)

        # --- Generar respuesta ---
        async with last_message.channel.typing():
            if all_images:
                response_text = await llm.generate_vision_response(
                    text=clean_content,
                    image_base64_list=all_images,
                    system_prompt=system_prompt,
                    history=formatted_messages[:-1] if len(formatted_messages) > 1 else None,
                )
            else:
                response_text = await llm.generate_response(formatted_messages, system_prompt)

        await send_reply(last_message, response_text)

        database.add_chat_message(
            channel_id,
            user_id=self.bot.user.id,
            username=self.bot.user.name,
            content=response_text,
            is_bot=True,
        )

        # --- Memorias de imágenes ---
        if all_images:
            await self._process_image_memories(
                author, all_images, last_message, formatted_messages
            )
            all_images = []

        # --- Consolidación de memoria periódica ---
        # Refrescar el perfil después de incrementar interacciones
        profile = database.get_user_profile(author.id, author.name)
        if profile["interaction_count"] > 0 and profile["interaction_count"] % 3 == 0:
            asyncio.create_task(
                self._consolidate_memory_with_images(author.id, author.name, history)
            )

    async def _process_image_memories(
        self,
        author: discord.User,
        all_images: List[dict[str, str]],
        last_message: discord.Message,
        formatted_messages: List[dict],
    ) -> None:
        """Genera un resumen de las imágenes compartidas y lo guarda como memoria."""
        try:
            img_prompt = (
                "Resume brevemente (máximo 2 líneas) qué muestran estas imágenes "
                "y qué contexto relevante aportan sobre la persona que las compartió. "
                "Sé natural y conciso."
            )
            image_summary = await llm.generate_vision_response(
                text=img_prompt,
                image_base64_list=all_images,
                system_prompt=personality.LULU_LORE,
                history=formatted_messages[:-1] if len(formatted_messages) > 1 else None,
            )

            if image_summary:
                # Añadir información sobre emojis
                try:
                    text_emojis = EMOJI_REGEX.findall(last_message.content or "")
                except Exception:
                    text_emojis = []

                try:
                    server_emojis = DISCORD_EMOJI_REGEX.findall(last_message.content or "")
                except Exception:
                    server_emojis = []

                reaction_emojis = []
                try:
                    for react in last_message.reactions:
                        try:
                            reaction_emojis.append(str(react.emoji))
                        except Exception:
                            continue
                except Exception:
                    reaction_emojis = []

                extra_parts = []
                if text_emojis:
                    extra_parts.append(f"emojis en texto: {' '.join(text_emojis)}")
                if server_emojis:
                    seen = set()
                    uniq = [e for e in server_emojis if not (e in seen or seen.add(e))]
                    extra_parts.append(f"emojis de servidor: {' '.join(uniq)}")
                if reaction_emojis:
                    seen = set()
                    uniq = [e for e in reaction_emojis if not (e in seen or seen.add(e))]
                    extra_parts.append(f"reacciones: {' '.join(uniq)}")

                if extra_parts:
                    image_summary = f"{image_summary} ({'; '.join(extra_parts)})"

                database.add_image_memory(author.id, author.name, image_summary)

        except Exception as error:
            logger.error("Error generating/storing image summary: %s", error)

    async def _consolidate_memory_with_images(
        self,
        user_id: int,
        username: str,
        history: List[Dict],
    ) -> None:
        """Consolida la memoria del usuario incluyendo memorias de imágenes."""
        # Obtener memorias de imagen recientes
        image_memories = database.get_image_memories(user_id, limit=5)

        # Construir contexto extra de imágenes para la consolidación
        image_context = ""
        if image_memories:
            img_lines = [f"- {mem['summary']}" for mem in image_memories]
            image_context = (
                "\n\n[Imágenes que ha compartido recientemente]:\n"
                + "\n".join(img_lines)
            )

        # Delegar al consolidador de personalidad con el contexto enriquecido
        profile = database.get_user_profile(user_id, username)
        current_summary = profile["personality_summary"]

        dialogue_lines = []
        for msg in history:
            speaker = f"@{msg['username']}" if not msg['is_bot'] else "Lulu"
            dialogue_lines.append(f"{speaker}: {msg['message_content']}")

        consolidation_prompt = f"""
Eres la memoria a largo plazo de Lulu. Analiza la conversación reciente y actualiza el archivo de recuerdos para @{username}.

[Recuerdos actuales sobre @{username}]:
"{current_summary}"

[Conversación reciente]:
{chr(10).join(dialogue_lines)}
{image_context}

Instrucciones para la actualización:
1. Datos personales: gustos, pasatiempos, cosas que ha compartido.
2. ACTITUD hacia Lulu: ¿es buena onda? ¿grosero? ¿bromista? ¿tóxico? ¿cariñoso? Esto es MUY importante.
3. CÓMO debe tratarlo Lulu: basándote en cómo la trata, indica el tono que Lulu debería usar.
4. Nivel de confianza: nula / poca / media / alta / muchísima.
5. Si compartió imágenes, integra lo relevante de ellas en el resumen.
6. Escribe en tercera persona desde la perspectiva de Lulu.
7. Máximo 150 palabras.
8. Devuelve ÚNICAMENTE el resumen. Sin intros ni comillas.
"""

        try:
            new_summary = await llm.generate_summary(consolidation_prompt)
            if new_summary and not new_summary.startswith("*("):
                database.update_user_profile_summary(user_id, new_summary)
                logger.info("Memory consolidated for @%s (with image context)", username)
        except Exception as error:
            logger.error("Error consolidating memory for @%s: %s", username, error)


async def setup(bot: commands.Bot):
    await bot.add_cog(ConversationCog(bot))
