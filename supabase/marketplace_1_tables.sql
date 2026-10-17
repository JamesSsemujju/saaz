-- Saaz marketplace, part 1 of 4: tables, settings and regions.
-- Source: "Saaz marketplace: build description" (17 Oct 2026). Adds to schema.sql; changes nothing in it.
-- All writes go through the functions in parts 2 and 3. Tables only allow direct reads (part 4).

-- Settings: every number in the build description's assumptions. Editable by admins.
create table public.settings (
  key text primary key,
  value jsonb not null,
  note text,
  updated_at timestamptz not null default now()
);
insert into public.settings (key, value, note) values
  ('garage_contact_hours', '24', 'Hours a garage in play has to message the seller'),
  ('listing_limit', '3', 'Active listings per seller, unless trusted'),
  ('mileage_flag_pct', '5', 'Review odometer differs from seller figure by more than this percent'),
  ('min_price_ugx', '1000000', 'Lowest asking price, UGX'),
  ('min_price_kes', '30000', 'Lowest asking price, KES'),
  ('min_offer_pct', '50', 'Lowest offer allowed, percent of asking'),
  ('review_valid_days', '60', 'Days a Saaz review stays valid'),
  ('selling_fast_min_sold', '2', 'Sold in 90 days to count as Selling fast'),
  ('selling_fast_max_days', '14', 'Median days to sell to count as Selling fast'),
  ('trend_min_listings', '5', 'Below this many listings a model is a hint, not a trend'),
  ('require_phone_verified', 'false', 'Placeholder: true once an SMS provider is connected'),
  ('approval_response', '"1 working day"', 'Shown to sellers'),
  ('garage_response', '"2 working days"', 'Shown to garage applicants');

-- Regions with rough centres, for "nearest garage first". Assumption: centre points only.
create table public.regions (
  name text primary key,
  country text not null check (country in ('UG','KE')),
  lat double precision not null,
  lng double precision not null
);
insert into public.regions values
  ('Kampala','UG',0.3476,32.5825), ('Wakiso','UG',0.4044,32.4594), ('Entebbe','UG',0.0512,32.4637),
  ('Mukono','UG',0.3533,32.7553), ('Jinja','UG',0.4244,33.2042), ('Mbarara','UG',-0.6072,30.6545),
  ('Gulu','UG',2.7724,32.2881),
  ('Nairobi','KE',-1.2921,36.8219), ('Mombasa','KE',-4.0435,39.6682), ('Kisumu','KE',-0.0917,34.7680),
  ('Nakuru','KE',-0.3031,36.0800), ('Eldoret','KE',0.5143,35.2698);

-- Accounts: one type, keyed by email. Every account can buy and sell.
create table public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  email text not null,
  name text not null default '',
  country text check (country in ('UG','KE')),
  mobile text,
  phone_verified boolean not null default false,
  trusted boolean not null default false,
  suspended boolean not null default false,
  created_at timestamptz not null default now()
);

-- Vehicle record: one per VIN, separate from listings. Grows with every review and sale.
create table public.vehicles (
  id uuid primary key default gen_random_uuid(),
  vin text unique not null check (vin ~ '^[A-Z0-9-]{6,20}$'),
  make text, model text, year int, fuel text, gearbox text, body text, engine text,
  source text not null default 'local' check (source in ('saaz_import','local')),
  import_mileage int,
  saaz_owned boolean not null default false,       -- a Saaz import not yet sold to a person
  first_record_date date not null default current_date,
  created_at timestamptz not null default now()
);

create table public.odometer_readings (
  id uuid primary key default gen_random_uuid(),
  vehicle_id uuid not null references public.vehicles(id),
  km int not null check (km between 0 and 1000000),
  source text not null check (source in ('import','review','sale')),
  review_id uuid,
  flagged text,                                    -- why it was flagged, or null
  recorded_at timestamptz not null default now()
);

