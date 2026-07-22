import logging
import random
import re
from typing import Dict, List

import httpx
from openai import AsyncOpenAI

from bot import config

logger = logging.getLogger("lulu.llm")

TIRED_RESPONSES = [
    "zzz... perdón, estoy súper cansada ahorita, luego les respondo 😴",
    "ay no puedo más, necesito un descanso... luego hablamos va? 💤",
    "me estoy quedando dormida jaja, denme un rato y ya les contesto 😪",
    "ugh mi cerebro no da para más ahorita, vuelvo al rato ✨",
    "ya me agotaron jaja, déjenme descansar un poco y ya vuelvo 🛸💤",
    "ntp, estoy aquí pero necesito un break, luego sigo 😴",
    "perdón, me siento medio zzz ahorita... al rato respondo bien 💫",
]


def clean_response(text: str) -> str:
    """Limpia tags de pensamiento interno y devuelve la respuesta final."""
    patterns = [
        r"<thought>.*?</thought>",
        r"<think>.*?</think>",
        r"<reasoning>.*?</reasoning>",
        r"<reflection>.*?</reflection>",
        r"<thought>.*",
        r"<think>.*",
    ]

    for pattern in patterns:
        text = re.sub(pattern, "", text, flags=re.DOTALL | re.IGNORECASE)

    return text.strip()


def _get_client_and_model(provider: str):
    """Configura el cliente y el modelo según el proveedor elegido."""
    if provider == "openrouter":
        return (
            AsyncOpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=config.OPENROUTER_API_KEY,
                default_headers={
                    "HTTP-Referer": "https://github.com/google/antigravity",
                    "X-Title": "Lulu Discord Bot",
                },
            ),
            config.OPENROUTER_MODEL,
        )

    if provider == "ollama":
        base_url = config.OLLAMA_API_URL
        if not base_url.endswith("/v1"):
            base_url = f"{base_url}/v1"
        return (
            AsyncOpenAI(base_url=base_url, api_key="ollama"),
            config.OLLAMA_MODEL,
        )

    if provider == "huggingface":
        return (
            AsyncOpenAI(
                base_url="https://api-inference.huggingface.co/v1",
                api_key=config.HUGGINGFACE_API_TOKEN,
            ),
            config.HUGGINGFACE_MODEL,
        )

    if provider == "google":
        return (
            AsyncOpenAI(
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                api_key=config.GEMINI_API_KEY,
            ),
            config.GEMINI_MODEL,
        )

    raise ValueError(f"Unknown LLM provider: {provider}")


def get_fallback_chain() -> List[str]:
    """Genera la lista de proveedores disponibles en orden de prioridad."""
    primary = config.LLM_PROVIDER
    all_providers = ["google", "openrouter", "huggingface", "ollama"]
    configured = []

    # Verificar qué proveedores tienen API Keys o configuraciones válidas
    if config.GEMINI_API_KEY and not config.GEMINI_API_KEY.startswith("your_"):
        configured.append("google")
    if config.OPENROUTER_API_KEY and not config.OPENROUTER_API_KEY.startswith("your_"):
        configured.append("openrouter")
    if config.HUGGINGFACE_API_TOKEN and not config.HUGGINGFACE_API_TOKEN.startswith("your_"):
        configured.append("huggingface")
    if config.OLLAMA_API_URL and not config.OLLAMA_API_URL.startswith("your_"):
        configured.append("ollama")

    # Armar la cadena empezando por el principal
    chain = []
    if primary in configured:
        chain.append(primary)
    for p in configured:
        if p not in chain:
            chain.append(p)

    # Fallback de emergencia si nada está configurado o hay solo placeholders
    if not chain:
        chain = [primary] if primary in all_providers else ["google"]

    logger.info(f"Cadena de proveedores de IA configurada: {chain}")
    return chain


