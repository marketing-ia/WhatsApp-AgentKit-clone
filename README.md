# WhatsApp AgentKit — Construye tu Agente de WhatsApp con IA

> Por **Roy Mota / Marketing IA** · [marketingkoraia.com](https://marketingkoraia.com)

Construye un agente de WhatsApp con inteligencia artificial personalizado para tu negocio en menos de 30 minutos. Sin necesidad de saber programar.

---

## ¿Qué incluye?

- **Agente IA personalizado** — basado en Claude (Anthropic claude-sonnet-4-6)
- **Integración con Chatwoot + Evolution API** — recibe y responde mensajes de WhatsApp
- **Memoria de conversaciones** — recuerda el contexto de cada cliente
- **Intervención humana** — pausa el agente cuando necesitas atender personalmente
- **Multi-negocio** — un solo agente puede representar varios negocios
- **Deploy en Railway** — servidor en producción en minutos

---

## Requisitos

- Python 3.11+
- Una cuenta en [Anthropic](https://platform.anthropic.com) (API Key)
- Una instancia de [Chatwoot](https://www.chatwoot.com) con Evolution API
- Una cuenta en [Railway](https://railway.app) para el deploy

---

## Inicio rápido

### 1. Clona el repositorio

```bash
git clone https://github.com/marketing-ia/WhatsApp-AgentKit-clone.git
cd WhatsApp-AgentKit-clone
```

### 2. Instala dependencias

```bash
pip3 install -r requirements.txt
```

### 3. Configura tus variables de entorno

Copia el archivo de ejemplo y completa tus datos:

```bash
cp .env.example .env
```

Variables principales en `.env`:

```env
ANTHROPIC_API_KEY=sk-ant-...
WHATSAPP_PROVIDER=chatwoot

CHATWOOT_URL=https://tu-chatwoot.com
CHATWOOT_API_TOKEN=tu-token
CHATWOOT_ACCOUNT_ID=1
CHATWOOT_INBOX_ID=7

EVOLUTION_API_URL=https://tu-evolution-api.com
EVOLUTION_INSTANCE=nombre-instancia
EVOLUTION_API_KEY=tu-api-key

PORT=8000
ENVIRONMENT=development
DATABASE_URL=sqlite+aiosqlite:///./agentkit.db
```

### 4. Personaliza tu agente

- Edita `config/prompts.yaml` — define la personalidad y conocimiento de tu agente
- Edita `config/business.yaml` — datos de tu empresa, horario y servicios
- Agrega archivos a `knowledge/` — PDFs, TXTs, CSVs con info de tu negocio

### 5. Prueba en local (sin WhatsApp)

```bash
python3 tests/test_local.py
```

Chatea con tu agente directamente en la terminal.

### 6. Levanta el servidor

```bash
uvicorn agent.main:app --reload --port 8000
```

---

## Estructura del proyecto

```
WhatsApp-AgentKit/
├── agent/
│   ├── main.py            # Servidor FastAPI + webhook
│   ├── brain.py           # Conexión con Claude AI
│   ├── memory.py          # Historial de conversaciones (SQLite)
│   ├── tools.py           # Herramientas del negocio
│   └── providers/
│       ├── base.py        # Interfaz base de proveedores
│       ├── chatwoot.py    # Adaptador Chatwoot + Evolution API
│       └── __init__.py    # Factory de proveedores
├── config/
│   ├── business.yaml      # Datos del negocio
│   └── prompts.yaml       # System prompt del agente
├── tests/
│   └── test_local.py      # Simulador de chat en terminal
├── knowledge/             # Archivos de tu negocio (PDF, TXT, etc.)
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

---

## Intervención humana

Cuando necesitas atender personalmente, tienes 3 formas de pausar al agente:

**1. Asignar la conversación en Chatwoot** — el agente deja de responder automáticamente

**2. Etiqueta `paused`** — agrega la etiqueta en la conversación de Chatwoot

**3. API de administración:**

```bash
# Pausar el agente en una conversación
POST https://tu-servidor.railway.app/admin/pausa/{conversation_id}

# Reactivar el agente
POST https://tu-servidor.railway.app/admin/reanudar/{conversation_id}

# Ver todas las conversaciones pausadas
GET https://tu-servidor.railway.app/admin/pausadas
```

---

## Deploy en Railway

```bash
# Login en Railway
railway login

# Crear proyecto y desplegar
railway init
railway up

# Asignar dominio público
railway domain
```

Configura las variables de entorno en el dashboard de Railway y conecta el webhook en Chatwoot apuntando a `https://tu-app.up.railway.app/webhook`.

---

## Construido con

| Tecnología | Uso |
|-----------|-----|
| [FastAPI](https://fastapi.tiangolo.com) | Servidor web y webhook |
| [Anthropic Claude](https://anthropic.com) | Motor de IA (claude-sonnet-4-6) |
| [Chatwoot](https://chatwoot.com) | Bandeja de entrada omnicanal |
| [Evolution API](https://evolution-api.com) | Conexión con WhatsApp |
| [SQLAlchemy + SQLite](https://sqlalchemy.org) | Memoria de conversaciones |
| [Railway](https://railway.app) | Deploy en producción |

---

## ¿Necesitas ayuda o quieres una implementación personalizada?

**Roy Mota · Marketing IA**

- Web: [marketingkoraia.com](https://marketingkoraia.com)
- Roma Insurance: [romainsurancegroup.com](https://romainsurancegroup.com)

---

> *AgentKit — Porque cualquier negocio merece un agente de IA personalizado.*
