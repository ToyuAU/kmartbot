# KmartBot v2

Automated retail checkout bot targeting **Kmart Australia** (kmart.com.au). Built to cop limited-edition items the moment they drop. Runs locally on macOS. Architecture is intentionally extensible — adding a new site means creating a new `backend/sites/<site>/` module.

---

## How to Run

```bash
cd /Users/bayli/Desktop/kmartbot
source .venv/bin/activate

# Dev (backend hot-reload + Vite dev server):
python run.py --reload          # backend on http://localhost:8080
cd dashboard && npm run dev     # dashboard on http://localhost:5173

# Production (build UI, serve everything from :8080):
python run.py --build-ui
```

The dashboard proxies `/api` and `/ws` to the backend in dev mode (configured in `dashboard/vite.config.ts`).

---

## Project Structure

```
kmartbot/
├── backend/
│   ├── main.py                  # FastAPI app + lifespan (DB init, EventBus wiring)
│   ├── database.py              # aiosqlite setup, schema + idempotent ALTER migrations
│   ├── config.py                # Loads config.json into a Pydantic Settings singleton
│   ├── api/
│   │   ├── tasks.py             # CRUD + start/stop controls for tasks
│   │   ├── profiles.py          # CRUD for shipping/billing profiles
│   │   ├── cards.py             # CRUD for payment cards
│   │   ├── settings.py          # Key-value settings (persisted to SQLite)
│   │   └── ws.py                # WebSocket endpoint + _broadcast() function
│   ├── core/
│   │   ├── event_bus.py         # Async pub/sub — bots publish, WS hub subscribes
│   │   ├── task_manager.py      # asyncio.Task registry — start/stop/cancel
│   │   └── task_runner.py       # Runs one task: loads data, wires log_fn, persists results
│   ├── sites/
│   │   ├── base.py              # Abstract BaseSite — all site bots implement run() → order_number
│   │   └── kmart/
│   │       ├── bot.py           # KmartBot — orchestrates the checkout flow (watch mode + burst)
│   │       ├── graphql.py       # All GraphQL payload builders + KMART_GRAPHQL URL
│   │       ├── payment.py       # Paydock tokenisation + full 3DS form chain + polling
│   │       └── akamai.py        # Akamai bypass (hyper_sdk: SBSD + sensor posting)
│   ├── services/
│   │   ├── http_client.py       # tls_client Chrome 146 wrapper — one instance per task
│   │   ├── proxy_manager.py     # Loads data/proxies.txt, returns random proxy dict
│   │   └── discord.py           # Webhook POSTs (success / failure / 3DS challenge)
│   └── models/
│       ├── task.py              # Task DB model + Pydantic schema + TaskStatus constants
│       ├── profile.py           # Profile model
│       └── card.py              # Card model (stored plain — local only)
├── dashboard/                   # Vite + React 18 + TypeScript
│   └── src/
│       ├── api/client.ts        # Typed fetch wrapper for all REST endpoints
│       ├── store/index.ts       # Zustand: WS state, live task statuses, per-task logs (dedup'd)
│       ├── hooks/useWebSocket.ts # Single WS connection with auto-reconnect + event dispatch
│       ├── components/
│       │   ├── Sidebar.tsx      # Nav + WS connection indicator
│       │   ├── TaskCard.tsx     # Task row: status badge, step label, start/stop/delete, log drawer
│       │   ├── TaskForm.tsx     # Create/edit task modal (incl. watch_mode toggle)
│       │   ├── LogStream.tsx    # Virtualised per-task live log list
│       │   └── StatusBadge.tsx  # Colour-coded status pill
│       └── pages/
│           ├── Tasks.tsx        # Main page — task list + start-all/stop-all
│           ├── Profiles.tsx     # Address profile CRUD
│           ├── Cards.tsx        # Payment card CRUD
│           └── Settings.tsx     # Webhooks, email generation config, toggles
├── data/
│   ├── kmartbot.db              # SQLite database (auto-created, gitignored)
│   ├── proxies.txt              # One proxy per line (gitignored — contains credentials)
│   └── staff_codes.txt          # Staff discount card numbers (gitignored)
├── config.json                  # Runtime config (gitignored — contains webhook URLs)
├── .gitignore                   # Excludes .venv, node_modules, dist, db, secrets, old kmartbot-main/
├── requirements.txt
└── run.py                       # Single-command startup
```

---

## Kmart Checkout Flow

Each task runs as an `asyncio.Task` driven by `backend/sites/kmart/bot.py`. `asyncio.CancelledError` propagates cleanly on stop — stopping a task at any step is safe.

Two flow variants depending on the task's `watch_mode` flag:

