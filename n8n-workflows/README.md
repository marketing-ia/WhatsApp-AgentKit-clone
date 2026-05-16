# Flujos n8n — AgentKit Ecosistema

5 flujos listos para importar. Base URL n8n: `https://n8n-roy-n8n.78s07r.easypanel.host`

## Importar en n8n

1. Abre tu n8n → **Settings → Import from file**
2. Selecciona cada archivo `.json` de esta carpeta
3. Activa los flujos UNO A UNO después de configurar las variables

## Variables de entorno requeridas en n8n

Ve a n8n → **Settings → Variables** y añade:

| Variable               | Valor                                      |
|------------------------|--------------------------------------------|
| `EVOLUTION_API_URL`    | `http://evolution:8080` (interno) o URL pública |
| `EVOLUTION_API_KEY`    | Tu API key de Evolution                    |
| `SUPABASE_URL`         | `http://supabase-kong:8000` (interno) o URL pública |
| `SUPABASE_SERVICE_KEY` | Tu Service Role Key de Supabase            |
| `CHATWOOT_URL`         | `http://chatwoot-web:3000` (interno) o URL pública |
| `CHATWOOT_API_TOKEN`   | Token de acceso de Chatwoot                |
| `CHATWOOT_EXTERNAL_URL`| `https://chat.tudominio.com`               |
| `GHL_API_KEY`          | API Key de Go High Level                   |
| `GHL_BASE_URL`         | `https://services.leadconnectorhq.com`     |
| `GHL_LOCATION_SEGUROS` | Location ID para seguros en GHL            |
| `LUCY_API_URL`         | `http://lucy:8000` (interno) o URL pública |
| `AGENT_WHATSAPP`       | Teléfono de Roy/agente para notificaciones |

## Descripción de cada flujo

### WF-01 — Evolution: Enrutador STOP/CONTINUAR + Logging
**Webhook:** `POST /webhook/evolution`  
Recibe TODOS los mensajes de WhatsApp desde Evolution API. Detecta comandos especiales y registra en Supabase.

| Comando cliente | Acción |
|----------------|--------|
| `STOP`, `PARA`, `ALTO`, `HUMANO` | Pausa Lucy + notifica al cliente |
| `CONTINUAR`, `ACTIVAR`, `LUCY` | Reanuda Lucy + saludo de vuelta |
| Cualquier otro mensaje | Log en `message_logs` |

**Configurar en Evolution API:** `WEBHOOK_GLOBAL_URL=http://n8n:5678/webhook/evolution`

---

### WF-02 — GHL Oportunidad → WhatsApp por Etapa
**Webhook:** `POST /webhook/ghl-opportunity`  
Recibe eventos `OpportunityCreate/Update` de GHL y envía mensajes WhatsApp personalizados según la etapa del pipeline.

Etapas con mensaje automático: `New Lead`, `Contacted`, `Appointment Scheduled`, `Proposal Sent`, `Follow Up`, `Won`, `Cita Agendada`, `Property Interest`, y más.

**Configurar en GHL:** Settings → Webhooks → Add → URL: `https://n8n-roy-n8n.78s07r.easypanel.host/webhook/ghl-opportunity` → Events: OpportunityCreate, OpportunityUpdate

---

### WF-03 — GHL Citas: Confirmación + Recordatorios Automáticos
**Webhook:** `POST /webhook/ghl-appointment`  
**Scheduler:** Cada 15 minutos revisa recordatorios pendientes

Cuando llega una cita nueva:
1. Envía confirmación inmediata al cliente
2. Programa recordatorio -24h en tabla `appointment_reminders`
3. Programa recordatorio -1h en tabla `appointment_reminders`

El scheduler de 15 min envía los recordatorios cuando llega su hora y los marca como `sent=true`.

**Configurar en GHL:** Settings → Webhooks → Add → URL: `https://n8n-roy-n8n.78s07r.easypanel.host/webhook/ghl-appointment` → Events: AppointmentCreate, AppointmentUpdate

**Tabla Supabase requerida:** `appointment_reminders` (ver `supabase/migrations.sql`)

---

### WF-04 — Chatwoot Handoff: Notificar Agente Humano
**Webhook:** `POST /webhook/chatwoot-handoff`  
Cuando Chatwoot detecta que un cliente necesita atención humana, notifica al agente (Roy) por WhatsApp con el link directo a la conversación.

Se activa cuando la conversación tiene etiqueta `requires_human` o `human_requested`.

**Configurar en Chatwoot:** Settings → Integrations → Webhooks → Add → URL: `https://n8n-roy-n8n.78s07r.easypanel.host/webhook/chatwoot-handoff` → Events: conversation_created, conversation_updated, label_created

---

### WF-05 — Sync Contactos Evolution → GHL (cada hora)
**Trigger:** Schedule cada 1 hora  
Sincroniza los contactos de WhatsApp (Evolution API) con GHL como leads. Verifica en Supabase si ya fueron sincronizados para no duplicar.

Flujo: Evolution contacts → filtrar → check Supabase → crear en GHL → guardar en `contact_sync`

---

## Orden de activación recomendado

```
1. WF-03 (Citas) — activar primero para que el scheduler esté corriendo
2. WF-01 (Evolution) — activar cuando Evolution esté conectado con WhatsApp
3. WF-02 (GHL Oportunidades) — activar después de configurar webhooks en GHL
4. WF-04 (Chatwoot) — activar después de configurar Chatwoot webhooks
5. WF-05 (Sync) — activar último, es el menos urgente
```
