# tests/test_local.py — Simulador de chat en terminal
# Generado por AgentKit

"""
Prueba a Lucy sin necesitar WhatsApp ni Chatwoot.
Simula una conversación en la terminal directamente con Claude.
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.brain import generar_respuesta
from agent.memory import inicializar_db, guardar_mensaje, obtener_historial, limpiar_historial

CONVERSACION_TEST = "test-local-lucy-001"


async def main():
    await inicializar_db()

    print()
    print("=" * 60)
    print("   AgentKit — Test Local de Lucy")
    print("   Roy Mota / Marketing IA")
    print("=" * 60)
    print()
    print("  Escribe mensajes como si fueras un cliente.")
    print("  Comandos especiales:")
    print("    'limpiar'  — borra el historial de la conversación")
    print("    'salir'    — termina el test")
    print()
    print("-" * 60)
    print()

    while True:
        try:
            mensaje = input("Cliente: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\nTest finalizado.")
            break

        if not mensaje:
            continue

        if mensaje.lower() == "salir":
            print("\nTest finalizado. ¡Hasta luego!")
            break

        if mensaje.lower() == "limpiar":
            await limpiar_historial(CONVERSACION_TEST)
            print("[Historial borrado — nueva conversación]\n")
            continue

        # Obtener historial ANTES de guardar el mensaje actual
        historial = await obtener_historial(CONVERSACION_TEST)

        print("\nLucy: ", end="", flush=True)
        respuesta = await generar_respuesta(mensaje, historial)
        print(respuesta)
        print()

        # Guardar en memoria
        await guardar_mensaje(CONVERSACION_TEST, "user", mensaje)
        await guardar_mensaje(CONVERSACION_TEST, "assistant", respuesta)


if __name__ == "__main__":
    asyncio.run(main())