### Standard flow (`watch_mode=false`)
Runs top-to-bottom; used for "cart it now" attempts. Steps 1–4 are each wrapped in `_with_retry` (3 attempts, exponential backoff 1s → 2s → 4s + jitter). Payment (steps 7–10) is wrapped in a single **checkout burst** that retries the whole token → 3DS → submit chain up to 10 times (see below).

### Watch flow (`watch_mode=true`)
Inserts a `WATCHING_STOCK` step between 3 and 4. After ATC, the bot parks on a poll of `refreshMyCart.bagStockAvailability.BUCKET_INFO.HOME_DELIVERY[0].bucketType` every 3–8s (jittered) until the bucket flips off `"OOS"`. Can run for days. If five consecutive polls error, it rebuilds the cart (re-solve Akamai → create → ATC) and resumes. The moment stock drops, the flow continues into steps 4–10 normally.

| Step | File | What happens |
|------|------|-------------|
| 1. `SOLVING_AKAMAI` | `akamai.py` | hyper_sdk generates sensor data, posts 3–5 times to kmart.com.au Akamai endpoint until `_abck` cookie is valid. SBSD challenge handled if present. |
| 2. `CREATING_CART` | `graphql.py` | `createMyBag` mutation → returns `cart_id` + `cart_version`. |
| 3. `ADDING_TO_CART` | `graphql.py` | `updateMyBag` mutation with SKU + quantity. Handles quantity-limit errors by retrying with the API's reported max. |
| 3b. `WATCHING_STOCK` *(watch mode only)* | `bot.py` | Polls `refreshMyCart` (`refresh_bag_with_availability`) until `HOME_DELIVERY` bucket != `OOS`. Auto-rebuilds cart on sustained errors. |
| 4. `SETTING_SHIPPING` | `graphql.py` | `updateMyBagWithoutBagStockAvailability` — sets shipping + billing address, item shipping address, `reviewConsent=false`, `kmailSignup=false`. Email is generated via catch-all or Gmail `+alias` based on config. |
| 5. `APPLYING_STAFF_CODE` | `bot.py` | `ApplyTeamMemberDiscount` mutation. Codes loaded from `data/staff_codes.txt` as a rotating deque — each code is used then rotated to the back. Skipped if file is empty or both task + global toggles are off. |
| 6. `APPLYING_FLYBUYS` | `bot.py` | `updateMyBagWithoutBagStockAvailability` with `flyBuysNumber`. Skipped if profile has no Flybuys number. |
| 7. `TOKENIZING_CARD` | `payment.py` | POST to `https://api.paydock.com/v1/payment_sources/tokens` with raw card data → one-time token. Header: `x-user-public-key: 5b12b8af610ca9e784c0f86ab5b9657e66fadbc0`. |
| 8. `CREATING_3DS_TOKEN` | `payment.py` | `create3DSToken` GraphQL mutation → base64url JWT → decoded to `tokenData` dict (`charge_3ds_id`, `initialization_url`, `xAccessToken`). |
| 9. `PROCESSING_3DS` | `payment.py` | GET gpayments.net init URL → POST browser fingerprint form → follow form chain → poll `https://api.paydock.com/v1/charges/standalone-3ds/process` until `status == "success"`. If `status == "pending"` with a challenge URL, a Discord challenge webhook is sent. |
| 10. `SUBMITTING_ORDER` | `bot.py` | `chargePayDockWithToken` mutation with `charge_3ds_id` → `orderNumber`. |

### Checkout burst (steps 7–10)

Paydock tokens are single-use but can be requested infinitely. `_checkout_burst()` exploits this: it runs tokenise → 3DS → submit, and on any failure that isn't an unrecoverable cart error, it waits (exponential backoff, capped 30s + jitter) and regenerates the whole chain. Up to 10 attempts. This is "spray and pray" — the right strategy once stock is live.

Unrecoverable errors (cart expired / not found / invalid) short-circuit the burst, the task fails, and Discord gets a failure webhook.

---

## Stock Monitoring Strategy

Two distinct availability signals on kmart.com.au, per community guidance:

1. **Cartability** — can the item be added to a cart at all? "In-store only" items can't, and this is a hard gate.
2. **Shippability** — even if cartable, home delivery may be OOS. The truth lives in `bagStockAvailability.BUCKET_INFO.HOME_DELIVERY[0].bucketType` on `refreshMyCart`. `"OOS"` means not shippable; anything else means checkout will succeed.

There is **no separate SKU monitor service**. Availability is checked per-task via `watch_mode`:

- Enable "Watch mode" on a task, press start.
- Task solves Akamai once, creates a cart, ATCs the SKU, then polls the shipping signal until stock drops.
- The moment it does, the same task seamlessly proceeds through shipping → staff code → Flybuys → checkout burst.
- Can be left running for days/weeks. Stopping the task cancels cleanly at the next poll.

