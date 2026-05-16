# agent/tools.py — Herramientas del agente de WhatsApp
# Generado por AgentKit

"""
Funciones de soporte para los casos de uso del agente:
FAQ, agendamiento GHL, calificación de leads, pedidos y soporte post-venta.
Incluye: llamada Twilio + folletos PDF + calendario GHL.
"""

import os
import base64
import yaml
import logging
import httpx
from datetime import datetime

logger = logging.getLogger("agentkit")


def cargar_info_negocio() -> dict:
    try:
        with open("config/business.yaml", "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        logger.error("config/business.yaml no encontrado")
        return {}


def obtener_horario() -> dict:
    """Retorna el horario de atención del negocio."""
    info = cargar_info_negocio()
    horario = info.get("negocio", {}).get("horario", "Lunes a Viernes 9am a 5pm")
    ahora = datetime.now()
    en_horario = ahora.weekday() < 5 and 9 <= ahora.hour < 17
    return {"horario": horario, "esta_abierto": en_horario}


def buscar_en_knowledge(consulta: str) -> str:
    """Busca información relevante en archivos de /knowledge."""
    knowledge_dir = "knowledge"
    if not os.path.exists(knowledge_dir):
        return "No hay archivos de conocimiento disponibles."

    resultados = []
    for archivo in os.listdir(knowledge_dir):
        if archivo.startswith(".") or not os.path.isfile(os.path.join(knowledge_dir, archivo)):
            continue
        try:
            with open(os.path.join(knowledge_dir, archivo), "r", encoding="utf-8") as f:
                contenido = f.read()
                if consulta.lower() in contenido.lower():
                    resultados.append(f"[{archivo}]: {contenido[:500]}")
        except (UnicodeDecodeError, IOError):
            continue

    return "\n---\n".join(resultados) if resultados else "No encontré información específica sobre eso."


# ═══════════════════════════════════════════════════
# CASO DE USO 1: FAQ
# buscar_en_knowledge() ya cubre este caso
# ═══════════════════════════════════════════════════


# ═══════════════════════════════════════════════════
# CASO DE USO 2: AGENDAR CITAS — GHL CALENDAR
# ═══════════════════════════════════════════════════

GHL_API_BASE = "https://services.leadconnectorhq.com"
GHL_CALENDAR_ID = os.getenv("GHL_CALENDAR_ID", "")   # Configurar en .env
GHL_TIMEZONE = "America/New_York"


def _ghl_headers() -> dict:
    return {
        "Authorization": f"Bearer {os.getenv('GHL_API_KEY', '')}",
        "Version": "2021-04-15",
        "Content-Type": "application/json",
    }


async def obtener_slots_disponibles(dias_adelante: int = 7) -> list[str]:
    """
    Obtiene los próximos slots disponibles en el calendario GHL configurado.
    Retorna lista de hasta 6 ISO datetime strings.
    """
    import time
    start_ms = int(time.time() * 1000)
    end_ms = int((time.time() + dias_adelante * 86400) * 1000)

    url = (
        f"{GHL_API_BASE}/calendars/{GHL_CALENDAR_ID}/free-slots"
        f"?startDate={start_ms}&endDate={end_ms}&timezone={GHL_TIMEZONE}"
    )
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            r = await client.get(url, headers=_ghl_headers())
            if r.status_code != 200:
                logger.error(f"GHL free-slots error {r.status_code}: {r.text[:200]}")
                return []
            data = r.json()
            slots: list[str] = []
            for fecha_data in data.values():
                for slot in fecha_data.get("slots", []):
                    slots.append(slot)
                    if len(slots) >= 6:
                        return slots
            return slots
        except Exception as e:
            logger.error(f"Error obteniendo slots GHL: {e}")
            return []


def formatear_slots_para_lucy(slots: list[str]) -> str:
    """Convierte ISO datetime list en texto amigable en español."""
    from datetime import datetime, timezone, timedelta
    if not slots:
        return "No hay horarios disponibles en este momento. El equipo se pondrá en contacto."

    DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]

    lineas = []
    for slot in slots[:4]:
        try:
            dt = datetime.fromisoformat(slot)
            hora = dt.strftime("%-I:%M %p").lower().replace("am", "am").replace("pm", "pm")
            dia = DIAS[dt.weekday()]
            mes = MESES[dt.month - 1]
            lineas.append(f"• {dia} {dt.day} de {mes} a las {hora}")
        except Exception:
            lineas.append(f"• {slot}")

    return "\n".join(lineas)


