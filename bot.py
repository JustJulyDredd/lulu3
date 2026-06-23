"""
bot.py — Punto de entrada de Lulu Bot 🛸
Configuración del bot, logging con rotación, carga de Cogs y arranque.
"""

import asyncio
import logging
from logging.handlers import RotatingFileHandler

import discord
from discord.ext import commands

import config
import database

# --- Logging con rotación ---

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter(LOG_FORMAT))

file_handler = RotatingFileHandler(
    "lulu_logs.txt",
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
    "cogs.bump",
    "cogs.conversation",
    "cogs.minigames",
    "cogs.social",
    "cogs.ambient",
]


@bot.event
async def on_ready() -> None:
    logger.info("Bot connected as %s (ID: %s)", bot.user.name, bot.user.id)

    try:
        synced = await bot.tree.sync()
        logger.info("Synced %s slash command(s)", len(synced))
    except Exception as error:
        logger.error("Failed to sync slash commands: %s", error)


async def main():
    async with bot:
        for ext in EXTENSIONS:
            try:
                await bot.load_extension(ext)
                logger.info("Loaded extension: %s", ext)
            except Exception as error:
                logger.error("Failed to load extension %s: %s", ext, error)

        config.validate_config()
        await bot.start(config.DISCORD_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
