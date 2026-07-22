"""
bot/main.py — Punto de entrada de Lulu Bot 🛸
Configuración del bot, logging con rotación, carga de Cogs y arranque.
"""

import argparse
import asyncio
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

import discord
from discord.ext import commands

from bot import config, database

# --- Logging con rotación ---

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter(LOG_FORMAT))

_log_path = Path(__file__).parent.parent / "lulu_logs.txt"
file_handler = RotatingFileHandler(
    _log_path,
    maxBytes=5 * 1024 * 1024,  # 5 MB
    backupCount=3,
    encoding="utf-8",
)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter(LOG_FORMAT))

logging.basicConfig(level=logging.INFO, handlers=[console_handler, file_handler])
logger = logging.getLogger("lulu.bot")

# --- Inicialización ---

database.init_db()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    help_command=commands.DefaultHelpCommand(),
)

# --- Cogs ---

EXTENSIONS = [
    "bot.cogs.bump",
    "bot.cogs.conversation",
    "bot.cogs.minigames",
    "bot.cogs.social",
    "bot.cogs.ambient",
]


@bot.event
async def on_ready() -> None:
    assert bot.user is not None
    logger.info("Bot connected as %s (ID: %s)", bot.user.name, bot.user.id)

    try:
        synced = await bot.tree.sync()
        logger.info("Synced %s slash command(s)", len(synced))
    except Exception as error:
        logger.error("Failed to sync slash commands: %s", error)


async def main() -> None:
    async with bot:
        for ext in EXTENSIONS:
            try:
                await bot.load_extension(ext)
                logger.info("Loaded extension: %s", ext)
            except Exception as error:
                logger.error("Failed to load extension %s: %s", ext, error)

        config.validate_config()
        assert config.DISCORD_TOKEN is not None
        await bot.start(config.DISCORD_TOKEN)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Inicia el bot principal de Discord.")
    args = parser.parse_args()
    asyncio.run(main())
