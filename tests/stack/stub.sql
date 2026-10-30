-- Minimal stand-in for Supabase: roles, auth.users, auth.uid(), storage.
do $$ begin if not exists (select 1 from pg_roles where rolname = 'anon') then create role anon nologin; create role authenticated nologin; create role service_role nologin bypassrls; end if; end $$;
grant usage on schema public to anon, authenticated;
alter default privileges in schema public grant select, insert, update, delete on tables to anon, authenticated;
alter default privileges in schema public grant execute on functions to anon, authenticated;
alter default privileges in schema public grant usage, select on sequences to anon, authenticated;
create schema auth; grant usage on schema auth to anon, authenticated;
create table auth.users (id uuid primary key default gen_random_uuid(), email text unique, raw_user_meta_data jsonb default '{}'::jsonb, created_at timestamptz default now(), invited_at timestamptz, email_confirmed_at timestamptz, last_sign_in_at timestamptz);
create function auth.uid() returns uuid language sql stable as $$ select nullif(nullif(current_setting('request.jwt.claims', true),'')::jsonb->>'sub','')::uuid $$;
grant execute on function auth.uid() to anon, authenticated;
create schema storage; grant usage on schema storage to anon, authenticated;
create table storage.buckets (id text primary key, name text, public boolean, file_size_limit bigint, allowed_mime_types text[]);
-- Shaped like Supabase's storage.objects (the columns policies use). The API roles hold table rights and row security decides, as on Supabase.
create table storage.objects (id uuid primary key default gen_random_uuid(), bucket_id text, name text, owner uuid, owner_id text default (nullif(nullif(current_setting('request.jwt.claims', true),'')::jsonb->>'sub','')), metadata jsonb, created_at timestamptz default now());
grant select, insert, update, delete on storage.objects to anon, authenticated;
alter table storage.objects enable row level security;
create function storage.foldername(name text) returns text[] language sql immutable as $$ select (string_to_array(name, '/'))[1:array_length(string_to_array(name, '/'),1)-1] $$;

-- MFA and sessions, shaped like Supabase's auth schema (only the columns Saaz reads)
create type auth.aal_level as enum ('aal1','aal2','aal3');
create type auth.factor_status as enum ('unverified','verified');
create type auth.factor_type as enum ('totp','webauthn','phone');
create table auth.mfa_factors (id uuid primary key default gen_random_uuid(), user_id uuid references auth.users(id) on delete cascade, friendly_name text, factor_type auth.factor_type, status auth.factor_status, secret text, created_at timestamptz default now(), updated_at timestamptz default now());
create table auth.sessions (id uuid primary key default gen_random_uuid(), user_id uuid references auth.users(id) on delete cascade, aal auth.aal_level default 'aal1', factor_id uuid, ip inet, user_agent text, created_at timestamptz default now());
create table auth.mfa_amr_claims (id uuid primary key default gen_random_uuid(), session_id uuid references auth.sessions(id) on delete cascade, authentication_method text, created_at timestamptz default now());
create function auth.jwt() returns jsonb language sql stable as $$ select coalesce(nullif(current_setting('request.jwt.claims', true),''),'{}')::jsonb $$;
grant execute on function auth.jwt() to anon, authenticated;
