-- KeyFall accounts + sync on Supabase (Postgres). Run in the SQL editor of a new project.
--
-- Mirrors keyfall.sync: one row per synced item, newest updated_at wins, sessions
-- never change once stored. Clients read their rows directly (row-level security)
-- and write only through push_sync_items(), which checks the paid entitlement.
-- See docs/plans/0018_accounts_and_sync.md.

-- ------------------------------------------------------------------ entitlements
-- Written only by the billing webhook (service role). Accounts are created and
-- paid for on the website; the app only signs in.
create table public.entitlements (
    user_id            uuid primary key references auth.users on delete cascade,
    plan               text not null default 'free',      -- 'free' | 'plus'
    status             text not null default 'inactive',  -- Stripe subscription status
    current_period_end timestamptz,
    stripe_customer_id text unique,
    updated_at         timestamptz not null default now()
);

alter table public.entitlements enable row level security;

create policy "read own entitlement" on public.entitlements
    for select using (auth.uid() = user_id);

create or replace function public.has_sync(uid uuid) returns boolean
language sql stable security definer set search_path = public as $$
    select exists (
        select 1 from entitlements
        where user_id = uid and plan <> 'free'
          and status in ('active', 'trialing')
          and (current_period_end is null or current_period_end > now() - interval '3 days')
    );
$$;

-- ------------------------------------------------------------------ sync items
create sequence public.sync_seq;

create table public.sync_items (
    user_id    uuid not null references auth.users on delete cascade,
    kind       text not null check (kind in ('session', 'settings', 'coach')),
    key        text not null,
    -- ISO-8601 UTC text exactly as the client wrote it; compared as text like the client
    updated_at text not null,
    payload    jsonb not null,
    device_id  text not null default '',
    seq        bigint not null default nextval('public.sync_seq'),
    primary key (user_id, kind, key)
);

create index sync_items_pull on public.sync_items (user_id, seq);

alter table public.sync_items enable row level security;

-- Pull: GET /rest/v1/sync_items?seq=gt.<cursor>&order=seq&limit=500
-- Data stays readable after a subscription lapses (only pushing stops), so nobody
-- loses access to their own progress.
create policy "read own items" on public.sync_items
    for select using (auth.uid() = user_id);

-- Push: POST /rest/v1/rpc/push_sync_items {"items": [{kind, key, updated_at, payload,
-- device_id}, ...]}. Returns how many rows were stored.
create or replace function public.push_sync_items(items jsonb) returns integer
language plpgsql security definer set search_path = public as $$
declare
    uid uuid := auth.uid();
    stored integer := 0;
    n integer;
    item jsonb;
begin
    if uid is null then
        raise exception 'not signed in' using errcode = '28000';
    end if;
    if not has_sync(uid) then
        raise exception 'sync needs KeyFall Plus' using errcode = '42501';
    end if;
    if jsonb_array_length(items) > 500 then
        raise exception 'push at most 500 items at a time';
    end if;

    for item in select * from jsonb_array_elements(items) loop
        insert into sync_items as s (user_id, kind, key, updated_at, payload, device_id)
        values (uid, item->>'kind', item->>'key', item->>'updated_at', item->'payload',
                coalesce(item->>'device_id', ''))
        on conflict (user_id, kind, key) do update
            set updated_at = excluded.updated_at,
                payload    = excluded.payload,
                device_id  = excluded.device_id,
                seq        = nextval('public.sync_seq')
            where s.kind <> 'session' and excluded.updated_at > s.updated_at;
        get diagnostics n = row_count;
        stored := stored + n;
    end loop;
    return stored;
end;
$$;

revoke all on function public.push_sync_items(jsonb) from public, anon;
grant execute on function public.push_sync_items(jsonb) to authenticated;
