import asyncio
import base64
import logging
import random
import time
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple

import httpx
import discord
from discord.ext import commands, tasks
import re

import config
import database
import llm
import personality

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("lulu.bot")

database.init_db()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    help_command=commands.DefaultHelpCommand(),
)

DISBOARD_BOT_ID = 302050872383242240
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}

# Regex sencillo para capturar muchos emoji Unicode comunes
EMOJI_REGEX = re.compile(
    "[\U0001F300-\U0001F5FF\U0001F600-\U0001F64F\U0001F680-\U0001F6FF\u2600-\u26FF\u2700-\u27BF]+",
    flags=re.UNICODE,
)

# Regex para capturar emojis de servidor (custom emojis)
# Formato: <:nombre:ID> o <a:nombre:ID> (animado)
DISCORD_EMOJI_REGEX = re.compile(r"<a?:\w+:\d+>", re.UNICODE)

LURK_CHANCE = 0.02
LURK_GLOBAL_COOLDOWN = 3600
LURK_CHANNEL_COOLDOWN = 5400
REACT_CHANCE = 0.08
_last_lurk_global = 0.0
_last_lurk_per_channel: Dict[int, float] = {}

LULU_REACTIONS = [
    "😂",
    "💀",
    "✨",
    "👀",
    "🔥",
    "💫",
    "👾",
    "🛸",
    "😭",
    "🫶",
    "💀",
    "🤣",
    "❤️",
    "🍕",
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

BUMP_SUCCESS_PATTERNS = [
    "bump done",
    "bumped successfully",
    "bump successful",
    "has been bumped",
    "server bumped",
    "publicación actualizada",
    "bump realizado",
    "servidor bumpeado",
    "bump exitoso",
    "bump hecho",
    "bump feito",
    "publicação atualizada",
    "bump effectué",
    "bump réussi",
    "bump erfolgreich",
    "server gebumpt",
    "범프 완료",
    "バンプ完了",
    ":thumbsup:",
    "👍",
]


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
            logger.info("Bump detected via interaction_metadata.name == 'bump'")

    if is_from_disboard and is_bump_interaction:
        return True

    if is_from_disboard:
        logger.info(
            "[DISBOARD MSG] content='%s' | embeds=%s | interaction=%s | type=%s",
            message.content[:100],
            len(message.embeds),
            message.interaction,
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
            logger.info("Bump detected via content match")
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
                logger.info("Bump detected via embed text match")
                return True

        if any(embed.image and embed.image.url for embed in message.embeds):
            logger.info("Bump detected via Disboard embed with image")
            return True

        if any(embed.color and embed.color.value in (2405303, 2406327, 0x24b7b7) for embed in message.embeds):
            logger.info("Bump detected via Disboard embed color")
            return True

        if message.embeds:
            logger.info("Bump detected: Disboard message with embed (fallback)")
            return True

    if is_bump_interaction:
        logger.info("Bump detected via interaction only (author ID may have changed)")
        return True

    return False


async def get_bump_reminder_text() -> str:
    """Genera un recordatorio de bump en el estilo de Lulu."""
    prompt = (
        "Genera un mensaje muy corto e informal (máximo 2 líneas) avisando a todos "
        "de que ya pasaron las 2 horas y es hora de hacer bump (comando /bump) en el servidor. "
        "Recuerda que eres Lulu, una adolescente graciosa y amigable. Usa algún emoji (ej. 🛸, 👾). "
        "No los llames 'humanos', son tus amigos."
    )
    try:
        reminder = await llm.generate_response(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=personality.LULU_LORE,
            temperature=0.9,
        )
        if reminder and not reminder.startswith("*("):
            return reminder
    except Exception as error:
        logger.error("Failed to generate LLM bump reminder: %s", error)

    return "🛸 ¡Hey! Ya pasaron 2 horas. ¡Es hora del bump! Usen `/bump` por fis. 👾"


async def get_bump_ack_text() -> str:
    """Genera un mensaje de agradecimiento cuando el bump fue exitoso."""
    prompt = (
        "El servidor acaba de ser bump-eado exitosamente. Genera una respuesta corta "
        "(máximo 2 líneas) agradeciendo a la persona y diciendo que vas a poner un temporizador "
        "de 2 horas para recordarles. Usa tu estilo adolescente de Lulu. No los llames 'humanos'."
    )
    try:
        ack = await llm.generate_response(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=personality.LULU_LORE,
            temperature=0.9,
        )
        if ack and not ack.startswith("*("):
            return ack
    except Exception as error:
        logger.error("Failed to generate LLM bump ack: %s", error)

    return "👾 ¡Súper! Server bump-eado. ¡Pongo mi alarma para dentro de 2 horas! 🛸"


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


@bot.event
async def on_ready() -> None:
    logger.info("Bot connected as %s (ID: %s)", bot.user.name, bot.user.id)

    if not check_bump_reminders.is_running():
        check_bump_reminders.start()
    if not rotate_status.is_running():
        rotate_status.start()
    if not random_message.is_running():
        random_message.start()
    if not check_birthdays.is_running():
        check_birthdays.start()

    try:
        synced = await bot.tree.sync()
        logger.info("Synced %s slash command(s)", len(synced))
    except Exception as error:
        logger.error("Failed to sync slash commands: %s", error)

    await bot.change_presence(activity=discord.Game(name="pasando el rato 🛸"))

    if config.BUMP_CHANNEL_ID:
        await _scan_bump_channel_history()

    now = time.time()
    pending = database.get_pending_reminders(now)
    if pending:
        logger.info("Found %s pending bump reminder(s) from while offline.", len(pending))
        for record in pending:
            channel_id = record["channel_id"]
            try:
                channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)
                if channel:
                    reminder_msg = await get_bump_reminder_text()
                    await channel.send(f"@here {reminder_msg}")
                database.mark_reminder_sent(channel_id)
                logger.info("Sent missed bump reminder to channel %s", channel_id)
            except Exception as error:
                logger.error("Failed to send missed bump reminder to %s: %s", channel_id, error)
                database.mark_reminder_sent(channel_id)


async def _scan_bump_channel_history() -> None:
    """Busca en el historial reciente del canal de bump el último bump válido."""
    logger.info("Scanning bump channel %s for recent bumps...", config.BUMP_CHANNEL_ID)

    try:
        channel = bot.get_channel(config.BUMP_CHANNEL_ID)
        if not channel:
            channel = await bot.fetch_channel(config.BUMP_CHANNEL_ID)

        if not channel:
            logger.error("Could not find bump channel %s", config.BUMP_CHANNEL_ID)
            return

        last_bump_time: Optional[float] = None
        async for msg in channel.history(limit=50):
            if is_disboard_bump_message(msg):
                last_bump_time = msg.created_at.timestamp()
                logger.info(
                    "Found bump in history from %s by interaction/Disboard",
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
                    "⏰ Bump timer recovered! Last bump was %ss ago. Next reminder in %sh %sm %ss",
                    int(time_since_bump),
                    hours,
                    minutes,
                    seconds,
                )
                database.set_bump_time(config.BUMP_CHANNEL_ID, next_bump)
            else:
                logger.info(
                    "⏰ Last bump was %ss ago — timer already expired! Sending reminder now.",
                    int(time_since_bump),
                )
                database.set_bump_time(config.BUMP_CHANNEL_ID, now - 1)
        else:
            logger.info("No recent bumps found in channel history.")
    except Exception as error:
        logger.error("Error scanning bump channel history: %s", error)


@bot.event
async def on_message(message: discord.Message) -> None:
    if message.author == bot.user:
        return

    if message.author.bot and message.author != bot.user:
        interaction_meta = getattr(message, "interaction_metadata", None)
        logger.info(
            "[BOT MSG] author='%s' (ID: %s) | content='%s' | embeds=%s | channel=%s | interaction=%s",
            message.author.name,
            message.author.id,
            message.content[:80],
            len(message.embeds),
            message.channel.id,
            interaction_meta,
        )

    if is_disboard_bump_message(message):
        bump_channel_id = config.BUMP_CHANNEL_ID or message.channel.id
        next_bump = time.time() + (config.BUMP_INTERVAL_MINUTES * 60)
        database.set_bump_time(bump_channel_id, next_bump)
        logger.info(
            "✅ BUMP REGISTERED! Channel %s -> Reminder in channel %s. Next bump at %s",
            message.channel.id,
            bump_channel_id,
            datetime.fromtimestamp(next_bump).strftime("%H:%M:%S"),
        )

        interaction_meta = getattr(message, "interaction_metadata", None)
        if interaction_meta:
            bumper = getattr(interaction_meta, "user", None)
            if bumper:
                database.record_bump(bumper.id, bumper.name)
                logger.info("Bump recorded for @%s", bumper.name)

        ack_msg = await get_bump_ack_text()
        await message.channel.send(ack_msg)
        return

    if message.author.bot:
        return

    ctx = await bot.get_context(message)
    if ctx.valid:
        await bot.process_commands(message)
        return

    is_dm = isinstance(message.channel, discord.DMChannel)
    is_mentioned = bot.user in message.mentions
    is_name_called = "lulu" in message.content.lower()
    is_reply_to_bot = (
        message.reference is not None
        and message.reference.resolved is not None
        and isinstance(message.reference.resolved, discord.Message)
        and message.reference.resolved.author == bot.user
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
        await handle_conversation(message)
    else:
        await maybe_lurk(message)


_pending_messages: Dict[Tuple[int, int], List[discord.Message]] = {}
_pending_tasks: Dict[Tuple[int, int], asyncio.Task] = {}
BUFFER_WAIT_SECONDS = 2.5


async def handle_conversation(message: discord.Message) -> None:
    """Agrupa mensajes del mismo usuario antes de responder."""
    key = (message.channel.id, message.author.id)

    if key not in _pending_messages:
        _pending_messages[key] = []
    _pending_messages[key].append(message)

    if key in _pending_tasks and not _pending_tasks[key].done():
        _pending_tasks[key].cancel()

    _pending_tasks[key] = asyncio.create_task(_process_after_delay(key))


async def _process_after_delay(key: Tuple[int, int]) -> None:
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
    profile = database.get_user_profile(author.id, author.name)

    all_parts: List[str] = []
    all_images: List[dict[str, str]] = []

    for msg in messages:
        content = msg.content
        if bot.user in msg.mentions:
            content = content.replace(f"<@{bot.user.id}>", "").replace(f"<@!{bot.user.id}>", "")
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
        and first_message.reference.resolved.author == bot.user
    ):
        quoted_content = first_message.reference.resolved.content
        if quoted_content:
            clean_content = f"[Respondiendo a tu mensaje: \"{quoted_content[:200]}\"] {clean_content}"

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
        user_id=bot.user.id,
        username=bot.user.name,
        content=response_text,
        is_bot=True,
    )

    # Si se procesaron imágenes, generamos un resumen breve (no guardamos la imagen)
    # y lo almacenamos como memoria asociada al usuario. Luego liberamos la variable
    # que contenía los datos en base64 para no persistir binarios en memoria.
    if all_images:
        try:
            img_prompt = "Resume brevemente (máximo 2 líneas) qué muestran estas imágenes y qué contexto relevante aportan sobre la persona que las compartió. Sé natural y conciso."
            image_summary = await llm.generate_vision_response(
                text=img_prompt,
                image_base64_list=all_images,
                system_prompt=personality.LULU_LORE,
                history=formatted_messages[:-1] if len(formatted_messages) > 1 else None,
            )

            if image_summary:
                # Añadir información sobre emojis visibles en el mensaje o reacciones
                try:
                    text_emojis = EMOJI_REGEX.findall(last_message.content or "")
                except Exception:
                    text_emojis = []

                # También capturar emojis de servidor (custom emojis)
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
                    # Deduplicar emojis de servidor
                    seen = set()
                    uniq = []
                    for e in server_emojis:
                        if e not in seen:
                            seen.add(e)
                            uniq.append(e)
                    extra_parts.append(f"emojis de servidor: {' '.join(uniq)}")
                if reaction_emojis:
                    # Deduplicar preservando orden
                    seen = set()
                    uniq = []
                    for e in reaction_emojis:
                        if e not in seen:
                            seen.add(e)
                            uniq.append(e)
                    extra_parts.append(f"reacciones: {' '.join(uniq)}")

                if extra_parts:
                    image_summary = f"{image_summary} ({'; '.join(extra_parts)})"

                # Guardar resumen en tabla de memorias de imágenes
                database.add_image_memory(author.id, author.name, image_summary)

                # También actualizar el resumen del perfil del usuario con una nota corta
                try:
                    profile = database.get_user_profile(author.id, author.name)
                    current = profile.get("personality_summary", "")
                    addition = f"Compartió una imagen: {image_summary}"
                    # Evitar que el resumen crezca sin control
                    max_len = 800
                    new_summary = (current + " " + addition).strip()
                    if len(new_summary) > max_len:
                        new_summary = new_summary[: max_len - 3] + "..."
                    database.update_user_profile_summary(author.id, new_summary)
                except Exception:
                    pass
        except Exception as error:
            logger.error("Error generating/storing image summary: %s", error)

        # Liberar la lista de imágenes (no almacenamos los base64 en la BD)
        all_images = []

    if profile["interaction_count"] > 0 and profile["interaction_count"] % 3 == 0:
        asyncio.create_task(personality.consolidate_user_memory(author.id, author.name, history))


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