create sequence public.listing_ref_seq;
create table public.listings (
  id uuid primary key default gen_random_uuid(),
  ref text unique not null default ('SZ-' || lpad(nextval('public.listing_ref_seq')::text, 5, '0')),
  vehicle_id uuid not null references public.vehicles(id),
  seller_id uuid references public.profiles(id),   -- null when Saaz owns the car
  saaz_owned boolean not null default false,
  country text not null check (country in ('UG','KE')),
  region text not null references public.regions(name),
  status text not null default 'draft' check (status in ('draft','awaiting_review','review_booked','awaiting_approval',
    'changes_requested','live','reserved','sold','rejected','withdrawn','re_review_due')),
  make text not null, model text not null,
  year int not null, fuel text not null, gearbox text not null, body text not null, colour text not null,
  engine text,
  mileage int not null check (mileage between 0 and 1000000),
  plate text not null,
  currency text not null check (currency in ('UGX','KES')),
  price bigint not null check (price > 0),
  description text not null default '',
  photos text[] not null default '{}',
  logbook_name_matches boolean not null default false,
  owner_authorised boolean not null default false,
  -- offer rules
  rule_min_pct int check (rule_min_pct between 1 and 100),
  rule_min_amount bigint check (rule_min_amount > 0),
  rule_no_trade_in boolean not null default false,
  rule_on_counters boolean not null default false,
  auto_reject boolean not null default false,
  -- line and review state
  line_empty boolean not null default false,
  line_round int not null default 1,           -- admin "restart the line" starts a new round
  current_review_id uuid,
  admin_note text,
  submitted_at timestamptz, live_at timestamptz, sold_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check ((saaz_owned and seller_id is null) or (not saaz_owned and seller_id is not null))
);
create unique index listings_one_active_plate on public.listings (upper(replace(plate,' ','')))
  where status not in ('sold','rejected','withdrawn');
create unique index listings_one_active_vehicle on public.listings (vehicle_id)
  where status not in ('sold','rejected','withdrawn');

-- Garages and their teams
create table public.garages (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  business_type text not null check (business_type in ('garage','independent_mechanic')),
  country text not null check (country in ('UG','KE')),
  region text not null references public.regions(name),
  address text not null,
  phone text not null,
  registration_no text not null,
  years int check (years >= 0),
  specialties text[] not null default '{}',
  honest_declaration boolean not null default false,
  status text not null default 'applied' check (status in ('applied','more_info','certified','rejected','suspended')),
  status_note text,
  certified_at timestamptz,
  created_by uuid references public.profiles(id),
  created_at timestamptz not null default now()
);

create table public.garage_members (
  id uuid primary key default gen_random_uuid(),
  garage_id uuid not null references public.garages(id),
  user_id uuid not null references public.profiles(id),
  role text not null check (role in ('owner','inspector')),
  status text not null default 'invited' check (status in ('invited','active','removed')),
  added_at timestamptz not null default now()
);
-- One garage per person (assumption from the build description)
create unique index garage_members_one_garage on public.garage_members (user_id) where status <> 'removed';

-- Invites for emails with no account yet. Matched when that email signs up.
create table public.garage_invites (
  id uuid primary key default gen_random_uuid(),
  garage_id uuid not null references public.garages(id),
  email text not null,
  name text,
  mobile text,
  role text not null check (role in ('owner','inspector')),
  used boolean not null default false,
  created_at timestamptz not null default now()
);

-- Garage line: one garage in play per car, talking only inside Saaz
create table public.conversations (
  id uuid primary key default gen_random_uuid(),
  listing_id uuid not null references public.listings(id),
  garage_id uuid not null references public.garages(id),
  status text not null default 'in_play' check (status in ('in_play','agreed','passed','declined','timed_out','released','closed')),
  assigned_by_admin boolean not null default false,
  round int not null default 1,
  deadline timestamptz,
  garage_first_message_at timestamptz,
  review_date date,
  opened_at timestamptz not null default now(),
  closed_at timestamptz
);
create unique index conversations_one_open on public.conversations (listing_id) where status in ('in_play','agreed');

-- The seller's reason for passing. Separate table so the garage can't read it.
create table public.pass_reasons (
  conversation_id uuid primary key references public.conversations(id),
  reason text not null
);

