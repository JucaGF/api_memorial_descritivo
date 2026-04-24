-- Migração 002: histórico persistente de memoriais gerados
-- Execute no SQL Editor do Supabase antes de usar os endpoints persistentes.

create table if not exists generated_memorials (
    id              uuid        primary key,
    type            text        not null,
    project_name    text        not null,
    status          text        not null,
    observations    text,
    pdf_filenames   jsonb       not null default '[]',
    storage_bucket  text        not null,
    storage_path    text        not null,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);

create index if not exists idx_generated_memorials_type
    on generated_memorials (type);

create index if not exists idx_generated_memorials_created_at
    on generated_memorials (created_at desc);

-- Storage:
-- Crie um bucket privado chamado "generated-memorials" no Supabase Storage.
-- O backend usa service_role_key para gravar e gera URLs assinadas para download.
