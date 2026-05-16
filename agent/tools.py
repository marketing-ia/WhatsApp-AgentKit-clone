# agent/tools.py — Herramientas de Lucy para Roy Mota / Marketing IA
# Generado por AgentKit

"""
Funciones de soporte para los 5 casos de uso de Lucy:
FAQ, agendamiento, calificación de leads, pedidos y soporte post-venta.
Incluye: llamada Twilio a Roy + envío de folletos PDF.
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
# CASO DE USO 2: AGENDAR CITAS
# ═══════════════════════════════════════════════════

def obtener_info_para_cita() -> dict:
    """Retorna los datos que Lucy necesita recopilar para agendar una cita."""
    return {
        "campos_requeridos": ["nombre_completo", "email", "disponibilidad_horaria"],
        "horario_disponible": "Lunes a Viernes de 9:00 AM a 5:00 PM",
        "duracion_reunion": "30 minutos",
        "instrucciones": (
            "Lucy recopila: nombre completo, email y horario preferido. "
            "Luego confirma que el equipo de Roy Mota enviará un enlace de calendly o confirmación."
        ),
    }


def registrar_solicitud_cita(nombre: str, email: str, disponibilidad: str) -> str:
    """Registra una solicitud de cita (en producción, conectar con Calendly o GHL)."""
    logger.info(f"Solicitud de cita — Nombre: {nombre} | Email: {email} | Disponibilidad: {disponibilidad}")
    return (
        f"Solicitud registrada para {nombre}. "
        "El equipo de Roy Mota te contactará al email proporcionado para confirmar el horario."
    )


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
    lineas = ["Servicios de Roy Mota / Marketing IA:\n"]
    for clave, servicio in SERVICIOS_DISPONIBLES.items():
        lineas.append(f"• {servicio['nombre']}: {servicio['descripcion']}")
    return "\n".join(lineas)


def registrar_pedido(nombre: str, servicio: str, email: str, detalles: str = "") -> str:
    """Registra un pedido de servicio (en producción, conectar con GHL o sistema de tickets)."""
    logger.info(f"Pedido — {nombre} | Servicio: {servicio} | Email: {email} | Detalles: {detalles}")
    return (
        f"Pedido registrado correctamente para {nombre}. "
        "El equipo de Roy Mota te contactará en las próximas 24 horas para coordinar los detalles."
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
        "Un especialista de Roy Mota revisará tu caso y te contactará pronto. "
        "Guarda este número de ticket para dar seguimiento."
    )


def escalar_a_humano(nombre: str, motivo: str) -> str:
    """Marca la conversación para escalación a agente humano."""
    logger.info(f"Escalación solicitada — Cliente: {nombre} | Motivo: {motivo}")
    return (
        "Entiendo, voy a conectarte con un miembro del equipo de Roy Mota. "
        "Alguien te contactará a la brevedad. "
        "¿Hay algo más que quieras que le comunique?"
    )


# ═══════════════════════════════════════════════════
# TRANSFERENCIA DE LLAMADA — TWILIO
# ═══════════════════════════════════════════════════

async def llamar_a_roy(nombre_cliente: str = "Cliente", motivo: str = "") -> bool:
    """
    Hace una llamada saliente via Twilio al número de Roy.
    Roy recibe un aviso de voz diciéndole que hay un cliente esperando en WhatsApp.
    Retorna True si la llamada fue iniciada con éxito.
    """
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    from_number = os.getenv("TWILIO_PHONE_NUMBER")
    to_number = os.getenv("TWILIO_TRANSFER_NUMBER", "+14073838844")

    if not all([account_sid, auth_token, from_number]):
        logger.warning("Twilio no configurado — omitiendo llamada de alerta a Roy")
        return False

    motivo_texto = f"El cliente mencionó: {motivo}." if motivo else ""
    twiml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        '<Say language="es-MX">'
        f"Hola Roy. Tienes un cliente en WhatsApp esperando hablar contigo. "
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
