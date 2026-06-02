-- Migracao 007: permite remover usuarios do Supabase Auth sem violar FKs publicas.
-- Perfis continuam sendo removidos por user_profiles.user_id on delete cascade.
-- Memoriais gerados preservam historico textual em created_by_name.

alter table public.generated_memorials
    alter column owner_user_id drop not null;

alter table public.user_profiles
    drop constraint if exists user_profiles_created_by_fkey;

alter table public.user_profiles
    add constraint user_profiles_created_by_fkey
    foreign key (created_by)
    references auth.users(id)
    on delete set null;

alter table public.generated_memorials
    drop constraint if exists generated_memorials_owner_user_id_fkey;

alter table public.generated_memorials
    add constraint generated_memorials_owner_user_id_fkey
    foreign key (owner_user_id)
    references auth.users(id)
    on delete set null;

alter table public.review_sessions
    drop constraint if exists review_sessions_owner_user_id_fkey;

alter table public.review_sessions
    add constraint review_sessions_owner_user_id_fkey
    foreign key (owner_user_id)
    references auth.users(id)
    on delete cascade;
