# agent/main.py — Servidor FastAPI + Webhook de WhatsApp
# Generado por AgentKit

"""
Servidor principal del agente de WhatsApp.
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
from agent.tools import (
    llamar_a_roy, obtener_folletos, llamar_prospecto,
    obtener_slots_disponibles, formatear_slots_para_lucy, agendar_cita_ghl,
)

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
    "con una persona", "con alguien del equipo", "quiero hablar con alguien",
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


# Palabras clave para detectar intención de agendar cita
PALABRAS_CITA = [
    "agendar", "cita", "reunión", "reunion", "appointment", "horario disponible",
    "cuándo podemos", "cuando podemos", "qué horarios", "que horarios",
    "disponibilidad", "me puedo reunir", "podemos hablar", "quiero una cita",
    "quiero una reunión", "quiero una reunion", "programar",
]

# Palabras clave de cotización de seguros (inyecta el URL proactivamente)
PALABRAS_COTIZACION = [
    "cotización", "cotizacion", "cotizar", "cuánto cuesta", "cuanto cuesta",
    "precio del seguro", "cuánto vale", "cuanto vale", "costo del plan",
    "cuánto es", "cuanto es el seguro", "quiero saber el precio",
]


def _solicita_humano(texto: str) -> bool:
    """Detecta si el cliente está pidiendo intervención humana o llamada."""
    texto_lower = texto.lower()
    return any(frase in texto_lower for frase in FRASES_ESCALACION)


def _quiere_cita(texto: str) -> bool:
    """Detecta si el cliente quiere agendar una cita."""
    texto_lower = texto.lower()
    return any(p in texto_lower for p in PALABRAS_CITA)


def _quiere_cotizacion(texto: str) -> bool:
    """Detecta si el cliente está preguntando por precios o cotizaciones de seguro."""
    texto_lower = texto.lower()
    return any(p in texto_lower for p in PALABRAS_COTIZACION)


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
    logger.info(f"Servidor AgentKit listo en puerto {PORT}")
    yield


app = FastAPI(
    title="AgentKit — Agente IA de WhatsApp",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/")
async def health_check():
    agente_nombre = os.getenv("AGENT_NAME", "Agente")
    return {"status": "ok", "agente": agente_nombre, "version": "3.0"}


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
                _tel = os.getenv("TRANSFER_NUMBER_DISPLAY", "")
                _tel_txt = f" También puedes llamar directamente al {_tel}." if _tel else ""
                aviso = (
                    f"Claro, le aviso a nuestro equipo en este momento para que te contacte 🙏 "
                    f"Alguien te llamará o escribirá a la brevedad.{_tel_txt}"
                )
                await guardar_mensaje(conversation_id, "user", msg.texto)
                await guardar_mensaje(conversation_id, "assistant", aviso)
                await proveedor.enviar_mensaje(conversation_id, aviso)
                # Notificar al propietario via llamada Twilio
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
                        "Para recibirlo, escríbenos a info@tunegocio.com"
                        "o llama al tu número de contacto."
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
                            "Para recibir este material, escríbenos a info@tunegocio.com"
                            "o llama al tu número de contacto.",
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

            # ── Flujo normal: historial → contexto → Claude → guardar → enviar ──
            historial = await obtener_historial(conversation_id)
            contexto_extra = None

            # Inyectar slots disponibles cuando detectamos intención de cita
            if _quiere_cita(msg.texto):
                slots = await obtener_slots_disponibles(dias_adelante=7)
                if slots:
                    texto_slots = formatear_slots_para_lucy(slots)
                    contexto_extra = (
                        f"HORARIOS DISPONIBLES PARA CITA ({os.getenv('AGENT_NAME', 'el negocio')}):\n{texto_slots}\n"
                        "Preséntale estos horarios al cliente para que elija uno. "
                        "Cuando confirme nombre, email, teléfono y horario, incluye al FINAL de tu respuesta "
                        "EXACTAMENTE este marcador (sin modificar el formato):\n"
                        '[BOOKING:{"nombre":"NOMBRE","email":"EMAIL","telefono":"TEL","slot":"SLOT_ISO"}]'
                    )
                    logger.info(f"[{conversation_id}] Slots inyectados: {len(slots)} disponibles")

            # Inyectar link de cotización cuando preguntan por precios de seguro
            if _quiere_cotizacion(msg.texto) and not contexto_extra:
                quote_url = os.getenv("QUOTE_URL", "https://tucotizacion.com")
                contexto_extra = (
                    "El cliente está preguntando por precios o cotizaciones. "
                    "Recuérdale que la cotización es gratuita y sin compromiso. "
                    f"Incluye en tu respuesta el link directo: {quote_url}"
                )

            respuesta = await generar_respuesta(
                msg.texto,
                historial,
                imagen_b64=msg.imagen_b64,
                imagen_mime=msg.imagen_mime,
                contexto_extra=contexto_extra,
            )

            # Detectar marcador de reserva [BOOKING:{...}] en la respuesta de Lucy
            import re, json as _json
            booking_match = re.search(r'\[BOOKING:(\{[^}]+\})\]', respuesta, re.DOTALL)
            if booking_match:
                try:
                    booking_data = _json.loads(booking_match.group(1))
                    resultado = await agendar_cita_ghl(
                        nombre=booking_data.get("nombre", ""),
                        email=booking_data.get("email", ""),
                        telefono=booking_data.get("telefono", ""),
                        slot_iso=booking_data.get("slot", ""),
                    )
                    if resultado.get("ok"):
                        from datetime import datetime
                        try:
                            dt = datetime.fromisoformat(booking_data["slot"])
                            DIAS = ["lunes","martes","miércoles","jueves","viernes","sábado","domingo"]
                            MESES = ["enero","febrero","marzo","abril","mayo","junio","julio","agosto","septiembre","octubre","noviembre","diciembre"]
                            fecha_texto = f"{DIAS[dt.weekday()]} {dt.day} de {MESES[dt.month-1]} a las {dt.strftime('%-I:%M %p').lower()}"
                        except Exception:
                            fecha_texto = booking_data.get("slot", "")
                        confirmacion = f"¡Cita agendada! el {fecha_texto}. Recibirás un email de confirmación. ¡Nos vemos! 📅"
                    else:
                        confirmacion = "Hubo un problema al agendar la cita. Por favor llama a nuestro número de contacto y lo coordinamos en seguida."
                    # Reemplazar el marcador con la confirmación
                    respuesta = re.sub(r'\[BOOKING:[^\]]+\]', confirmacion, respuesta)
                    logger.info(f"[{conversation_id}] Cita GHL agendada — resultado: {resultado}")
                except Exception as e:
                    respuesta = re.sub(r'\[BOOKING:[^\]]+\]', '', respuesta)
                    logger.error(f"[{conversation_id}] Error procesando BOOKING: {e}")

            # Guardar en historial: audio → "[Nota de voz]" (la transcripción no se persiste ni se muestra)
            texto_historial = "[Nota de voz]" if msg.extra.get("es_audio") else msg.texto
            await guardar_mensaje(conversation_id, "user", texto_historial)
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


@app.post("/admin/llamar/{telefono}")
async def admin_llamar_prospecto(
    telefono: str,
    nombre: str = "Prospecto",
    motivo: str = "",
):
    """
    Dispara una llamada Twilio outbound al teléfono del prospecto.
    Dispara desde n8n, Postman o cualquier herramienta.

    Ejemplo: POST /admin/llamar/+15551234567?nombre=Juan+Garcia
    El prospecto recibe una llamada de voz avisando que el equipo lo contactará.
    """
    # Normalizar formato: +15551234567 o 15551234567
    tel = telefono if telefono.startswith("+") else f"+{telefono}"
    exito = await llamar_prospecto(tel, nombre=nombre, mensaje_personalizado=motivo)
    if exito:
        logger.info(f"Llamada outbound iniciada a {tel} — {nombre}")
        return {
            "status": "llamando",
            "telefono": tel,
            "nombre": nombre,
            "mensaje": f"Llamada a {nombre} ({tel}) iniciada via Twilio.",
        }
    return {
        "status": "error",
        "telefono": tel,
        "mensaje": "No se pudo iniciar la llamada. Verifica las credenciales de Twilio.",
    }
