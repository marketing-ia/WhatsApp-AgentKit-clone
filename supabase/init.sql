-- ============================================================
-- Supabase self-hosted — Inicialización de base de datos
-- Se ejecuta una sola vez al crear el contenedor de PostgreSQL
-- ============================================================

-- Extensiones requeridas por Supabase
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pgjwt";
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";

-- ── Schemas de Supabase ─────────────────────────────────────────────────────
CREATE SCHEMA IF NOT EXISTS auth;
CREATE SCHEMA IF NOT EXISTS extensions;
CREATE SCHEMA IF NOT EXISTS storage;
CREATE SCHEMA IF NOT EXISTS graphql_public;
CREATE SCHEMA IF NOT EXISTS realtime;
CREATE SCHEMA IF NOT EXISTS _realtime;
CREATE SCHEMA IF NOT EXISTS supabase_functions;
CREATE SCHEMA IF NOT EXISTS supabase_migrations;

-- ── Roles de servicio de Supabase ───────────────────────────────────────────
DO $$
BEGIN
  -- anon: rol para requests anónimos (ANON_KEY)
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'anon') THEN
    CREATE ROLE anon NOLOGIN NOINHERIT;
  END IF;
  -- authenticated: rol para usuarios autenticados
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'authenticated') THEN
    CREATE ROLE authenticated NOLOGIN NOINHERIT;
  END IF;
  -- service_role: admin sin RLS (SERVICE_ROLE_KEY)
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'service_role') THEN
    CREATE ROLE service_role NOLOGIN NOINHERIT BYPASSRLS;
  END IF;
  -- authenticator: login role para PostgREST
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'authenticator') THEN
    CREATE ROLE authenticator NOINHERIT LOGIN PASSWORD :'POSTGRES_PASSWORD';
  END IF;
  -- supabase_admin
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'supabase_admin') THEN
    CREATE ROLE supabase_admin NOLOGIN BYPASSRLS;
  END IF;
  -- supabase_auth_admin
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'supabase_auth_admin') THEN
    CREATE ROLE supabase_auth_admin NOLOGIN BYPASSRLS;
  END IF;
  -- supabase_storage_admin
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'supabase_storage_admin') THEN
    CREATE ROLE supabase_storage_admin NOLOGIN BYPASSRLS;
  END IF;
  -- supabase_replication_admin
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'supabase_replication_admin') THEN
    CREATE ROLE supabase_replication_admin NOLOGIN;
  END IF;
END $$;

-- Grants
GRANT anon TO authenticator;
GRANT authenticated TO authenticator;
GRANT service_role TO authenticator;
GRANT supabase_admin TO postgres;

-- ── Base de datos para n8n ──────────────────────────────────────────────────
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_database WHERE datname = 'n8n') THEN
    PERFORM dblink_exec('dbname=postgres', 'CREATE DATABASE n8n');
  END IF;
END $$;

-- User dedicado para n8n
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'n8n_user') THEN
    CREATE ROLE n8n_user LOGIN PASSWORD :'POSTGRES_PASSWORD';
  END IF;
END $$;
GRANT ALL PRIVILEGES ON DATABASE n8n TO n8n_user;

-- ── Base de datos para Chatwoot ─────────────────────────────────────────────
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_database WHERE datname = 'chatwoot') THEN
    PERFORM dblink_exec('dbname=postgres', 'CREATE DATABASE chatwoot');
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'chatwoot_user') THEN
    CREATE ROLE chatwoot_user LOGIN PASSWORD :'POSTGRES_PASSWORD';
  END IF;
END $$;
GRANT ALL PRIVILEGES ON DATABASE chatwoot TO chatwoot_user;

-- ── Base de datos para Evolution API ────────────────────────────────────────
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_database WHERE datname = 'evolution') THEN
    PERFORM dblink_exec('dbname=postgres', 'CREATE DATABASE evolution');
  END IF;
END $$;
GRANT ALL PRIVILEGES ON DATABASE evolution TO postgres;

-- ── Base de datos para Lucy (AgentKit) ──────────────────────────────────────
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_database WHERE datname = 'lucy') THEN
    PERFORM dblink_exec('dbname=postgres', 'CREATE DATABASE lucy');
  END IF;
END $$;
GRANT ALL PRIVILEGES ON DATABASE lucy TO postgres;

-- ── Schema público de Supabase ──────────────────────────────────────────────
GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;
GRANT ALL ON ALL TABLES IN SCHEMA public TO anon, authenticated, service_role;
GRANT ALL ON ALL ROUTINES IN SCHEMA public TO anon, authenticated, service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  GRANT ALL ON TABLES TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  GRANT ALL ON ROUTINES TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  GRANT ALL ON SEQUENCES TO anon, authenticated, service_role;

-- ── Replication para Realtime ───────────────────────────────────────────────
ALTER SYSTEM SET wal_level = logical;
ALTER SYSTEM SET max_replication_slots = 5;
ALTER SYSTEM SET max_wal_senders = 10;