@bot.tree.command(name="status", description="Ver cuánto falta para el próximo bump")
async def slash_status(interaction: discord.Interaction) -> None:
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


@bot.tree.command(name="remember", description="Ver qué recuerda Lulu de ti")
async def slash_remember(interaction: discord.Interaction) -> None:
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


@bot.tree.command(name="cumple", description="Registra tu cumpleaños para que Lulu te felicite")
@discord.app_commands.describe(dia="Día de tu cumpleaños (1-31)", mes="Mes de tu cumpleaños (1-12)")
async def slash_cumple(interaction: discord.Interaction, dia: int, mes: int) -> None:
    if not (1 <= mes <= 12 and 1 <= dia <= 31):
        await interaction.response.send_message("eso no es una fecha real 😒", ephemeral=True)
        return

    meses = [
        "",
        "enero",
        "febrero",
        "marzo",
        "abril",
        "mayo",
        "junio",
        "julio",
        "agosto",
        "septiembre",
        "octubre",
        "noviembre",
        "diciembre",
    ]

    database.set_birthday(interaction.user.id, interaction.user.name, mes, dia)
    await interaction.response.send_message(
        f"Listo! Ya me apunté tu cumple: **{dia} de {meses[mes]}** 🎂✨ te voy a felicitar ese día!"
    )


