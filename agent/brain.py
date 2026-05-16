# agent/brain.py — Cerebro de Lucy: conexión con Claude API
# Generado por AgentKit

"""
Genera respuestas usando Claude AI.
Lee el system prompt desde config/prompts.yaml.
"""

import os
import yaml
import logging
from anthropic import AsyncAnthropic
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("agentkit")

client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def _cargar_config() -> dict:
    try:
        with open("config/prompts.yaml", "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        logger.error("config/prompts.yaml no encontrado")
        return {}


def cargar_system_prompt() -> str:
    return _cargar_config().get(
        "system_prompt",
        "Eres un asistente virtual. Responde en español con calidez."
    )


def obtener_mensaje_error() -> str:
    return _cargar_config().get(
        "error_message",
        "Lo siento, estoy teniendo un pequeño problema técnico. Por favor intenta de nuevo en unos minutos."
    )


def obtener_mensaje_fallback() -> str:
    return _cargar_config().get(
        "fallback_message",
        "Disculpa, no entendí bien tu mensaje. ¿Podrías contarme un poco más sobre lo que necesitas? 🤍"
    )


async def generar_respuesta(
    mensaje: str,
    historial: list[dict],
    imagen_b64: str | None = None,
    imagen_mime: str | None = None,
    contexto_extra: str | None = None,
) -> str:
    """
    Genera una respuesta usando Claude API.

    Args:
        mensaje: El mensaje nuevo del cliente (texto o transcripción de voz)
        historial: Mensajes anteriores de esta conversación
        imagen_b64: Imagen en base64 (si el cliente mandó una foto)
        imagen_mime: MIME type de la imagen
        contexto_extra: Contexto adicional a inyectar (ej: slots disponibles)

    Returns:
        Respuesta generada por Claude
    """
    if not mensaje or len(mensaje.strip()) < 2:
        return obtener_mensaje_fallback()

    system_prompt = cargar_system_prompt()
    if contexto_extra:
        system_prompt = f"{system_prompt}\n\n---\n{contexto_extra}"

    mensajes = [
        {"role": m["role"], "content": m["content"]}
        for m in historial
    ]

    # Construir el contenido del mensaje actual (texto + imagen opcional)
    if imagen_b64 and imagen_mime:
        contenido_usuario = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": imagen_mime,
                    "data": imagen_b64,
                },
            },
            {"type": "text", "text": mensaje or "¿Qué ves en esta imagen?"},
        ]
    else:
        contenido_usuario = mensaje

    mensajes.append({"role": "user", "content": contenido_usuario})

    try:
        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=system_prompt,
            messages=mensajes,
        )

        respuesta = response.content[0].text
        logger.info(
            f"Claude respondió ({response.usage.input_tokens} in / {response.usage.output_tokens} out tokens)"
        )
        return respuesta

    except Exception as e:
        logger.error(f"Error Claude API: {e}")
        return obtener_mensaje_error()
