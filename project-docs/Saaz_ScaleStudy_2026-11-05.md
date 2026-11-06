# Saaz scale study: Buy cars at 24 to 10,000 cars (5 Nov 2026)

Run on the local stack with `tests/scale_browse_study.py` (results in `tests/scale_results.json`). Live Saaz today: 0 live cars (2 awaiting review, 1 draft).

Profiles: phone_4g = 390 px, CPU 4x slower, about 6.4 Mbit/s with 150 ms delay, list sent uncompressed (worst case). phone_cpu = same phone, no network limit. laptop = 1280 px, no limits.

| Live cars | List size raw / compressed | Database | Phone 4G, first open | Phone, no network limit | Laptop | Admin, Cars shows |
|---|---|---|---|---|---|---|
| 24 | 22 KB / 2 KB | 4 ms | 0.7 s | 0.5 s | 0.2 s | 24 |
| 100 | 93 KB / 8 KB | 8 ms | 0.8 s | 0.5 s | 0.2 s | 100 |
| 500 | 466 KB / 37 KB | 42 ms | 1.2 s | 0.5 s | 0.2 s | 500 |
| 1,000 | 0.9 MB / 74 KB | 68 ms | 1.9 s | 0.6 s | 0.2 s | 500 |
| 2,500 | 2.3 MB / 185 KB | 167 ms | 3.8 s | 1.0 s | 0.4 s | 500 |
| 5,000 | 4.6 MB / 370 KB | 349 ms | 7.1 s | 1.1 s | 0.5 s | 500 |
| 10,000 | 9.3 MB / 738 KB | 675 ms | 14.8 s | 1.8 s | 1.0 s | 500 |

Held at every size (Certain): 24 cards a page, about 1,050 page elements, pager stays 5 items wide (page 417 of 417 fits a phone), no sideways scroll, last page correct, make filter correct, Back returns to the same spot, no script errors. Memory 3 MB at 24 cars, 9 MB at 10,000.

## Milestones

1. 501 cars: Admin, Cars shows only 500 and says "500 cars" (Certain: `admin_listings` has `limit 500`).
2. 1,001 cars: visitors would see only 1,000 and the count would say "1000 cars" (Likely: Supabase's default Max rows is 1,000; reproduced locally with that setting. Check Settings, API, Max rows).
3. About 2,500 cars: a phone on a slow link waits about 4 s for Buy cars, and every return after 20 seconds fetches the whole list again.
4. 5,000 to 10,000 cars: 7 to 15 s on a slow phone link uncompressed; about 2 to 3 s if Supabase compresses (Likely, not measured live: the proxy here blocks the live API).

Cause: the home page and Buy cars download every live car, then show 24. Fix before 1,000 cars: the database returns one page (24 cars) plus the total and the filter choices.