create table public.messages (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references public.conversations(id),
  sender_id uuid not null references public.profiles(id),
  side text not null check (side in ('seller','garage')),
  body text not null check (length(body) between 1 and 2000),
  created_at timestamptz not null default now()
);

-- Saaz reviews
create sequence public.review_doc_seq;
create table public.reviews (
  id uuid primary key default gen_random_uuid(),
  listing_id uuid not null references public.listings(id),
  vehicle_id uuid not null references public.vehicles(id),
  garage_id uuid not null references public.garages(id),
  member_id uuid not null references public.profiles(id),
  status text not null default 'draft' check (status in ('draft','issued','superseded','void')),
  checks jsonb not null default '{}'::jsonb,       -- {"engine":"pass|advise|fail", ...} 12 keys
  panels jsonb not null default '{}'::jsonb,       -- {"bonnet":"none|scratch|dent|repaint|damage", ...} 9 keys
  odometer int check (odometer between 0 and 1000000),
  notes text not null default '',
  in_person boolean not null default false,
  doc_no text unique,
  version int,
  verdict text check (verdict in ('pass','conditional','fail')),
  score int check (score between 0 and 100),
  fingerprint text,
  verify_code text unique,
  odometer_flag text,
  member_name text, member_role text, garage_name text, garage_certified_at timestamptz,
  issued_at timestamptz,
  valid_until date,
  void_reason text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
alter table public.listings add constraint listings_current_review_fk foreign key (current_review_id) references public.reviews(id);
alter table public.odometer_readings add constraint odometer_review_fk foreign key (review_id) references public.reviews(id);

-- Offers and deals. One deal per buyer per listing; every offer and counter is a deal event.
create table public.deals (
  id uuid primary key default gen_random_uuid(),
  listing_id uuid not null references public.listings(id),
  buyer_id uuid not null references public.profiles(id),
  amount bigint not null check (amount > 0),
  trade_in boolean not null default false,
  last_by text not null check (last_by in ('buyer','seller','admin')),
  buyer_ok boolean not null default false,
  seller_ok boolean not null default false,
  flag text,                                       -- which rule the latest buyer figure breaks (auto-reject off)
  status text not null default 'negotiating' check (status in ('negotiating','agreed','completed','cancelled','on_hold','closed','auto_rejected','rejected','withdrawn')),
  agreed_note text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create unique index deals_one_open on public.deals (listing_id, buyer_id) where status in ('negotiating','agreed','on_hold');

create table public.deal_events (
  id uuid primary key default gen_random_uuid(),
  deal_id uuid not null references public.deals(id),
  by_side text not null check (by_side in ('buyer','seller','admin','system')),
  kind text not null check (kind in ('offer','counter','accept','reject','auto_reject','withdraw','propose','agreed','completed','cancelled','on_hold','reopened','closed')),
  amount bigint,
  message text,
  created_at timestamptz not null default now()
);

-- Demand
create table public.listing_views (
  listing_id uuid not null references public.listings(id),
  viewer text not null,                            -- account id, or a random id kept on the device
  day date not null default current_date,
  primary key (listing_id, viewer, day)
);
create table public.saves (
  listing_id uuid not null references public.listings(id),
  user_id uuid not null references public.profiles(id),
  created_at timestamptz not null default now(),
  primary key (listing_id, user_id)
);

-- Notifications and audit trail
create table public.notifications (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id),
  kind text not null,
  body text not null,
  link text,
  channels text[] not null default '{app}',        -- email and SMS land here until a provider is connected
  read boolean not null default false,
  created_at timestamptz not null default now()
);
create table public.audit_log (
  id bigint generated always as identity primary key,
  at timestamptz not null default now(),
  actor_id uuid,
  actor_role text not null,                        -- seller, buyer, garage, admin, system
  entity text not null,                            -- listing, vehicle, review, deal, garage, member, account, setting, conversation
  entity_id text not null,
  action text not null,
  detail jsonb not null default '{}'::jsonb        -- {"before":...,"after":...} or other facts, never message text
);
create index audit_entity on public.audit_log (entity, entity_id);
