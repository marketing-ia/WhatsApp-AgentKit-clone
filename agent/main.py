# agent/main.py — Servidor FastAPI + Webhook de WhatsApp
# Generado por AgentKit

"""
Servidor principal del agente Lucy.
Recibe webhooks de Chatwoot, procesa con Claude y responde.
Incluye endpoints de admin para pausar/reanudar conversaciones (intervención humana).
"""

import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse
from dotenv import load_dotenv

from agent.brain import generar_respuesta
from agent.memory import (
    inicializar_db,
    guardar_mensaje,
    obtener_historial,
    pausar_conversacion,
    reanudar_conversacion,
    esta_pausada,
    listar_pausadas,
)
from agent.providers import obtener_proveedor
from agent.tools import llamar_a_roy, obtener_folletos

load_dotenv()

ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
log_level = logging.DEBUG if ENVIRONMENT == "development" else logging.INFO
logging.basicConfig(
    level=log_level,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("agentkit")

proveedor = obtener_proveedor()
PORT = int(os.getenv("PORT", 8000))

# Frases que el cliente puede escribir para pedir hablar con un humano o transferencia de llamada
FRASES_ESCALACION = [
    "hablar con humano", "hablar con una persona", "hablar con alguien",
    "quiero un agente", "agente humano", "persona real", "asesor",
    "con una persona", "con alguien del equipo", "quiero hablar con Roy",
    "quiero que me llamen", "que me llame", "llamada", "llamarme",
    "hablar por teléfono", "transfer", "transferir",
]

# Frases EXPLÍCITAS para solicitar folletos — solo cuando el cliente claramente lo pide
# IMPORTANTE: usar frases específicas, no palabras sueltas genéricas como "información" o "material"
FRASES_FOLLETO = [
    "envíame el folleto", "enviame el folleto",
    "mándame el folleto", "mandame el folleto",
    "envíame el brochure", "enviame el brochure",
    "quiero el folleto", "quiero un folleto",
    "quiero el brochure", "quiero un brochure",
    "puedes enviarme el folleto", "puedes mandarme el folleto",
    "envíame información en pdf", "enviame informacion en pdf",
    "mándame el pdf", "mandame el pdf",
    "envíame el pdf", "enviame el pdf",
    "quiero el pdf", "quiero ver el pdf",
    "tienes folleto", "tienes brochure",
    "me puedes enviar el folleto", "me puedes mandar el folleto",
    "me puedes enviar un folleto", "me puedes mandar un folleto",
]


def _solicita_humano(texto: str) -> bool:
    """Detecta si el cliente está pidiendo intervención humana o llamada."""
    texto_lower = texto.lower()
    return any(frase in texto_lower for frase in FRASES_ESCALACION)


def _solicita_folleto(texto: str) -> bool:
    """
    Detecta si el cliente está pidiendo EXPLÍCITAMENTE un folleto o PDF.
    Usa frases completas para evitar falsos positivos en conversaciones normales.
    """
    texto_lower = texto.lower()
    return any(frase in texto_lower for frase in FRASES_FOLLETO)


def _detectar_negocio(texto: str) -> str:
    """Detecta a qué negocio se refiere el mensaje para filtrar el folleto correcto."""
    texto_lower = texto.lower()
    palabras_roma = ["seguro", "salud", "vida", "iul", "póliza", "poliza", "cobertura", "prima", "roma"]
    palabras_kora = ["marketing", "crm", "automatización", "automatizacion", "kora", "agente ia", "landing", "ghl"]
    if any(p in texto_lower for p in palabras_roma):
        return "roma_insurance"
    if any(p in texto_lower for p in palabras_kora):
        return "marketing_ia"
    return ""  # no determinado — enviar todos


@asynccontextmanager
async def lifespan(app: FastAPI):
    await inicializar_db()
    logger.info("Base de datos inicializada")
    logger.info(f"Proveedor activo: {proveedor.__class__.__name__}")
    logger.info(f"Servidor Lucy listo en puerto {PORT}")
    yield


app = FastAPI(
    title="Lucy — Agente IA de Roy Mota / Marketing IA",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/")
async def health_check():
    return {"status": "ok", "agente": "Lucy", "negocio": "Roy Mota / Marketing IA"}


@app.get("/webhook")
async def webhook_verificacion(request: Request):
    resultado = await proveedor.validar_webhook(request)
    if resultado is not None:
        return PlainTextResponse(str(resultado))
    return {"status": "ok"}


@app.post("/webhook")
async def webhook_handler(request: Request):
    """
    Recibe mensajes entrantes via el proveedor configurado.
    Genera respuesta con Claude y la envía de vuelta al cliente.
    Si el cliente pide un humano, pausa a Lucy y notifica.
    """
    try:
        mensajes = await proveedor.parsear_webhook(request)

        for msg in mensajes:
            if msg.es_propio or not msg.texto:
                continue

            conversation_id = msg.telefono
            logger.info(f"[{conversation_id}] Mensaje: {msg.texto[:80]}")

            # Verificar si la conversación está pausada por intervención humana
            if await esta_pausada(conversation_id):
                logger.info(f"[{conversation_id}] Pausada — Lucy no responde")
                continue

            # Detectar si el cliente solicita hablar con un humano / transferencia de llamada
            if _solicita_humano(msg.texto):
                await pausar_conversacion(conversation_id, motivo="cliente solicitó humano")
                aviso = (
                    "Claro, le aviso a Roy en este momento para que te contacte 🙏 "
                    "Él te llamará o escribirá a la brevedad. "
                    "También puedes llamar directamente al +1 (407) 383-8844."
                )
                await guardar_mensaje(conversation_id, "user", msg.texto)
                await guardar_mensaje(conversation_id, "assistant", aviso)
                await proveedor.enviar_mensaje(conversation_id, aviso)
                # Notificar a Roy via llamada Twilio
                await llamar_a_roy(nombre_cliente="Cliente en WhatsApp", motivo=msg.texto[:100])
                logger.info(f"[{conversation_id}] Escalada a humano — llamada Twilio activada — Lucy pausada")
                continue

            # Detectar si el cliente solicita un folleto / brochure
            if _solicita_folleto(msg.texto):
                negocio = _detectar_negocio(msg.texto)
                folletos = obtener_folletos(negocio)

                await guardar_mensaje(conversation_id, "user", msg.texto)

                if not folletos:
                    # No hay folletos configurados → respuesta genérica
                    aviso_folleto = (
                        "Con gusto te comparto nuestro material informativo 📄 "
                        "Para recibirlo, escríbenos a info@romainsurancegroup.com "
                        "o llama al +1 (407) 383-8844."
                    )
                    await guardar_mensaje(conversation_id, "assistant", aviso_folleto)
                    await proveedor.enviar_mensaje(conversation_id, aviso_folleto)
                    logger.info(f"[{conversation_id}] Solicitud de folleto — sin folletos configurados")
                    continue

                aviso_folleto = "Con gusto te envío nuestro material 📄 Dame un momento..."
                await guardar_mensaje(conversation_id, "assistant", aviso_folleto)
                await proveedor.enviar_mensaje(conversation_id, aviso_folleto)

                # Enviar cada folleto disponible
                for folleto in folletos:
                    url_pdf = folleto.get("url", "").strip()
                    if not url_pdf:
                        # Sin URL configurada → texto con info de contacto
                        await proveedor.enviar_mensaje(
                            conversation_id,
                            f"📄 *{folleto['nombre']}*\n{folleto['descripcion']}\n\n"
                            "Para recibir este material, escríbenos a info@romainsurancegroup.com "
                            "o llama al +1 (407) 383-8844.",
                        )
                        logger.info(f"[{conversation_id}] Folleto sin URL — mensaje alternativo: {folleto['nombre']}")
                        continue

                    # Enviar el PDF via Evolution API
                    enviado = await proveedor.enviar_documento(
                        conversation_id,
                        url_pdf,
                        folleto.get("archivo", "folleto.pdf"),
                        folleto.get("descripcion", ""),
                    )
                    if not enviado:
                        # Fallback: enviar el link como texto
                        await proveedor.enviar_mensaje(
                            conversation_id,
                            f"📄 *{folleto['nombre']}*\n{folleto['descripcion']}\n\n"
                            f"Puedes verlo aquí: {url_pdf}",
                        )
                    logger.info(f"[{conversation_id}] Folleto procesado: {folleto['nombre']} — enviado={enviado}")

                continue

            # Flujo normal: obtener historial → generar respuesta → guardar → enviar
            historial = await obtener_historial(conversation_id)
            respuesta = await generar_respuesta(msg.texto, historial)

            await guardar_mensaje(conversation_id, "user", msg.texto)
            await guardar_mensaje(conversation_id, "assistant", respuesta)

            exito = await proveedor.enviar_mensaje(conversation_id, respuesta)
            if exito:
                logger.info(f"[{conversation_id}] Respuesta enviada: {respuesta[:80]}")
            else:
                logger.error(f"[{conversation_id}] Falló el envío de respuesta")

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Error en webhook: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ── Endpoints de administración (intervención humana) ─────────────────────────

@app.post("/admin/pausa/{conversation_id}")
async def admin_pausar(conversation_id: str, motivo: str = "intervención manual"):
    """
    Pausa a Lucy para una conversación específica.
    Úsalo desde Chatwoot o cualquier herramienta cuando un humano toma el control.

    Ejemplo: POST /admin/pausa/123?motivo=agente+tomó+control
    """
    await pausar_conversacion(conversation_id, motivo=motivo)
    logger.info(f"[{conversation_id}] Pausada manualmente — motivo: {motivo}")
    return {
        "status": "pausada",
        "conversation_id": conversation_id,
        "motivo": motivo,
        "mensaje": "Lucy dejará de responder en esta conversación.",
    }


@app.post("/admin/reanudar/{conversation_id}")
async def admin_reanudar(conversation_id: str):
    """
    Reactiva a Lucy en una conversación pausada.
    Úsalo cuando el agente humano termina y quiere devolver el control a Lucy.

    Ejemplo: POST /admin/reanudar/123
    """
    reanudada = await reanudar_conversacion(conversation_id)
    if not reanudada:
        raise HTTPException(status_code=404, detail="Conversación no encontrada o ya activa")
    logger.info(f"[{conversation_id}] Reanudada — Lucy vuelve a responder")
    return {
        "status": "reanudada",
        "conversation_id": conversation_id,
        "mensaje": "Lucy volverá a responder en esta conversación.",
    }


@app.get("/admin/pausadas")
async def admin_listar_pausadas():
    """Lista todas las conversaciones donde Lucy está pausada actualmente."""
    pausadas = await listar_pausadas()
    return {
        "total": len(pausadas),
        "conversaciones": pausadas,
    }