async def generate_response(
    messages: list,
    system_prompt: str = None,
    temperature: float = 0.8,
) -> str:
    """Pide una respuesta al modelo intentando múltiples proveedores en cascada si hay fallos."""
    providers = get_fallback_chain()
    full_messages = []

    if system_prompt:
        full_messages.append({"role": "system", "content": system_prompt})
    full_messages.extend(messages)

    last_error = None
    for provider in providers:
        logger.info(f"Intentando generar respuesta con proveedor: {provider}")
        try:
            client, model = _get_client_and_model(provider)
            response = await client.chat.completions.create(
                model=model,
                messages=full_messages,
                temperature=temperature,
                max_tokens=2000,
            )
            content = response.choices[0].message.content
            if content:
                cleaned = clean_response(content)
                if cleaned:
                    logger.info(f"Respuesta generada exitosamente con proveedor {provider}")
                    return cleaned
        except Exception as error:
            last_error = error
            logger.error(
                f"Error al generar respuesta con el proveedor {provider}: {error}"
            )

            # Fallback clásico a la API REST directa de Hugging Face si el cliente de HF falla
            if provider == "huggingface":
                logger.info("Intentando fallback directo de la API REST de Hugging Face...")
                try:
                    prompt = ""
                    if system_prompt:
                        prompt += f"System: {system_prompt}\n\n"
                    for msg in messages:
                        role = "User" if msg["role"] == "user" else "Lulu" if msg["role"] == "assistant" else "System"
                        prompt += f"{role}: {msg['content']}\n"
                    prompt += "Lulu: "

                    headers = {"Authorization": f"Bearer {config.HUGGINGFACE_API_TOKEN}"}
                    payload = {
                        "inputs": prompt,
                        "parameters": {
                            "max_new_tokens": 250,
                            "temperature": temperature,
                            "return_full_text": False,
                        },
                    }
                    api_url = f"https://api-inference.huggingface.co/models/{config.HUGGINGFACE_MODEL}"

                    async with httpx.AsyncClient(timeout=30.0) as http_client:
                        res = await http_client.post(api_url, json=payload, headers=headers)
                        if res.status_code == 200:
                            data = res.json()
                            if isinstance(data, list) and data:
                                generated = data[0].get("generated_text", "")
                                if "\nUser:" in generated:
                                    generated = generated.split("\nUser:")[0]
                                if "\nLulu:" in generated:
                                    generated = generated.split("\nLulu:")[0]
                                cleaned = clean_response(generated)
                                if cleaned:
                                    logger.info("Respuesta de fallback directo REST de Hugging Face exitosa")
                                    return cleaned
                        logger.error("HF fallback REST falló con estado %s: %s", res.status_code, res.text)
                except Exception as fallback_error:
                    logger.error("Error de fallback de la API REST de Hugging Face: %s", fallback_error)

    if last_error:
        error_str = str(last_error).lower()
        if any(keyword in error_str for keyword in [
            "429",
            "rate limit",
            "quota",
            "resource exhausted",
            "too many requests",
            "limit exceeded",
            "billing",
        ]):
            return random.choice(TIRED_RESPONSES)

    return random.choice(TIRED_RESPONSES)


async def generate_summary(prompt: str) -> str:
    """Genera un resumen sencillo y objetivo."""
    messages = [{"role": "user", "content": prompt}]
    return await generate_response(
        messages,
        system_prompt="Eres un sistema de procesamiento de información. Tu trabajo es resumir objetivamente.",
        temperature=0.3,
    )


async def generate_vision_response(
    text: str,
    image_base64_list: list,
    system_prompt: str = None,
    history: list = None,
    temperature: float = 0.8,
) -> str:
    """Analiza imágenes e intenta responder como Lulu usando proveedores con soporte de visión."""
    all_providers = get_fallback_chain()
    vision_providers = []

    # Priorizar google para visión, luego openrouter
    if "google" in all_providers:
        vision_providers.append("google")
    if "openrouter" in all_providers:
        vision_providers.append("openrouter")

    # Si ninguno tiene visión declarada de forma explícita, intentamos con todos los configurados
    if not vision_providers:
        vision_providers = all_providers

    full_messages = []
    if system_prompt:
        full_messages.append({"role": "system", "content": system_prompt})
    if history:
        full_messages.extend(history)

    content_parts = []
    for img in image_base64_list:
        content_parts.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:{img['media_type']};base64,{img['base64']}"},
            }
        )

    content_parts.append(
        {"type": "text", "text": text or "¿Qué ves en esta imagen?"}
    )
    full_messages.append({"role": "user", "content": content_parts})

    for provider in vision_providers:
        logger.info(f"Intentando visión con proveedor: {provider}")
        try:
            client, model = _get_client_and_model(provider)
            response = await client.chat.completions.create(
                model=model,
                messages=full_messages,
                temperature=temperature,
                max_tokens=2000,
            )
            content = response.choices[0].message.content
            if content:
                cleaned = clean_response(content)
                if cleaned:
                    logger.info(f"Visión exitosa con proveedor {provider}")
                    return cleaned
        except Exception as error:
            logger.error(f"Error al procesar visión con proveedor {provider}: {error}")

    return "*(No pude procesar la imagen, algo salió mal 😵)*"


async def generate_emoji_reaction(message_content: str) -> str:
    """Pide al modelo un solo emoji que sea apropiado para reaccionar a un mensaje usando proveedores en cascada."""
    providers = get_fallback_chain()
    prompt = (
        "Eres Lulu, una chica de 16 años. Mira este mensaje de Discord y elige EXACTAMENTE UN emoji Unicode de reacción "
        "que usarías para reaccionar a él de forma genuina. "
        "No uses emojis aburridos como el pulgar arriba si no viene al caso. Sé expresiva y adolescente. "
        "Responde ÚNICAMENTE con el emoji (1 solo carácter emoji). Sin texto, sin explicaciones, sin comillas, sin formato.\n\n"
        f"Mensaje: {message_content}"
    )

    for provider in providers:
        try:
            client, model = _get_client_and_model(provider)
            response = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=5,
            )
            emoji = response.choices[0].message.content.strip()
            emoji = clean_response(emoji)
            emoji_match = re.search(r'[\U00010000-\U0010ffff\u2600-\u27ff]', emoji)
            if emoji_match:
                return emoji_match.group(0)
            return emoji
        except Exception as e:
            logger.error(f"Error al generar emoji con proveedor {provider}: {e}")

    return None


