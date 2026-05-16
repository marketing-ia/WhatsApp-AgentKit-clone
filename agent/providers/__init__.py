# agent/providers/__init__.py — Factory de proveedores
# Generado por AgentKit

"""
Selecciona el proveedor de WhatsApp según WHATSAPP_PROVIDER en .env.
"""

import os
from agent.providers.base import ProveedorWhatsApp


def obtener_proveedor() -> ProveedorWhatsApp:
    """Retorna el proveedor de WhatsApp configurado en .env."""
    proveedor = os.getenv("WHATSAPP_PROVIDER", "").lower()

    if not proveedor:
        raise ValueError("WHATSAPP_PROVIDER no configurado en .env. Usa: chatwoot, meta o twilio")

    if proveedor == "chatwoot":
        from agent.providers.chatwoot import ProveedorChatwoot
        return ProveedorChatwoot()
    elif proveedor == "meta":
        from agent.providers.meta import ProveedorMeta
        return ProveedorMeta()
    elif proveedor == "twilio":
        from agent.providers.twilio import ProveedorTwilio
        return ProveedorTwilio()
    else:
        raise ValueError(f"Proveedor no soportado: {proveedor}. Usa: chatwoot, meta o twilio")
