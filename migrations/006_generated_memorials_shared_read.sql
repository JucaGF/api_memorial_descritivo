-- Migracao 006: todos os usuarios autenticados podem ver e baixar todos os memoriais.
-- A criacao continua registrando owner_user_id/created_by_name.
-- Exclusao e atualizacao permanecem restritas ao dono do memorial.

drop policy if exists "Users can read own memorials" on public.generated_memorials;
drop policy if exists "Authenticated users can read generated memorials" on public.generated_memorials;

create policy "Authenticated users can read generated memorials"
    on public.generated_memorials
    for select
    to authenticated
    using (true);