@bot.tree.command(name="ranking", description="Ver el ranking de bumps del server")
async def slash_ranking(interaction: discord.Interaction) -> None:
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


@bot.tree.command(name="rps", description="Juega piedra papel o tijera con Lulu o con un amigo")
@discord.app_commands.describe(oponente="Si quieres jugar contra un amigo, etiquétalo aquí")
async def slash_rps(interaction: discord.Interaction, oponente: discord.Member = None) -> None:
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


@bot.tree.command(name="gato", description="Juega Tres en Raya (Tic Tac Toe) contra Lulu o un amigo")
@discord.app_commands.describe(oponente="Opcional: Etiqueta al amigo contra el que quieres jugar")
async def slash_gato(interaction: discord.Interaction, oponente: discord.Member = None) -> None:
    import games

    if oponente is None:
        oponente = bot.user

    if oponente.id == interaction.user.id:
        await interaction.response.send_message("no puedes jugar contra ti mismo 😒", ephemeral=True)
        return
    if oponente.bot and oponente.id != bot.user.id:
        await interaction.response.send_message("solo yo sé jugar al gato, los demás bots no tienen cerebro 💅", ephemeral=True)
        return

    embed, view = games.get_tictactoe_view(interaction.user, oponente)
    await interaction.response.send_message(embed=embed, view=view)
    view.message = await interaction.original_response()


