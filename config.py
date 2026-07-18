import os
from dotenv import load_dotenv

# Carga las variables de entorno desde variables.env
load_dotenv("variables.env")

# Configuración de Discord
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# Configuración del proveedor LLM
# Elige entre: openrouter | ollama | huggingface | google
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "google").lower()

# 1. Configuración de OpenRouter
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "google/gemma-4-31b-it")

# 2. Configuración de Ollama
OLLAMA_API_URL = os.getenv("OLLAMA_API_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma4:e4b")

# 3. Configuración de Hugging Face
HUGGINGFACE_API_TOKEN = os.getenv("HUGGINGFACE_API_TOKEN")
HUGGINGFACE_MODEL = os.getenv("HUGGINGFACE_MODEL", "google/gemma-2-27b-it")

# 4. Configuración de Google AI Studio (Gemini/Gemma API)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemma-4-31b-it")

# Ajustes generales del bot
try:
    BUMP_INTERVAL_MINUTES = int(os.getenv("BUMP_INTERVAL_MINUTES", "120"))
except ValueError:
    BUMP_INTERVAL_MINUTES = 120

DATABASE_PATH = os.getenv("DATABASE_PATH", "lulu_bot.db")

# Bump reminder channel
bump_channel_str = os.getenv("BUMP_CHANNEL_ID", "")
BUMP_CHANNEL_ID = None
if bump_channel_str.strip():
    try:
        BUMP_CHANNEL_ID = int(bump_channel_str.strip())
    except ValueError:
        pass

# Analiza los IDs de canales permitidos
allowed_channels_str = os.getenv("ALLOWED_CHANNEL_IDS", "")
ALLOWED_CHANNEL_IDS = []
if allowed_channels_str.strip():
    for cid in allowed_channels_str.split(","):
        try:
            ALLOWED_CHANNEL_IDS.append(int(cid.strip()))
        except ValueError:
            pass  # Ignorar IDs de canal inválidos

# Canal de bienvenida para saludar a nuevos miembros
welcome_channel_str = os.getenv("WELCOME_CHANNEL_ID", "")
WELCOME_CHANNEL_ID = None
if welcome_channel_str.strip():
    try:
        WELCOME_CHANNEL_ID = int(welcome_channel_str.strip())
    except ValueError:
        pass

# Canales donde Lulu puede meterse de vez en cuando en las conversaciones (lurker)
lurk_channels_str = os.getenv("LURK_CHANNEL_IDS", "")
LURK_CHANNEL_IDS = []
if lurk_channels_str.strip():
    for cid in lurk_channels_str.split(","):
        try:
            LURK_CHANNEL_IDS.append(int(cid.strip()))
        except ValueError:
            pass


def validate_config():
    """Valida que todas las variables de entorno necesarias para el proveedor seleccionado estén presentes.

    Raises:
        ValueError: Si falta alguna variable de configuración requerida.
    """
    if not DISCORD_TOKEN:
        raise ValueError(
            "Falta DISCORD_TOKEN. Agrégalo a tu archivo .env."
        )

    if LLM_PROVIDER not in ["openrouter", "ollama", "huggingface", "google"]:
        raise ValueError(
            f"LLM_PROVIDER inválido '{LLM_PROVIDER}'. Debe ser 'openrouter', 'ollama', 'huggingface' o 'google'."
        )

    if LLM_PROVIDER == "openrouter" and not OPENROUTER_API_KEY:
        raise ValueError(
            "OPENROUTER_API_KEY es obligatorio cuando LLM_PROVIDER está en 'openrouter'."
        )

    if LLM_PROVIDER == "huggingface" and not HUGGINGFACE_API_TOKEN:
        raise ValueError(
            "HUGGINGFACE_API_TOKEN es obligatorio cuando LLM_PROVIDER está en 'huggingface'."
        )

    if LLM_PROVIDER == "google" and not GEMINI_API_KEY:
        raise ValueError(
            "GEMINI_API_KEY (o GOOGLE_API_KEY) es obligatorio cuando LLM_PROVIDER está en 'google'."
        )