async def crear_contacto_ghl(nombre: str, email: str, telefono: str) -> str | None:
    """Crea o actualiza un contacto en GHL. Retorna el contactId."""
    location_id = os.getenv("GHL_LOCATION_ID_PRINCIPAL", "TU_LOCATION_ID_AQUI")
    url = f"{GHL_API_BASE}/contacts/"
    payload = {
        "locationId": location_id,
        "name": nombre,
        "email": email,
        "phone": telefono,
        "tags": [f"{os.getenv('AGENT_NAME', 'agente')}-WhatsApp"],
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            r = await client.post(url, json=payload, headers=_ghl_headers())
            if r.status_code in (200, 201):
                contact_id = r.json().get("contact", {}).get("id") or r.json().get("id")
                logger.info(f"Contacto GHL creado/actualizado: {contact_id} — {nombre}")
                return contact_id
            logger.error(f"Error creando contacto GHL {r.status_code}: {r.text[:200]}")
            return None
        except Exception as e:
            logger.error(f"Excepción creando contacto GHL: {e}")
            return None


async def agendar_cita_ghl(
    nombre: str,
    email: str,
    telefono: str,
    slot_iso: str,
) -> dict:
    """
    Agenda una cita en el calendario GHL configurado via GHL API.
    Retorna {"ok": True, "appointment_id": "..."} o {"ok": False, "error": "..."}.
    """
    from datetime import datetime, timedelta

    location_id = os.getenv("GHL_LOCATION_ID_PRINCIPAL", "TU_LOCATION_ID_AQUI")

    # Crear/actualizar contacto primero
    contact_id = await crear_contacto_ghl(nombre, email, telefono)

    # Calcular end_time (30 min después)
    try:
        dt_start = datetime.fromisoformat(slot_iso)
        dt_end = dt_start + timedelta(minutes=30)
        end_iso = dt_end.isoformat()
    except Exception:
        return {"ok": False, "error": "Formato de slot inválido"}

    payload = {
        "calendarId": GHL_CALENDAR_ID,
        "locationId": location_id,
        "title": f"Consulta — {nombre}",
        "appointmentStatus": "confirmed",
        "startTime": slot_iso,
        "endTime": end_iso,
        "timezone": GHL_TIMEZONE,
        "name": nombre,
        "email": email,
        "phone": telefono,
    }
    if contact_id:
        payload["contactId"] = contact_id

    url = f"{GHL_API_BASE}/calendars/events/appointments"
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            r = await client.post(url, json=payload, headers=_ghl_headers())
            if r.status_code in (200, 201):
                appt_id = r.json().get("id", "")
                logger.info(f"Cita GHL agendada: {appt_id} — {nombre} — {slot_iso}")
                return {"ok": True, "appointment_id": appt_id, "slot": slot_iso}
            logger.error(f"Error agendando cita GHL {r.status_code}: {r.text[:300]}")
            return {"ok": False, "error": f"GHL error {r.status_code}: {r.text[:100]}"}
        except Exception as e:
            logger.error(f"Excepción agendando cita GHL: {e}")
            return {"ok": False, "error": str(e)}


# ═══════════════════════════════════════════════════
# CASO DE USO 3: CALIFICACIÓN DE LEADS
# ═══════════════════════════════════════════════════

def obtener_preguntas_calificacion() -> list[str]:
    """Preguntas clave para calificar un lead de Marketing IA."""
    return [
        "¿Cuántos clientes o contactos manejas actualmente en tu negocio?",
        "¿Estás usando algún CRM o herramienta de gestión de clientes ahora mismo?",
        "¿Cuál es el mayor desafío que tienes con tu proceso de ventas o atención al cliente?",
        "¿Tienes un presupuesto aproximado en mente para esta solución?",
        "¿Cuándo necesitarías tener esto funcionando?",
    ]


def registrar_lead(nombre: str, empresa: str, interes: str, email: str = "") -> str:
    """Registra un lead calificado (en producción, conectar con GHL o CRM)."""
    logger.info(f"Lead registrado — {nombre} | {empresa} | Interés: {interes} | Email: {email}")
    return f"Lead de {nombre} registrado correctamente. El equipo de ventas lo atenderá pronto."


# ═══════════════════════════════════════════════════
# CASO DE USO 4: TOMAR PEDIDOS
# ═══════════════════════════════════════════════════

SERVICIOS_DISPONIBLES = {
    "agente_whatsapp": {
        "nombre": "Agente de IA para WhatsApp",
        "descripcion": "Bot inteligente con Claude AI integrado en tu WhatsApp Business",
    },
    "agente_llamadas": {
        "nombre": "Agente de IA para Llamadas",
        "descripcion": "Sistema de llamadas automatizadas con voz IA",
    },
    "crm_ghl": {
        "nombre": "CRM con GoHighLevel",
        "descripcion": "Implementación y configuración de GHL para tu negocio",
    },
    "crm_inteligente": {
        "nombre": "CRM Inteligente",
        "descripcion": "CRM personalizado con automatizaciones y IA integrada",
    },
    "consultoria": {
        "nombre": "Consultoría en Marketing IA",
        "descripcion": "Sesión estratégica para definir tu ruta de implementación de IA",
    },
}


def listar_servicios() -> str:
    """Retorna lista de servicios disponibles."""
    lineas = ["Servicios disponibles:\n"]
    for clave, servicio in SERVICIOS_DISPONIBLES.items():
        lineas.append(f"• {servicio['nombre']}: {servicio['descripcion']}")
    return "\n".join(lineas)


def registrar_pedido(nombre: str, servicio: str, email: str, detalles: str = "") -> str:
    """Registra un pedido de servicio (en producción, conectar con GHL o sistema de tickets)."""
    logger.info(f"Pedido — {nombre} | Servicio: {servicio} | Email: {email} | Detalles: {detalles}")
    return (
        f"Pedido registrado correctamente para {nombre}. "
        "El equipo de el propietario te contactará en las próximas 24 horas para coordinar los detalles."
    )


# ═══════════════════════════════════════════════════
# CASO DE USO 5: SOPORTE POST-VENTA
# ═══════════════════════════════════════════════════

def crear_ticket_soporte(nombre: str, servicio_contratado: str, problema: str) -> str:
    """Crea un ticket de soporte (en producción, conectar con Chatwoot o sistema de tickets)."""
    import uuid
    ticket_id = str(uuid.uuid4())[:8].upper()
    logger.info(f"Ticket #{ticket_id} — {nombre} | Servicio: {servicio_contratado} | Problema: {problema[:100]}")
    return (
        f"Ticket de soporte #{ticket_id} creado. "
        "Un especialista de el propietario revisará tu caso y te contactará pronto. "
        "Guarda este número de ticket para dar seguimiento."
    )


def escalar_a_humano(nombre: str, motivo: str) -> str:
    """Marca la conversación para escalación a agente humano."""
    logger.info(f"Escalación solicitada — Cliente: {nombre} | Motivo: {motivo}")
    return (
        "Entiendo, voy a conectarte con un miembro del equipo de el propietario. "
        "Alguien te contactará a la brevedad. "
        "¿Hay algo más que quieras que le comunique?"
    )


# ═══════════════════════════════════════════════════
# LLAMADAS OUTBOUND — TWILIO (al propietario y a prospectos)
# ═══════════════════════════════════════════════════

async def llamar_a_roy(nombre_cliente: str = "Cliente", motivo: str = "") -> bool:
    """
    Hace una llamada saliente via Twilio al número del propietario.
    El propietario recibe un aviso de voz cuando hay un cliente esperando en WhatsApp.
    Retorna True si la llamada fue iniciada con éxito.
    """
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    from_number = os.getenv("TWILIO_PHONE_NUMBER")
    to_number = os.getenv("TWILIO_TRANSFER_NUMBER", "")

    if not all([account_sid, auth_token, from_number]):
        logger.warning("Twilio no configurado — omitiendo llamada de alerta al propietario")
        return False

    motivo_texto = f"El cliente mencionó: {motivo}." if motivo else ""
    twiml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        '<Say language="es-MX">'
        f"Hola. Tienes un cliente en WhatsApp esperando hablar contigo. "
        f"El cliente es {nombre_cliente}. {motivo_texto} "
        "Por favor comunícate con él a la brevedad. Repito: "
        f"cliente {nombre_cliente} en WhatsApp esperando tu respuesta. Hasta luego."
        "</Say>"
        "</Response>"
    )

    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Calls.json"
    auth = base64.b64encode(f"{account_sid}:{auth_token}".encode()).decode()

    async with httpx.AsyncClient() as client:
        try:
            r = await client.post(
                url,
                data={"From": from_number, "To": to_number, "Twiml": twiml},
                headers={"Authorization": f"Basic {auth}"},
                timeout=15.0,
            )
            if r.status_code == 201:
                call_sid = r.json().get("sid", "")
                logger.info(f"Llamada Twilio iniciada a {to_number} — SID: {call_sid} — Cliente: {nombre_cliente}")
                return True
            else:
                logger.error(f"Error Twilio Calls: {r.status_code} — {r.text[:200]}")
                return False
        except Exception as e:
            logger.error(f"Excepción al llamar via Twilio: {e}")
            return False


