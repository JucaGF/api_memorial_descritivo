-- Migração 001: tabela de sessões de revisão manual
-- Execute no SQL Editor do Supabase antes de ativar o backend Supabase.

create table if not exists review_sessions (
    session_id          uuid        primary key,
    status              text        not null,
    created_at          timestamptz not null,
    expires_at          timestamptz not null,
    partial_context     jsonb       not null default '{}',
    extraction_report   jsonb       not null default '{}',
    corrections         jsonb       not null default '{}',
    error               text
);

-- Índice para limpeza eficiente de sessões expiradas
create index if not exists idx_review_sessions_expires_at
    on review_sessions (expires_at);

-- Limpeza automática de sessões expiradas (requer pg_cron no Supabase)
-- Habilite em: Dashboard > Database > Extensions > pg_cron
-- select cron.schedule(
--     'limpar_sessoes_expiradas',
--     '0 * * * *',  -- a cada hora
--     $$delete from review_sessions where expires_at < now()$$
-- );

-- Row Level Security: o backend usa service_role_key, portanto RLS não bloqueia.
-- Ative RLS se quiser proteger a tabela de acessos via anon key.
-- alter table review_sessions enable row level security;
