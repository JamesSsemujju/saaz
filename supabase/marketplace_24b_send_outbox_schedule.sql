-- Part 24b (optional): run send-outbox every minute with Supabase Cron, so SMS go out even when nobody is using the site.
-- Without this, the app calls send-outbox after actions, so SMS go out while people use Saaz.
-- Pattern from Supabase docs, "Scheduling Edge Functions" (pg_cron + pg_net + Vault). NOT tested locally: the local copy has no pg_cron.
-- Before running: Database, Extensions, turn on pg_cron and pg_net. Deploy send-outbox first.
-- The key stored here is the public anon key (the same one the website ships with), not the service key.

-- 1. Run these two once, in the SQL Editor, with the real values typed there (Settings, API):
--    select vault.create_secret('https://dkxyvlkhpnajbpethwqb.supabase.co', 'saaz_project_url');
--    select vault.create_secret('<the anon key from src/data/site.json>', 'saaz_anon_key');

-- 2. The schedule
select cron.schedule(
  'saaz-send-outbox',
  '* * * * *',
  $$
  select net.http_post(
    url := (select decrypted_secret from vault.decrypted_secrets where name = 'saaz_project_url') || '/functions/v1/send-outbox',
    headers := jsonb_build_object('Content-Type', 'application/json',
      'Authorization', 'Bearer ' || (select decrypted_secret from vault.decrypted_secrets where name = 'saaz_anon_key')),
    body := '{}'::jsonb) as request_id;
  $$
);

-- To stop it: select cron.unschedule('saaz-send-outbox');
