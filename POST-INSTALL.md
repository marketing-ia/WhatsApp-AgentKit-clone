# POST-INSTALL — Configuración del Ecosistema AgentKit en Easypanel

## ORDEN DE INSTALACIÓN

```
Paso 1 → Generar secretos → Paso 2 → Subir a Easypanel → Paso 3 → Init DBs
Paso 4 → Setup Chatwoot → Paso 5 → Conectar Evolution API → Paso 6 → Vincular GHL webhooks
Paso 7 → Importar flujos n8n → Paso 8 → Probar flujo completo
```

---

## PASO 1 — Generar todos los secretos

Ejecuta esto en tu terminal local (macOS/Linux):

```bash
echo "POSTGRES_PASSWORD=$(openssl rand -hex 24)"
echo "REDIS_PASSWORD=$(openssl rand -hex 16)"
echo "SUPABASE_JWT_SECRET=$(openssl rand -hex 32)"
echo "REALTIME_SECRET=$(openssl rand -hex 32)"
echo "CHATWOOT_SECRET_KEY=$(openssl rand -hex 64)"
echo "N8N_ENCRYPTION_KEY=$(openssl rand -hex 24)"
echo "EVOLUTION_API_KEY=$(openssl rand -hex 20)"
```

Para los JWT de Supabase (ANON_KEY y SERVICE_ROLE_KEY), usa:
https://supabase.com/docs/guides/self-hosting/docker#generate-api-keys

Selecciona "JWT Secret" = el valor de SUPABASE_JWT_SECRET que generaste arriba.
Copia el ANON KEY y el SERVICE ROLE KEY que muestra la herramienta.

---

## PASO 2 — Subir a Easypanel

### Opción A: Docker Compose en Easypanel (recomendada)
1. En Easypanel → tu proyecto → **New Service** → **Docker Compose**
2. Pega el contenido de `docker-compose.yml`
3. En la sección de variables de entorno, pega el contenido de tu `.env` (ya rellenado)
4. Easypanel detectará los servicios automáticamente

### Opción B: Push al repo y conectar desde GitHub
```bash
cd /Users/roymota/WhatsApp-AgentKit-Easypanel
git init && git add . && git commit -m "feat: ecosistema Easypanel completo"
git remote add origin git@github.com:marketing-ia/WhatsApp-AgentKit.git
git push -f origin main
```

### Dominios a configurar en Easypanel (un dominio por servicio):
| Servicio         | Puerto interno | Dominio sugerido                    |
|------------------|---------------|--------------------------------------|
| supabase-kong    | 8000          | `supabase.tudominio.com`            |
| supabase-studio  | 3002          | `studio.tudominio.com`              |
| evolution        | 8080          | `evolution.tudominio.com`           |
| n8n              | 5678          | `n8n.tudominio.com`                 |
| chatwoot-web     | 3000          | `chat.tudominio.com`                |
| lucy             | 8001          | `lucy.tudominio.com`                |

---

## PASO 3 — Inicializar bases de datos

### Chatwoot — migration inicial
```bash
# Desde Easypanel → chatwoot-web → Shell, o via docker exec:
docker exec agentkit-chatwoot-web bundle exec rails db:chatwoot_prepare
```

### Chatwoot — crear superadmin
```bash
docker exec -it agentkit-chatwoot-web bundle exec rails c
# Dentro de rails console:
SuperAdmin.create!(email: 'roymota@marketingkoraia.com', password: 'TuPasswordAqui')
```

---

## PASO 4 — Configurar Chatwoot

1. Abre `https://chat.tudominio.com`
2. Login con el superadmin creado
3. Crea una nueva cuenta → nombre "AgentKit"
4. **Settings → Integrations → Access Token** → copia el token → pega en `.env` como `CHATWOOT_API_TOKEN`
5. Crea un **Inbox de tipo API**:
   - Name: "WhatsApp Lucy"
   - Webhook URL: `https://lucy.tudominio.com/webhook`
6. Crea los agentes del equipo (Roy, etc.)

---

## PASO 5 — Conectar Evolution API con WhatsApp

### Crear instancia y escanear QR
```bash
# Crear instancia Lucy
curl -X POST https://evolution.tudominio.com/instance/create \
  -H "apikey: TU_EVOLUTION_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "instanceName": "lucy",
    "number": "",
    "qrcode": true,
    "integration": "WHATSAPP-BAILEYS",
    "chatwootAccountId": 1,
    "chatwootToken": "TU_CHATWOOT_API_TOKEN",
    "chatwootUrl": "https://chat.tudominio.com",
    "chatwootSignMsg": true,
    "chatwootReopenConversation": false,
    "chatwootConversationPending": false,
    "chatwootImportContacts": true,
    "chatwootNameInbox": "WhatsApp Lucy"
  }'
```

### Obtener QR y escanear
```bash
curl https://evolution.tudominio.com/instance/qrcode/lucy \
  -H "apikey: TU_EVOLUTION_API_KEY"
# Copia el QR base64 y ábrelo en el browser, o usa el endpoint /qrcode.png
```

---

## PASO 6 — Vincular Webhooks de GHL → n8n

GHL reactiva automaciones cuando hay cambios en oportunidades (clínicas, dentistas, seguros, realtor).

### 6.1 — Crear webhook en GHL (por cada Location/cliente)

1. Ve a `https://app.gohighlevel.com` (o tu GHL custom domain)
2. **Settings → Integrations → Webhooks → Add New Webhook**
3. Configura:

