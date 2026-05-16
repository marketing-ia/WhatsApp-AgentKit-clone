# agent/memory.py — Memoria de conversaciones con SQLite
# Generado por AgentKit

"""
Guarda y recupera el historial de conversaciones por ID de conversación.
También gestiona el estado de pausa por conversación (intervención humana).
Usa SQLite local (desarrollo) o PostgreSQL (producción en Railway).
"""

import os
from datetime import datetime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Text, DateTime, select, Integer, Boolean
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./agentkit.db")

if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Mensaje(Base):
    __tablename__ = "mensajes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telefono: Mapped[str] = mapped_column(String(100), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ConversacionPausada(Base):
    """Registra conversaciones donde un humano tomó el control."""
    __tablename__ = "conversaciones_pausadas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversacion_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    pausada: Mapped[bool] = mapped_column(Boolean, default=True)
    motivo: Mapped[str] = mapped_column(String(200), default="intervención humana")
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


async def inicializar_db():
    """Crea las tablas si no existen."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def guardar_mensaje(conversacion_id: str, role: str, content: str):
    """Guarda un mensaje en el historial."""
    async with async_session() as session:
        mensaje = Mensaje(
            telefono=conversacion_id,
            role=role,
            content=content,
            timestamp=datetime.utcnow(),
        )
        session.add(mensaje)
        await session.commit()


async def obtener_historial(conversacion_id: str, limite: int = 20) -> list[dict]:
    """Recupera los últimos N mensajes en orden cronológico."""
    async with async_session() as session:
        query = (
            select(Mensaje)
            .where(Mensaje.telefono == conversacion_id)
            .order_by(Mensaje.timestamp.desc())
            .limit(limite)
        )
        result = await session.execute(query)
        mensajes = result.scalars().all()
        mensajes.reverse()
        return [{"role": m.role, "content": m.content} for m in mensajes]


async def limpiar_historial(conversacion_id: str):
    """Borra todo el historial de una conversación."""
    async with async_session() as session:
        query = select(Mensaje).where(Mensaje.telefono == conversacion_id)
        result = await session.execute(query)
        for msg in result.scalars().all():
            await session.delete(msg)
        await session.commit()


# ── Control de intervención humana ───────────────────────────

async def pausar_conversacion(conversacion_id: str, motivo: str = "intervención humana") -> bool:
    """Pausa a Lucy para una conversación específica. Retorna True si se pausó."""
    async with async_session() as session:
        query = select(ConversacionPausada).where(
            ConversacionPausada.conversacion_id == conversacion_id
        )
        result = await session.execute(query)
        registro = result.scalar_one_or_none()

        if registro:
            registro.pausada = True
            registro.motivo = motivo
            registro.timestamp = datetime.utcnow()
        else:
            session.add(ConversacionPausada(
                conversacion_id=conversacion_id,
                pausada=True,
                motivo=motivo,
            ))
        await session.commit()
        return True


async def reanudar_conversacion(conversacion_id: str) -> bool:
    """Reactiva a Lucy para una conversación pausada. Retorna True si se reanudó."""
    async with async_session() as session:
        query = select(ConversacionPausada).where(
            ConversacionPausada.conversacion_id == conversacion_id
        )
        result = await session.execute(query)
        registro = result.scalar_one_or_none()

        if registro:
            registro.pausada = False
            registro.timestamp = datetime.utcnow()
            await session.commit()
            return True
        return False


async def esta_pausada(conversacion_id: str) -> bool:
    """Verifica si Lucy está pausada para esta conversación."""
    async with async_session() as session:
        query = select(ConversacionPausada).where(
            ConversacionPausada.conversacion_id == conversacion_id,
            ConversacionPausada.pausada == True,
        )
        result = await session.execute(query)
        return result.scalar_one_or_none() is not None


async def listar_pausadas() -> list[dict]:
    """Retorna todas las conversaciones pausadas actualmente."""
    async with async_session() as session:
        query = select(ConversacionPausada).where(ConversacionPausada.pausada == True)
        result = await session.execute(query)
        return [
            {
                "conversacion_id": r.conversacion_id,
                "motivo": r.motivo,
                "desde": r.timestamp.isoformat(),
            }
            for r in result.scalars().all()
        ]
