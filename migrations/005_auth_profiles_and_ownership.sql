-- Migracao 005: perfis de usuario, ownership e RLS para Supabase Auth.
-- Edite os valores OWNER_* antes de executar em ambientes com dados existentes.

create table if not exists public.user_profiles (
    user_id       uuid        primary key references auth.users(id) on delete cascade,
    email         text        not null,
    display_name  text        not null,
    role          text        not null default 'user' check (role in ('owner', 'user')),
    status        text        not null default 'active' check (status in ('active', 'inactive')),
    created_by    uuid        references auth.users(id),
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now()
);

create index if not exists idx_user_profiles_role
    on public.user_profiles (role);

create index if not exists idx_user_profiles_status
    on public.user_profiles (status);

create index if not exists idx_user_profiles_email
    on public.user_profiles (lower(email));

alter table public.generated_memorials
    add column if not exists owner_user_id uuid references auth.users(id),
    add column if not exists created_by_name text;

alter table public.review_sessions
    add column if not exists owner_user_id uuid references auth.users(id);

-- Bootstrap/backfill para desenvolvimento.
-- Troque estes valores antes de usar em outro ambiente.
insert into public.user_profiles (
    user_id,
    email,
    display_name,
    role,
    status,
    created_by
)
select
    id,
    email,
    split_part(email, '@', 1),
    'owner',
    'active',
    id
from auth.users
where id = 'adc8635c-193a-4568-9896-2bc523bba923'::uuid
on conflict (user_id) do update
set
    email = excluded.email,
    role = 'owner',
    status = 'active',
    updated_at = now();

update public.generated_memorials
set
    owner_user_id = 'adc8635c-193a-4568-9896-2bc523bba923'::uuid,
    created_by_name = coalesce(created_by_name, 'admin')
where owner_user_id is null;

update public.review_sessions
set owner_user_id = 'adc8635c-193a-4568-9896-2bc523bba923'::uuid
where owner_user_id is null;

alter table public.generated_memorials
    alter column owner_user_id set not null,
    alter column created_by_name set not null;

alter table public.review_sessions
    alter column owner_user_id set not null;

create index if not exists idx_generated_memorials_owner_created_at
    on public.generated_memorials (owner_user_id, created_at desc);

create index if not exists idx_review_sessions_owner_expires_at
    on public.review_sessions (owner_user_id, expires_at);

alter table public.user_profiles enable row level security;
alter table public.generated_memorials enable row level security;
alter table public.review_sessions enable row level security;

drop policy if exists "Users can read own profile" on public.user_profiles;
create policy "Users can read own profile"
    on public.user_profiles
    for select
    to authenticated
    using (user_id = auth.uid());

drop policy if exists "Owners can read all profiles" on public.user_profiles;
create policy "Owners can read all profiles"
    on public.user_profiles
    for select
    to authenticated
    using (
        exists (
            select 1
            from public.user_profiles owner_profile
            where owner_profile.user_id = auth.uid()
              and owner_profile.role = 'owner'
              and owner_profile.status = 'active'
        )
    );

drop policy if exists "Users can update own display profile" on public.user_profiles;
create policy "Users can update own display profile"
    on public.user_profiles
    for update
    to authenticated
    using (user_id = auth.uid())
    with check (user_id = auth.uid());

drop policy if exists "Users can read own memorials" on public.generated_memorials;
create policy "Users can read own memorials"
    on public.generated_memorials
    for select
    to authenticated
    using (owner_user_id = auth.uid());

drop policy if exists "Users can create own memorials" on public.generated_memorials;
create policy "Users can create own memorials"
    on public.generated_memorials
    for insert
    to authenticated
    with check (owner_user_id = auth.uid());

drop policy if exists "Users can update own memorials" on public.generated_memorials;
create policy "Users can update own memorials"
    on public.generated_memorials
    for update
    to authenticated
    using (owner_user_id = auth.uid())
    with check (owner_user_id = auth.uid());

drop policy if exists "Users can delete own memorials" on public.generated_memorials;
create policy "Users can delete own memorials"
    on public.generated_memorials
    for delete
    to authenticated
    using (owner_user_id = auth.uid());

drop policy if exists "Users can read own review sessions" on public.review_sessions;
create policy "Users can read own review sessions"
    on public.review_sessions
    for select
    to authenticated
    using (owner_user_id = auth.uid());

drop policy if exists "Users can create own review sessions" on public.review_sessions;
create policy "Users can create own review sessions"
    on public.review_sessions
    for insert
    to authenticated
    with check (owner_user_id = auth.uid());

drop policy if exists "Users can update own review sessions" on public.review_sessions;
create policy "Users can update own review sessions"
    on public.review_sessions
    for update
    to authenticated
    using (owner_user_id = auth.uid())
    with check (owner_user_id = auth.uid());

drop policy if exists "Users can delete own review sessions" on public.review_sessions;
create policy "Users can delete own review sessions"
    on public.review_sessions
    for delete
    to authenticated
    using (owner_user_id = auth.uid());
