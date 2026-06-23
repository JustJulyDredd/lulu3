import logging
import random
import re
from typing import Dict, List

import httpx
from openai import AsyncOpenAI

import config

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


def _get_client_and_model():
    """Configura el cliente y el modelo según el proveedor elegido."""
    provider = config.LLM_PROVIDER

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


async def generate_response(
    messages: list,
    system_prompt: str = None,
    temperature: float = 0.8,
) -> str:
    """Pide una respuesta al modelo y limpia la salida."""
    client, model = _get_client_and_model()
    full_messages = []

    if system_prompt:
        full_messages.append({"role": "system", "content": system_prompt})
    full_messages.extend(messages)

    try:
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
                return cleaned
        return "*(Se quedó pensando en silencio...)*"
    except Exception as error:
        error_str = str(error).lower()
        logger.error(
            "Error generating response from LLM provider %s: %s",
            config.LLM_PROVIDER,
            error,
        )

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

        if config.LLM_PROVIDER == "huggingface":
            logger.info("Attempting Hugging Face direct REST API fallback...")
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
                            return clean_response(generated)
                    logger.error("HF fallback failed with status %s: %s", res.status_code, res.text)
            except Exception as fallback_error:
                logger.error("Hugging Face REST API fallback error: %s", fallback_error)

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
    """Analiza imágenes y responde como Lulu."""
    client, model = _get_client_and_model()
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

    try:
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
                return cleaned
        return "*(No pude ver bien la imagen...)*"
    except Exception as error:
        logger.error("Error generating vision response: %s", error)
        return "*(No pude procesar la imagen, algo salió mal 😵)*"
