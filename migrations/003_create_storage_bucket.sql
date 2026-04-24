-- Migração 003: cria o bucket privado para armazenar os memoriais gerados (.docx)
-- Execute no SQL Editor do Supabase.

insert into storage.buckets (id, name, public)
values ('generated-memorials', 'generated-memorials', false)
on conflict (id) do nothing;
