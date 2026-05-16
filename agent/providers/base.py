# agent/providers/base.py — Interfaz base para proveedores de WhatsApp
# Generado por AgentKit

"""
Define el contrato común que todos los proveedores deben cumplir.
Permite cambiar de proveedor sin modificar el resto del sistema.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from fastapi import Request


@dataclass
class MensajeEntrante:
    """Mensaje normalizado — mismo formato independientemente del proveedor."""
    telefono: str               # Número del remitente (o conversation_id para Chatwoot)
    texto: str                  # Contenido del mensaje (o transcripción de audio)
    mensaje_id: str             # ID único del mensaje
    es_propio: bool             # True si lo envió el agente (se ignora)
    extra: dict = field(default_factory=dict)
    imagen_b64: str | None = None       # Imagen en base64 (para fotos recibidas)
    imagen_mime: str | None = None      # MIME type de la imagen (image/jpeg, etc.)


class ProveedorWhatsApp(ABC):
    """Interfaz que cada proveedor de WhatsApp debe implementar."""

    @abstractmethod
    async def parsear_webhook(self, request: Request) -> list[MensajeEntrante]:
        """Extrae y normaliza mensajes del payload del webhook."""
        ...

    @abstractmethod
    async def enviar_mensaje(self, destinatario: str, mensaje: str) -> bool:
        """Envía un mensaje de texto. Retorna True si fue exitoso."""
        ...

    async def validar_webhook(self, request: Request) -> dict | int | None:
        """Verificación GET del webhook (solo algunos proveedores la requieren)."""
        return None

    async def enviar_documento(
        self,
        destinatario: str,
        url: str,
        nombre_archivo: str,
        caption: str = "",
    ) -> bool:
        """
        Envía un documento (PDF) al destinatario.
        Los proveedores que soportan documentos deben sobrescribir este método.
        """
        return False