async def llamar_prospecto(
    telefono: str,
    nombre: str = "Prospecto",
    mensaje_personalizado: str = "",
) -> bool:
    """
    Hace una llamada outbound via Twilio al número de un prospecto.
    El propietario puede disparar esto desde el endpoint /admin/llamar/{telefono}.
    El prospecto escucha un mensaje de voz del agente y se le pide que espere.
    """
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    from_number = os.getenv("TWILIO_PHONE_NUMBER")

    if not all([account_sid, auth_token, from_number]):
        logger.warning("Twilio no configurado — no se puede llamar al prospecto")
        return False

    agent_name = os.getenv("AGENT_NAME", "el equipo")
    msg_base = mensaje_personalizado or (
        f"Hola {nombre}, le habla el equipo de [NOMBRE_NEGOCIO]. "
        f"Le contactamos porque usted mostró interés en nuestros servicios. "
        "Por favor espere un momento, nos comunicaremos con usted a la brevedad. Muchas gracias."
    )

    twiml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        f'<Say language="es-MX">{msg_base}</Say>'
        "</Response>"
    )

    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Calls.json"
    auth = base64.b64encode(f"{account_sid}:{auth_token}".encode()).decode()

    async with httpx.AsyncClient() as client:
        try:
            r = await client.post(
                url,
                data={"From": from_number, "To": telefono, "Twiml": twiml},
                headers={"Authorization": f"Basic {auth}"},
                timeout=15.0,
            )
            if r.status_code == 201:
                logger.info(f"Llamada outbound a {telefono} iniciada — SID: {r.json().get('sid')}")
                return True
            logger.error(f"Error Twilio llamada prospecto {r.status_code}: {r.text[:200]}")
            return False
        except Exception as e:
            logger.error(f"Excepción llamando a prospecto: {e}")
            return False


# ═══════════════════════════════════════════════════
# FOLLETOS Y BROCHURES — GOOGLE DRIVE
# ═══════════════════════════════════════════════════

def obtener_folletos(negocio: str = "") -> list[dict]:
    """
    Retorna la lista de folletos/brochures disponibles del negocio.
    Si se especifica 'negocio' (marketing_ia | roma_insurance), filtra por ese negocio.
    """
    info = cargar_info_negocio()
    folletos = info.get("folletos", [])
    if negocio:
        folletos = [f for f in folletos if f.get("negocio", "") == negocio]
    return folletos
