-- Migração 004: campos de contexto final, evidências e versão para memoriais persistidos
-- Execute no SQL Editor do Supabase em ambientes que já rodaram 002.
--
-- Persiste o snapshot estruturado que produziu o DOCX, permitindo que dashboard,
-- chatbot e site leiam os valores técnicos exatos (quantidades, diâmetros, etc.)
-- sem precisar fazer parsing do DOCX. Também guarda evidências/conflitos da
-- extração e o par (context_version, template_version) que identifica qual
-- contrato foi usado.
--
-- Todas as colunas são opcionais para preservar compatibilidade com registros
-- antigos persistidos pela migração 002.

alter table generated_memorials
    add column if not exists final_context     jsonb,
    add column if not exists extraction_report jsonb,
    add column if not exists conflicts         jsonb not null default '[]'::jsonb,
    add column if not exists context_version   text,
    add column if not exists template_version  text;
