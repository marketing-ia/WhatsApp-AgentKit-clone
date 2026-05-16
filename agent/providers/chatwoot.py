# agent/providers/chatwoot.py — Adaptador para Chatwoot + Evolution API
# Generado por AgentKit

"""
Proveedor de WhatsApp usando Chatwoot como bandeja de entrada (Opción B).
Chatwoot recibe mensajes de WhatsApp via Evolution API y dispara webhooks aquí.
Lucy responde enviando mensajes via la API REST de Chatwoot.

Flujo:
  Cliente → WhatsApp → Evolution API → Chatwoot → webhook → Lucy → Chatwoot API → Cliente
"""

import os
import base64
import logging
import httpx
from fastapi import Request
from agent.providers.base import ProveedorWhatsApp, MensajeEntrante

logger = logging.getLogger("agentkit")


class ProveedorChatwoot(ProveedorWhatsApp):
    """Proveedor que recibe webhooks de Chatwoot y responde via su API."""

    def __init__(self):
        self.chatwoot_url = os.getenv("CHATWOOT_URL", "").rstrip("/")
        self.api_token = os.getenv("CHATWOOT_API_TOKEN")
        self.account_id = os.getenv("CHATWOOT_ACCOUNT_ID", "1")
        self.inbox_id = int(os.getenv("CHATWOOT_INBOX_ID", "0"))

    async def parsear_webhook(self, request: Request) -> list[MensajeEntrante]:
        """
        Parsea el payload de Chatwoot.
        Solo procesa mensajes entrantes (message_type=0) de conversaciones sin agente asignado.
        Usa el conversation_id como identificador único para la memoria del agente.
        """
        try:
            body = await request.json()
        except Exception:
            logger.warning("Webhook de Chatwoot con body inválido")
            return []

        evento = body.get("event")

        # Solo procesamos mensajes nuevos
        if evento != "message_created":
            return []

        # Solo mensajes entrantes del cliente (message_type 0)
        message_type = body.get("message_type")
        if message_type != 0:
            return []

        # Datos de la conversación
        conversacion = body.get("conversation", {})
        conversation_id = str(conversacion.get("id", ""))

        if not conversation_id:
            logger.warning("Webhook sin conversation_id — ignorado")
            return []

        # Ignorar mensajes de grupos de WhatsApp (@g.us) — Lucy solo atiende mensajes directos
        sender = body.get("sender", {})
        sender_identifier = sender.get("identifier", "") or ""
        if "@g.us" in sender_identifier:
            logger.debug(f"Mensaje de grupo ignorado — JID: {sender_identifier}")
            return []

        # Ignorar si no hay contenido de texto
        contenido = body.get("content", "").strip()
        if not contenido:
            return []

        # Si hay un agente humano asignado, Lucy no interrumpe
        assignee = conversacion.get("assignee")
        if assignee and assignee.get("id"):
            logger.info(f"Conversación {conversation_id} asignada a humano — Lucy no responde")
            return []

        # Si la conversación tiene la etiqueta "paused", Lucy no responde
        etiquetas = conversacion.get("labels", [])
        if "paused" in etiquetas or "humano" in etiquetas:
            logger.info(f"Conversación {conversation_id} etiquetada como pausada — Lucy no responde")
            return []

        # Verificar que es del inbox correcto
        inbox_id = conversacion.get("inbox_id")
        if self.inbox_id and inbox_id != self.inbox_id:
            logger.debug(f"Mensaje de inbox {inbox_id} ignorado (solo proceso {self.inbox_id})")
            return []

        nombre_remitente = sender.get("name", "Cliente")
        mensaje_id = str(body.get("id", ""))

        # Procesar adjuntos: audio → transcripción, imagen → base64
        adjuntos = body.get("attachments", []) or []
        imagen_b64 = None
        imagen_mime = None
        es_audio = False

        for adj in adjuntos:
            file_type = adj.get("file_type", "")
            data_url = adj.get("data_url", "") or ""

            if file_type in ("audio", "voice") and not contenido:
                transcripcion = await self._transcribir_audio(data_url)
                if transcripcion:
                    contenido = transcripcion  # Solo Lucy ve este texto; el historial guardará [Nota de voz]
                    es_audio = True
                    logger.info(f"Audio transcrito ({len(transcripcion)} chars): {transcripcion[:60]}")

            elif file_type == "image" and not imagen_b64:
                b64, mime = await self._descargar_imagen_b64(data_url)
                if b64:
                    imagen_b64 = b64
                    imagen_mime = mime
                    if not contenido:
                        contenido = "[Foto recibida]"
                    logger.info(f"Imagen recibida ({mime}), {len(b64)} chars b64")

        if not contenido:
            return []

        logger.info(f"Mensaje de '{nombre_remitente}' en conversación {conversation_id}: {contenido[:50]}")

        return [MensajeEntrante(
            telefono=conversation_id,
            texto=contenido,
            mensaje_id=mensaje_id,
            es_propio=False,
            imagen_b64=imagen_b64,
            imagen_mime=imagen_mime,
            extra={
                "conversation_id": conversation_id,
                "nombre_remitente": nombre_remitente,
                "inbox_id": inbox_id,
                "es_audio": es_audio,
            }
        )]

    async def _transcribir_audio(self, url: str) -> str | None:
        """
        Descarga un archivo de audio desde Chatwoot y lo transcribe con OpenAI Whisper.
        Requiere OPENAI_API_KEY. Retorna el texto transcrito o None si falla.
        """
        openai_key = os.getenv("OPENAI_API_KEY")
        if not openai_key:
            logger.warning("OPENAI_API_KEY no configurado — no se puede transcribir audio")
            return None
        if not url:
            return None

        try:
            # Descargar audio
            headers_cw = {"api_access_token": self.api_token} if self.api_token else {}
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.get(url, headers=headers_cw, follow_redirects=True)
                if r.status_code != 200:
                    logger.error(f"Error descargando audio: {r.status_code}")
                    return None
                audio_bytes = r.content
                content_type = r.headers.get("content-type", "audio/ogg")

            # Determinar extensión
            ext_map = {
                "audio/ogg": "ogg", "audio/opus": "ogg",
                "audio/mpeg": "mp3", "audio/mp4": "m4a",
                "audio/webm": "webm", "audio/wav": "wav",
            }
            ext = ext_map.get(content_type.split(";")[0].strip(), "ogg")

            # Transcribir con OpenAI Whisper
            from openai import AsyncOpenAI
            oai = AsyncOpenAI(api_key=openai_key)
            import io
            audio_file = io.BytesIO(audio_bytes)
            audio_file.name = f"audio.{ext}"

            transcripcion = await oai.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language="es",
            )
            return transcripcion.text.strip()

        except Exception as e:
            logger.error(f"Error transcribiendo audio: {e}")
            return None

    async def _descargar_imagen_b64(self, url: str) -> tuple[str | None, str]:
        """
        Descarga una imagen y la convierte a base64 para Claude Vision.
        Retorna (base64_string, mime_type) o (None, '').
        """
        if not url:
            return None, ""
        try:
            headers_cw = {"api_access_token": self.api_token} if self.api_token else {}
            async with httpx.AsyncClient(timeout=20.0) as client:
                r = await client.get(url, headers=headers_cw, follow_redirects=True)
                if r.status_code != 200:
                    return None, ""
                mime = r.headers.get("content-type", "image/jpeg").split(";")[0].strip()
                if not mime.startswith("image/"):
                    mime = "image/jpeg"
                b64 = base64.b64encode(r.content).decode()
                return b64, mime
        except Exception as e:
            logger.error(f"Error descargando imagen: {e}")
            return None, ""

    async def _obtener_telefono_contacto(self, conversation_id: str) -> str | None:
        """
        Obtiene el número de teléfono del contacto via la API de Chatwoot.
        Necesario para enviar documentos via Evolution API directamente.
        """
        if not self.chatwoot_url or not self.api_token:
            return None
        url = f"{self.chatwoot_url}/api/v1/accounts/{self.account_id}/conversations/{conversation_id}"
        headers = {"api_access_token": self.api_token}
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                r = await client.get(url, headers=headers)
                if r.status_code == 200:
                    data = r.json()
                    phone = data.get("meta", {}).get("sender", {}).get("phone_number", "")
                    if phone:
                        # Normaliza: quitar +, espacios y guiones
                        return phone.replace("+", "").replace(" ", "").replace("-", "")
            except Exception as e:
                logger.error(f"Error obteniendo teléfono de conversación {conversation_id}: {e}")
        return None

    async def enviar_documento(
        self,
        destinatario: str,
        url: str,
        nombre_archivo: str,
        caption: str = "",
    ) -> bool:
        """
        Envía un PDF via Evolution API usando el teléfono real del contacto.
        El parámetro 'destinatario' es el conversation_id de Chatwoot.
        """
        evolution_url = os.getenv("EVOLUTION_API_URL", "").rstrip("/")
        evolution_key = os.getenv("EVOLUTION_API_KEY")
        evolution_instance = os.getenv("EVOLUTION_INSTANCE", "agentkit")

        if not evolution_url or not evolution_key:
            logger.warning("EVOLUTION_API_URL o EVOLUTION_API_KEY no configurados — no se puede enviar documento")
            return False

        phone = await self._obtener_telefono_contacto(destinatario)
        if not phone:
            logger.warning(f"No se encontró teléfono para conversación {destinatario} — no se puede enviar documento")
            return False

        api_url = f"{evolution_url}/message/sendMedia/{evolution_instance}"
        headers = {"apikey": evolution_key, "Content-Type": "application/json"}
        payload = {
            "number": phone,
            "mediatype": "document",
            "mimetype": "application/pdf",
            "media": url,
            "caption": caption,
            "fileName": nombre_archivo,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                r = await client.post(api_url, json=payload, headers=headers)
                if r.status_code in (200, 201):
                    logger.info(f"Documento '{nombre_archivo}' enviado a {phone} via Evolution")
                    return True
                else:
                    logger.error(f"Error Evolution sendMedia {r.status_code}: {r.text[:200]}")
                    return False
            except Exception as e:
                logger.error(f"Error enviando documento via Evolution: {e}")
                return False

    async def enviar_mensaje(self, destinatario: str, mensaje: str) -> bool:
        """
        Envía un mensaje a una conversación de Chatwoot.
        El parámetro 'destinatario' es el conversation_id.
        """
        if not self.chatwoot_url or not self.api_token:
            logger.error("CHATWOOT_URL o CHATWOOT_API_TOKEN no configurados")
            return False

        conversation_id = destinatario
        url = f"{self.chatwoot_url}/api/v1/accounts/{self.account_id}/conversations/{conversation_id}/messages"
        headers = {
            "api_access_token": self.api_token,
            "Content-Type": "application/json",
        }
        payload = {
            "content": mensaje,
            "message_type": "outgoing",
            "private": False,
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                r = await client.post(url, json=payload, headers=headers)
                if r.status_code not in (200, 201):
                    logger.error(f"Error Chatwoot API {r.status_code}: {r.text[:200]}")
                    return False
                logger.info(f"Mensaje enviado a conversación {conversation_id}")
                return True
            except httpx.RequestError as e:
                logger.error(f"Error de conexión con Chatwoot: {e}")
                return False