@bot.tree.command(name="trivia", description="Lulu te hace una pregunta de trivia")
async def slash_trivia(interaction: discord.Interaction) -> None:
    import games

    await interaction.response.defer()
    embed, view = await games.get_trivia_question()

    message = await interaction.followup.send(embed=embed, view=view, wait=True)
    view.message = message


@bot.tree.command(name="ranking_juegos", description="Ver quién manda en los minijuegos")
@discord.app_commands.describe(juego="Elige qué ranking quieres ver")
@discord.app_commands.choices(
    juego=[
        discord.app_commands.Choice(name="🧠 Trivia", value="trivia"),
        discord.app_commands.Choice(name="🪨✂️📄 Piedra Papel Tijera", value="rps"),
        discord.app_commands.Choice(name="❌⭕ Gato (Tres en raya)", value="gato"),
    ]
)
async def slash_ranking_juegos(interaction: discord.Interaction, juego: discord.app_commands.Choice[str]) -> None:
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


@bot.command(name="mockbump")
async def mock_bump_command(ctx: commands.Context, seconds: int = None) -> None:
    """Simula un bump exitoso para pruebas."""
    if seconds is None:
        next_bump = time.time() + (config.BUMP_INTERVAL_MINUTES * 60)
        time_msg = f"{config.BUMP_INTERVAL_MINUTES} minutos"
    else:
        next_bump = time.time() + seconds
        time_msg = f"{seconds} segundos"

    bump_channel_id = config.BUMP_CHANNEL_ID or ctx.channel.id
    database.set_bump_time(bump_channel_id, next_bump)
    logger.info("Mock bump scheduled for %s", time_msg)

    ack_msg = await get_bump_ack_text()
    if seconds is not None:
        ack_msg += f" (Modo simulación: sonará en {seconds} segundos)"
    await ctx.send(ack_msg)