This is cheaper (one Akamai solve, reused cart session) and more reliable (real shipping signal, not the lying `isAvailable` flag) than a standalone poller.

---

## API Endpoints

Base URL: `http://localhost:8080`. No authentication — local-only system.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/tasks` | List all tasks |
| `POST` | `/api/tasks` | Create task (body incl. `watch_mode: bool`) |
| `PATCH` | `/api/tasks/{id}` | Update task |
| `DELETE` | `/api/tasks/{id}` | Delete task (stops if running) |
| `POST` | `/api/tasks/start-all` | Start all idle/failed/stopped tasks |
| `POST` | `/api/tasks/stop-all` | Cancel all running tasks |
| `POST` | `/api/tasks/{id}/start` | Start a specific task |
| `POST` | `/api/tasks/{id}/stop` | Stop a specific task |
| `GET` | `/api/tasks/{id}/logs` | Fetch historical logs (limit=200) |
| `GET/POST` | `/api/profiles` | List / create profiles |
| `PATCH/DELETE` | `/api/profiles/{id}` | Update / delete profile |
| `GET/POST` | `/api/cards` | List / create cards |
| `PATCH/DELETE` | `/api/cards/{id}` | Update / delete card |
| `GET` | `/api/settings` | Get all settings |
| `PUT` | `/api/settings` | Save settings (key-value dict) |
| `WS` | `/ws` | WebSocket — real-time events |

Bulk routes (`/start-all`, `/stop-all`) are defined **before** `/{task_id}` in `tasks.py` to prevent FastAPI matching the literal strings as UUIDs.

---

## WebSocket Event Protocol

The dashboard connects to `ws://localhost:8080/ws`. All events are JSON; bots publish to the EventBus, a single `_broadcast` subscriber fans out to every connected client.

```jsonc
// Task status changed (also fired when step changes mid-run)
{ "type": "task_update", "task_id": "uuid", "status": "running", "step": "WATCHING_STOCK" }

// Task completed successfully
{ "type": "task_update", "task_id": "uuid", "status": "success", "order_number": "KM-12345678" }

// Task failed
{ "type": "task_update", "task_id": "uuid", "status": "failed", "error_message": "..." }

// Log line from a running task
{ "type": "task_log", "task_id": "uuid", "level": "info|warn|error|success",
  "message": "...", "step": "ADDING_TO_CART", "ts": "ISO8601" }

// Keep-alive (every 30s, per-client)
{ "type": "ping" }
```

The frontend store deduplicates `task_log` events against the last line (same `ts + message + step`) — protects against React StrictMode dev double-mounting or uvicorn reload repeat-subscriptions.

---

## Database Schema

SQLite at `data/kmartbot.db`. Created automatically on first run by `backend/database.py`. `ALTER TABLE` migrations run inside `init_db()` for columns added after v1 (e.g. `watch_mode`) — safe to ship against existing DBs.

```sql
profiles   (id, name, first_name, last_name, email, mobile, address1, address2,
            city, state, postcode, country, flybuys, created_at)
cards      (id, alias, cardholder, number, expiry_month, expiry_year, cvv, created_at)
tasks      (id, name, site, sku, profile_id, card_ids[JSON], quantity,
            use_staff_codes, use_flybuys, watch_mode,
            status, error_message, order_number, created_at, updated_at)
task_logs  (id, task_id, level, message, step, ts)
settings   (key, value)
```

Task statuses: `idle` → `running` → `success | failed | stopped`.

Cards are stored in plain text — acceptable because the DB is local-only and never shipped. `.gitignore` excludes the DB file.

---

## Config (`config.json`)

```jsonc
{
  "webhook_url": "",           // Discord webhook for success/failure notifications
  "challenge_webhook_url": "", // Discord webhook for 3DS challenge alerts (falls back to webhook_url)
  "catchall_domain": "",       // Domain for generated order emails (e.g. "yourdomain.com")
  "use_gmail_spoofing": false, // Use Gmail sub-address trick for order emails
  "gmail_spoofing_email": "",  // Base Gmail address (e.g. "you@gmail.com")
  "use_staff_codes": true,     // Globally enable staff discount codes
  "precheck_shipping": false,  // Reserved — not currently wired to any step
  "rotate_proxy_on_bot_detection": false,
  "dashboard_port": 8080
}
```

Settings can also be saved via the dashboard (`/api/settings`), which stores them in SQLite and overrides `config.json` values at runtime.

`config.json` is gitignored because it holds webhook URLs and personal email. Commit a sanitised `config.example.json` if you want a template in the repo.

---

## Key External Services

