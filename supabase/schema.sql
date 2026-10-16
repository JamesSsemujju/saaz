-- Saaz database: cars, admins and car photos.
-- Run once in Supabase: Dashboard > SQL Editor > New query > paste > Run.
-- Rules enforced by the database itself, not just the website:
--   * anyone can read published cars; nobody else can read drafts
--   * only people listed in public.admins can add, edit or delete cars and photos
--   * a car cannot be published unless it passed a review, has a review date and garage,
--     and an admin confirmed the photos hide number plates

create table if not exists public.admins (
  user_id uuid primary key references auth.users(id) on delete cascade,
  name text not null,
  added_at timestamptz not null default now()
);

create table if not exists public.cars (
  id uuid primary key default gen_random_uuid(),
  ref text unique not null,                       -- Saaz reference, e.g. SZ-0001
  source text not null check (source in ('import','local')),
  status text not null default 'draft' check (status in ('draft','published','sold')),
  make text not null,
  model text not null,
  year int not null check (year between 1980 and 2100),
  body text not null,
  fuel text not null,
  gearbox text not null,
  drive text not null,
  km int not null check (km >= 0),
  cc int check (cc > 0),
  colour text,
  price_ugx bigint not null check (price_ugx > 0),
  area text not null,
  seller text not null,
  chassis text not null,                          -- shown masked on the site, e.g. ZSU60-•••2210
  review_result text check (review_result in ('Passed','Failed')),
  review_date date,
  review_garage text,
  findings jsonb not null default '[]'::jsonb,   -- [{"area":"Tyres","level":"attention|note","note":"..."}]
  photos text[] not null default '{}',            -- storage paths in the car-photos bucket
  plates_hidden boolean not null default false,
  created_by uuid references auth.users(id) default auth.uid(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint publish_needs_review check (
    status = 'draft' or (review_result = 'Passed' and review_date is not null and review_garage is not null and plates_hidden)
  )
);

create or replace function public.is_admin() returns boolean
language sql stable security definer set search_path = public as
$$ select exists (select 1 from public.admins where user_id = auth.uid()) $$;

create or replace function public.touch_updated_at() returns trigger language plpgsql set search_path = public as
$$ begin new.updated_at = now(); return new; end $$;
drop trigger if exists cars_touch on public.cars;
create trigger cars_touch before update on public.cars for each row execute function public.touch_updated_at();

alter table public.admins enable row level security;
alter table public.cars enable row level security;

drop policy if exists "admins read own row" on public.admins;
create policy "admins read own row" on public.admins for select using (user_id = auth.uid());

drop policy if exists "public reads published cars" on public.cars;
create policy "public reads published cars" on public.cars for select using (status = 'published' or public.is_admin());
drop policy if exists "admins insert cars" on public.cars;
create policy "admins insert cars" on public.cars for insert with check (public.is_admin());
drop policy if exists "admins update cars" on public.cars;
create policy "admins update cars" on public.cars for update using (public.is_admin()) with check (public.is_admin());
drop policy if exists "admins delete cars" on public.cars;
create policy "admins delete cars" on public.cars for delete using (public.is_admin());

-- Photos: public bucket for reading; only admins can upload, change or delete.
insert into storage.buckets (id, name, public) values ('car-photos', 'car-photos', true)
  on conflict (id) do nothing;
drop policy if exists "admins upload photos" on storage.objects;
create policy "admins upload photos" on storage.objects for insert with check (bucket_id = 'car-photos' and public.is_admin());
drop policy if exists "admins change photos" on storage.objects;
create policy "admins change photos" on storage.objects for update using (bucket_id = 'car-photos' and public.is_admin());
drop policy if exists "admins delete photos" on storage.objects;
create policy "admins delete photos" on storage.objects for delete using (bucket_id = 'car-photos' and public.is_admin());

-- To make someone an admin: create their login under Authentication > Users, copy their user id, then run:
-- insert into public.admins (user_id, name) values ('<user id>', '<name>');
