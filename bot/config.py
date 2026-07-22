import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from variables.env file
_env_path = Path(__file__).parent.parent / "variables.env"
load_dotenv(_env_path)

# Discord settings
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# LLM Provider settings
# Choose from: openrouter | ollama | huggingface | google
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "google").lower()

# 1. OpenRouter Configuration
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "google/gemma-4-31b-it")

# 2. Ollama Configuration
OLLAMA_API_URL = os.getenv("OLLAMA_API_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma4:e4b")

# 3. Hugging Face Configuration
HUGGINGFACE_API_TOKEN = os.getenv("HUGGINGFACE_API_TOKEN")
HUGGINGFACE_MODEL = os.getenv("HUGGINGFACE_MODEL", "google/gemma-2-27b-it")

# 4. Google AI Studio (Gemini/Gemma API) Configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemma-4-31b-it")

# General Bot Settings
try:
    BUMP_INTERVAL_MINUTES = int(os.getenv("BUMP_INTERVAL_MINUTES", "120"))
except ValueError:
    BUMP_INTERVAL_MINUTES = 120

DATABASE_PATH = os.getenv("DATABASE_PATH", str(Path(__file__).parent.parent / "lulu_bot.db"))

# Bump reminder channel
bump_channel_str = os.getenv("BUMP_CHANNEL_ID", "")
BUMP_CHANNEL_ID = None
if bump_channel_str.strip():
    try:
        BUMP_CHANNEL_ID = int(bump_channel_str.strip())
    except ValueError:
        pass

# Parse allowed channel IDs
allowed_channels_str = os.getenv("ALLOWED_CHANNEL_IDS", "")
ALLOWED_CHANNEL_IDS = []
if allowed_channels_str.strip():
    for cid in allowed_channels_str.split(","):
        try:
            ALLOWED_CHANNEL_IDS.append(int(cid.strip()))
        except ValueError:
            pass  # Ignore invalid channel IDs

# Welcome channel for greeting new members
welcome_channel_str = os.getenv("WELCOME_CHANNEL_ID", "")
WELCOME_CHANNEL_ID = None
if welcome_channel_str.strip():
    try:
        WELCOME_CHANNEL_ID = int(welcome_channel_str.strip())
    except ValueError:
        pass

# Channels where Lulu can occasionally jump into conversations (lurk)
lurk_channels_str = os.getenv("LURK_CHANNEL_IDS", "")
LURK_CHANNEL_IDS = []
if lurk_channels_str.strip():
    for cid in lurk_channels_str.split(","):
        try:
            LURK_CHANNEL_IDS.append(int(cid.strip()))
        except ValueError:
            pass


def validate_config():
    """Validates that all required environment variables for the selected provider are present.

    Raises:
        ValueError: If a required configuration variable is missing.
    """
    if not DISCORD_TOKEN:
        raise ValueError(
            "DISCORD_TOKEN is missing. Please add it to your .env file."
        )

    if LLM_PROVIDER not in ["openrouter", "ollama", "huggingface", "google"]:
        raise ValueError(
            f"Invalid LLM_PROVIDER '{LLM_PROVIDER}'. Must be 'openrouter', 'ollama', 'huggingface', or 'google'."
        )

    if LLM_PROVIDER == "openrouter" and not OPENROUTER_API_KEY:
        raise ValueError(
            "OPENROUTER_API_KEY is required when LLM_PROVIDER is set to 'openrouter'."
        )

    if LLM_PROVIDER == "huggingface" and not HUGGINGFACE_API_TOKEN:
        raise ValueError(
            "HUGGINGFACE_API_TOKEN is required when LLM_PROVIDER is set to 'huggingface'."
        )

    if LLM_PROVIDER == "google" and not GEMINI_API_KEY:
        raise ValueError(
            "GEMINI_API_KEY (or GOOGLE_API_KEY) is required when LLM_PROVIDER is set to 'google'."
        )