| Service | URL | Purpose |
|---------|-----|---------|
| Kmart GraphQL API | `https://api.kmart.com.au/gateway/graphql` | All cart/checkout/refresh mutations |
| Paydock tokenisation | `https://api.paydock.com/v1/payment_sources/tokens` | Card tokenisation |
| Paydock 3DS process | `https://api.paydock.com/v1/charges/standalone-3ds/process` | 3DS status polling |
| Akamai sensor endpoint | `https://www.kmart.com.au/<script_path>` | Bot detection bypass |
| hyper_sdk API | `api.hyper-solutions.dev` | Generates Akamai sensor + SBSD payloads |
| gpayments.net | `tokenData.initialization_url` | 3DS authentication iframe / form chain |

**Paydock public key** (hardcoded, Kmart's): `5b12b8af610ca9e784c0f86ab5b9657e66fadbc0`
**hyper_sdk API key** (hardcoded in `akamai.py`): `88e24b72-251d-4359-85ac-c0c301db5f38`

---

## Adding a New Site

1. Create `backend/sites/<site>/bot.py` with a class extending `BaseSite`.
2. Implement `async def run(self) -> str` — must return an order number on success, raise on failure. Emit logs via `self._log(level, message, step)` for live UI streaming.
3. Register it in `backend/core/task_runner.py` `_make_bot()` factory.
4. Set `task.site = "<site>"` when creating tasks.

The rest (task runner, event bus, WebSocket, dashboard, staff codes, Discord webhooks) works automatically. Watch mode is Kmart-specific right now — to support it on another site, follow the `_watch_stock()` pattern in `kmart/bot.py`.

---

## Tech Stack

**Backend**
- Python 3.13 / FastAPI + uvicorn
- aiosqlite (async SQLite)
- tls_client (Chrome 146 TLS fingerprinting, wrapped in `asyncio.to_thread`)
- hyper_sdk (Akamai bypass — SBSD + sensor generation)
- aiohttp (Discord webhooks)
- BeautifulSoup4 (3DS form parsing)
- Pydantic v2

**Dashboard**
- Vite 8 + React 18 + TypeScript
- Tailwind CSS v4 (via `@tailwindcss/vite`)
- Zustand (global state: WS connection, live task statuses, logs)
- TanStack Query (REST API calls with caching)
- React Router v6
- lucide-react (icons)

---

## Data Files

| File | Format | Purpose |
|------|--------|---------|
| `data/proxies.txt` | `host:port` or `host:port:user:pass` or `user:pass@host:port` | Proxy pool. Loaded once on first use. Empty file = no proxy. |
| `data/staff_codes.txt` | One code per line (blank lines + `#` comments ignored) | Staff discount card numbers. Loaded into a module-level rotating deque at first use — each code is used then rotated to the back. |
| `data/kmartbot.db` | SQLite | All persistent data. Auto-created. |

All three are `.gitignored`.

---

## Known SKU Quantity Limits

Some SKUs have per-order max quantities enforced by Kmart. Known limits live in `SKU_QUANTITY_MAP` in `backend/sites/kmart/graphql.py`. When the API returns a quantity-limit error for an unknown SKU, the bot parses the reported max out of the error message and retries ATC with that value.

---

## Development Notes

- **tls_client is synchronous** — all HTTP calls are wrapped in `asyncio.to_thread()` (in `http_client.py` and `akamai.py`) so they don't block the event loop.
- **One HttpClient per task** — never share sessions across tasks; each has its own cookie jar and proxy.
- **Staff codes** are a module-level deque shared across all KmartBot instances — coroutine-safe for simple popleft/append rotation.
- **EventBus subscribers** receive all events; the frontend filters by `task_id`. Exceptions inside a handler are swallowed to avoid one dead client killing a task.
- **Log dedup** — the Zustand store drops `task_log` entries that match the previous line on `ts + message + step`. React StrictMode's dev double-mount briefly opens two WebSockets, which would otherwise duplicate every log line.
- **No authentication on the API** — local-only system, no login needed. If you ever expose this beyond localhost, add auth first.
- **`/api/tasks/start-all` and `/api/tasks/stop-all` must be defined before `/{task_id}` routes** in `tasks.py` to prevent FastAPI matching the literal strings as UUIDs.
- **Discord webhooks** — success / failure / 3DS challenge are three distinct message templates in `services/discord.py`. Challenge webhook falls back to the main webhook URL if unset.
- **Stop semantics** — `task_manager.stop(id)` cancels the underlying asyncio task; the runner catches `CancelledError`, marks the task `stopped`, and emits a final `task_update` event. Safe at any step, including mid-poll in watch mode.
- **Reload gotcha** — `python run.py --reload` spawns a new process per reload, so module-level state (`_subscribers`, staff code deque) resets cleanly. No double-subscription risk in prod; dev dedup is still worthwhile because of StrictMode.
