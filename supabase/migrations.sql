-- ============================================================
-- AgentKit — Tablas para los flujos n8n
-- Ejecutar en: Supabase Studio → SQL Editor
-- O: psql -U postgres -d postgres -f migrations.sql
-- ============================================================

-- ── Tabla: message_logs (WF-01) ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.message_logs (
  id            UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
  phone         TEXT        NOT NULL,
  push_name     TEXT,
  text          TEXT,
  instance      TEXT        DEFAULT 'lucy',
  message_id    TEXT        UNIQUE,
  is_stop       BOOLEAN     DEFAULT false,
  is_continuar  BOOLEAN     DEFAULT false,
  created_at    TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_msg_logs_phone ON public.message_logs(phone);
CREATE INDEX IF NOT EXISTS idx_msg_logs_created ON public.message_logs(created_at DESC);

-- ── Tabla: ghl_message_logs (WF-02) ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.ghl_message_logs (
  id              UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
  phone           TEXT        NOT NULL,
  contact_name    TEXT,
  stage           TEXT,
  location_id     TEXT,
  opportunity_id  TEXT,
  message_sent    TEXT,
  created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ghl_logs_phone ON public.ghl_message_logs(phone);
CREATE INDEX IF NOT EXISTS idx_ghl_logs_stage ON public.ghl_message_logs(stage);

-- ── Tabla: appointment_reminders (WF-03) ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.appointment_reminders (
  id               UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
  appointment_id   TEXT        NOT NULL UNIQUE,
  contact_phone    TEXT        NOT NULL,
  contact_name     TEXT,
  appointment_time TIMESTAMPTZ NOT NULL,
  reminder_type    TEXT        NOT NULL CHECK (reminder_type IN ('24h', '1h')),
  send_at          TIMESTAMPTZ NOT NULL,
  sent             BOOLEAN     DEFAULT false,
  sent_at          TIMESTAMPTZ,
  message          TEXT,
  location_id      TEXT,
  created_at       TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_reminders_send_at ON public.appointment_reminders(send_at) WHERE sent = false;
CREATE INDEX IF NOT EXISTS idx_reminders_phone ON public.appointment_reminders(contact_phone);

-- ── Tabla: contact_sync (WF-05) ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.contact_sync (
  id                UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
  phone             TEXT        NOT NULL UNIQUE,
  push_name         TEXT,
  ghl_contact_id    TEXT,
  evolution_instance TEXT       DEFAULT 'lucy',
  last_synced_at    TIMESTAMPTZ,
  created_at        TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_contact_sync_phone ON public.contact_sync(phone);
CREATE INDEX IF NOT EXISTS idx_contact_sync_ghl ON public.contact_sync(ghl_contact_id);

-- ── RLS: habilitar y dar acceso al service_role ───────────────────────────────
ALTER TABLE public.message_logs        ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ghl_message_logs    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.appointment_reminders ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.contact_sync        ENABLE ROW LEVEL SECURITY;

-- service_role bypasses RLS; anon/authenticated solo si se necesita
CREATE POLICY "service_role full access" ON public.message_logs
  FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role full access" ON public.ghl_message_logs
  FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role full access" ON public.appointment_reminders
  FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role full access" ON public.contact_sync
  FOR ALL TO service_role USING (true) WITH CHECK (true);