@tasks.loop(seconds=10.0)
async def check_bump_reminders() -> None:
    """Verifica si hay recordatorios de bump pendientes."""
    now = time.time()
    pending = database.get_pending_reminders(now)

    for record in pending:
        channel_id = record["channel_id"]
        channel = bot.get_channel(channel_id)

        if not channel:
            try:
                channel = await bot.fetch_channel(channel_id)
            except Exception as error:
                logger.error("Could not fetch channel %s: %s", channel_id, error)
                database.mark_reminder_sent(channel_id)
                continue

        try:
            reminder_msg = await get_bump_reminder_text()
            await channel.send(f"@here {reminder_msg}")
            database.mark_reminder_sent(channel_id)
            logger.info("Sent bump reminder to channel %s", channel_id)
        except Exception as error:
            logger.error("Error sending bump reminder to %s: %s", channel_id, error)


@check_bump_reminders.before_loop
async def before_check_bump_reminders() -> None:
    await bot.wait_until_ready()


_birthdays_checked_today: Set[int] = set()


@tasks.loop(hours=1)
async def check_birthdays() -> None:
    """Revisa cumpleaños y envía felicitaciones."""
    if not config.WELCOME_CHANNEL_ID:
        return

    now = datetime.now()
    today_key = now.month * 100 + now.day

    if now.hour == 0:
        _birthdays_checked_today.clear()

    birthdays = database.get_todays_birthdays(now.month, now.day)
    channel = bot.get_channel(config.WELCOME_CHANNEL_ID)
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
async def before_check_birthdays() -> None:
    await bot.wait_until_ready()


@bot.event
async def on_member_join(member: discord.Member) -> None:
    """Da la bienvenida a nuevos miembros con un mensaje personalizado."""
    if not config.WELCOME_CHANNEL_ID:
        return

    channel = bot.get_channel(config.WELCOME_CHANNEL_ID)
    if not channel:
        try:
            channel = await bot.fetch_channel(config.WELCOME_CHANNEL_ID)
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


@tasks.loop(minutes=30)
async def rotate_status() -> None:
    """Cambia el estado de Lulu cada 30 minutos."""
    status = random.choice(STATUS_MESSAGES)
    await bot.change_presence(activity=status)
    logger.info("Status rotated to: %s", status)


@rotate_status.before_loop
async def before_rotate_status() -> None:
    await bot.wait_until_ready()


@tasks.loop(hours=3)
async def random_message() -> None:
    """Envía un mensaje casual en los canales de lurk para mantener presencia."""
    if not config.LURK_CHANNEL_IDS:
        return

    channel_id = random.choice(config.LURK_CHANNEL_IDS)
    channel = bot.get_channel(channel_id)
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
async def before_random_message() -> None:
    await bot.wait_until_ready()
    await asyncio.sleep(random.randint(600, 3600))


async def maybe_lurk(message: discord.Message) -> None:
    """De vez en cuando Lulu reacciona o comenta en canales de lurk."""
    global _last_lurk_global

    if message.channel.id not in config.LURK_CHANNEL_IDS:
        return
    if message.author.bot:
        return
    if len(message.content) < 15:
        return

    now = time.time()
    if random.random() < REACT_CHANCE:
        try:
            emoji = random.choice(LULU_REACTIONS)
            await message.add_reaction(emoji)
        except Exception:
            pass

    if random.random() > LURK_CHANCE:
        return
    if now - _last_lurk_global < LURK_GLOBAL_COOLDOWN:
        return

    last_channel_lurk = _last_lurk_per_channel.get(message.channel.id, 0)
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
            _last_lurk_global = now
            _last_lurk_per_channel[message.channel.id] = now

            database.add_chat_message(
                message.channel.id,
                message.author.id,
                message.author.name,
                message.content,
                is_bot=False,
            )
            database.add_chat_message(
                message.channel.id,
                bot.user.id,
                bot.user.name,
                response,
                is_bot=True,
            )
            logger.info("[LURK] Responded in channel %s", message.channel.id)
    except Exception as error:
        logger.error("[LURK] Error: %s", error)


if __name__ == "__main__":
    config.validate_config()
    bot.run(config.DISCORD_TOKEN)