```
Name:         "AgentKit n8n — [Nombre Cliente]"
URL:          https://n8n.tudominio.com/webhook/ghl-[tipo-negocio]
Method:       POST
Events (seleccionar):
  ✅ OpportunityCreate
  ✅ OpportunityUpdate  
  ✅ OpportunityDelete
  ✅ ContactCreate
  ✅ ContactUpdate
  ✅ AppointmentCreate
  ✅ AppointmentUpdate
  ✅ NoteCreate
  ✅ TaskCreate
  ✅ InboundMessage
```

### 6.2 — URLs de webhook por vertical (a crear en n8n)

| Vertical   | Webhook URL n8n                                              |
|------------|--------------------------------------------------------------|
| Clínicas   | `https://n8n.tudominio.com/webhook/ghl-clinica`             |
| Dentistas  | `https://n8n.tudominio.com/webhook/ghl-dentista`            |
| Seguros    | `https://n8n.tudominio.com/webhook/ghl-seguros`             |
| Realtor    | `https://n8n.tudominio.com/webhook/ghl-realtor`             |

### 6.3 — Flujo n8n sugerido para GHL webhook

```
[Webhook GHL] → [Switch por event_type]
  → OpportunityCreate: Notificar por WhatsApp al agente + crear contacto en Evolution
  → OpportunityUpdate: Si stage cambió → enviar seguimiento automático por WhatsApp
  → AppointmentCreate: Enviar confirmación WhatsApp al cliente via Evolution API
  → InboundMessage: Registrar en Supabase → pasar a Lucy si no hay agente activo
```

### 6.4 — Llamar a Evolution desde n8n (ejemplo)

En un nodo HTTP Request de n8n:
```
Method: POST
URL: http://evolution:8080/message/sendText/lucy
Headers:
  apikey: {{ $env.EVOLUTION_API_KEY }}
  Content-Type: application/json
Body:
{
  "number": "{{ $json.contact.phone }}",
  "text": "Hola {{ $json.contact.firstName }}, te confirmo tu cita para mañana..."
}
```

---

## PASO 7 — Importar flujos base en n8n

Dentro de n8n (`https://n8n.tudominio.com`):

1. **Credenciales a crear primero:**
   - PostgreSQL → host: `postgres`, db: `n8n`, user: `n8n_user`
   - HTTP Header Auth "Evolution" → Name: `apikey`, Value: `TU_EVOLUTION_API_KEY`
   - HTTP Header Auth "Chatwoot" → Name: `api_access_token`, Value: `TU_CHATWOOT_TOKEN`
   - HTTP Header Auth "Supabase" → Name: `Authorization`, Value: `Bearer TU_SERVICE_ROLE_KEY`
   - GHL OAuth2 → client_id/secret de tu app GHL

2. **Flujos sugeridos a construir:**
   - `[WF-01]` Recibir mensaje Evolution → Router → Lucy → Responder
   - `[WF-02]` GHL Opportunity Update → WhatsApp follow-up
   - `[WF-03]` GHL Appointment → Confirmación + Recordatorio (-24h, -1h)
   - `[WF-04]` Chatwoot Handoff → Notificar agente humano por WhatsApp
   - `[WF-05]` Supabase trigger → Sync contactos GHL ↔ Evolution

---

## PASO 8 — Verificación final

```bash
# ✅ Todos los servicios corriendo
docker compose ps

# ✅ Evolution API responde
curl https://evolution.tudominio.com/instance/fetchInstances \
  -H "apikey: TU_EVOLUTION_API_KEY"

# ✅ n8n accesible
curl https://n8n.tudominio.com/healthz

# ✅ Lucy responde
curl https://lucy.tudominio.com/

# ✅ Supabase Kong
curl https://supabase.tudominio.com/rest/v1/ \
  -H "apikey: TU_ANON_KEY"

# ✅ Chatwoot
curl https://chat.tudominio.com/auth/sign_in \
  -X POST -H "Content-Type: application/json" \
  -d '{"email":"roymota@marketingkoraia.com","password":"TuPass"}'
```

---

## TROUBLESHOOTING RÁPIDO

| Problema | Causa probable | Solución |
|----------|---------------|----------|
| Evolution no conecta a n8n | URL del webhook incorrecta | Verificar `WEBHOOK_GLOBAL_URL=http://n8n:5678/webhook/evolution` |
| n8n no puede escribir en Supabase | DB user no existe | Correr el init.sql manualmente |
| Chatwoot 500 error | DB no migrada | `rails db:chatwoot_prepare` |
| QR de WhatsApp no aparece | Instancia no creada | Crear instancia via API POST |
| Kong 401 | ANON_KEY no coincide con JWT_SECRET | Regenerar tokens con el mismo JWT_SECRET |
| Lucy no responde | Chatwoot token incorrecto | Actualizar `CHATWOOT_API_TOKEN` en .env |

---

## ARQUITECTURA INTERNA (URLs Docker)

```
n8n → Evolution:   http://evolution:8080
n8n → Supabase DB: postgres://postgres:PASS@postgres:5432/postgres
n8n → Chatwoot:    http://chatwoot-web:3000
n8n → Supabase REST: http://supabase-kong:8000/rest/v1/
Evolution → n8n:   http://n8n:5678/webhook/evolution
Lucy → Postgres:   postgresql+asyncpg://postgres:PASS@postgres:5432/lucy
```
