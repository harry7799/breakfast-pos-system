# Breakfast Store System (POS + KDS + Inventory + Analytics)

This project is a deployable MVP for Zeabur with:

- Front POS ordering
- Real-time kitchen board (KDS) via WebSocket
- Inventory and stock movement management
- Business analytics dashboard
- Role-based login and permissions
- Optional no-password mode (`AUTH_DISABLED=true`)

## Stack

- Backend: FastAPI + SQLAlchemy
- Realtime: WebSocket (`/ws/events`)
- Database: SQLite (local) or PostgreSQL (Zeabur)
- Frontend: Vanilla HTML/CSS/JS (`/pos`, `/kds`, `/admin`)

## Run locally

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
alembic upgrade head
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

If you are on Windows and see `PermissionError: [WinError 5]` with `--reload`, run without `--reload`.

If your local database already existed before Alembic was added, just run migration:

```bash
alembic upgrade head
```

Open:

- `http://localhost:8000/`
- `http://localhost:8000/pos`
- `http://localhost:8000/kds`
- `http://localhost:8000/admin`
- `http://localhost:8000/docs`

## Default accounts (seed)

Change these in production.

- `staff1 / staff1234`
- `kitchen1 / kitchen1234`
- `manager1 / manager1234`
- `owner1 / owner1234`

## Authentication switch

- `AUTH_DISABLED=true` (default): no login/password required for frontend pages and API.
- `AUTH_DISABLED=false`: enforce normal JWT login and role checks.

## Roles

- `staff`: create/pay orders, view menu and order list
- `kitchen`: view orders and update order status
- `manager`: inventory + analytics + menu management
- `owner`: all manager permissions + user management

## Main API

- `POST /api/auth/login`
- `GET /api/auth/me`
- `GET /api/auth/users` (owner)
- `POST /api/auth/users` (owner)
- `GET /api/menu/items`
- `POST /api/menu/items` (manager/owner)
- `PUT /api/menu/items/{id}` (manager/owner)
- `GET /api/menu/items/{id}/recipe` (manager/owner)
- `PUT /api/menu/items/{id}/recipe` (manager/owner)
- `GET /api/menu/combos`
- `GET /api/menu/combos/{id}`
- `POST /api/menu/combos` (manager/owner)
- `PUT /api/menu/combos/{id}` (manager/owner)
- `GET /api/orders`
- `POST /api/orders`
- `POST /api/orders/{id}/pay`
- `POST /api/orders/{id}/amend` (staff/manager/owner)
- `POST /api/orders/{id}/status`
- `GET /api/inventory/ingredients` (manager/owner)
- `GET /api/inventory/low-stock` (kitchen/manager/owner)
- `POST /api/inventory/movements` (manager/owner)
- `GET /api/analytics/overview` (manager/owner)
- `GET /api/audit/logs` (manager/owner)
- `WS /ws/events?token=...`

## Core flow

1. POS creates an order.
2. Order event is pushed to KDS immediately.
3. KDS updates status (`pending -> preparing -> ready -> completed`).
4. Paid order auto-deducts inventory by recipe.
5. Dashboard reads analytics overview data.

## Stability safeguards

- Auto-pay order checks stock first; order is rejected with `409` if inventory is insufficient.
- Inventory deduction is transactional, preventing partial stock updates.
- Cancelling a paid order auto-restores recipe inventory (`CANCEL:<order_number>` movement reference).
- Amending a paid order adjusts inventory by delta only (`AMEND:<order_number>` movement reference).
- Frontend API requests include timeout + retry for GET endpoints.
- WebSocket reconnect uses exponential backoff to reduce reconnect storms.
- Login rate limit supports Redis-backed counters for multi-instance deployment (`REDIS_URL`), keyed by `IP + username`.
- Role-sensitive actions are captured in `audit_logs` for traceability.

## Database migration (Alembic)

- Create migration: `alembic revision --autogenerate -m "message"`
- Apply migration: `alembic upgrade head`
- Roll back one revision: `alembic downgrade -1`

## Zeabur deployment

### Git Service

1. Push this repo to GitHub.
2. Create one Zeabur project and add Git service.
3. Start command:
   - `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT`
4. Set env vars:
   - `DATABASE_URL` (Zeabur PostgreSQL connection string)
   - `REDIS_URL` (optional but recommended for distributed login rate limit)
   - `APP_ENV=production`
   - `AUTH_DISABLED=false` (recommended in production)
   - `SECRET_KEY=<long-random-string>`
   - `TOKEN_EXPIRE_MINUTES=720`
   - `LOGIN_RATE_WINDOW_SECONDS=60`
   - `LOGIN_RATE_MAX_ATTEMPTS=10`
   - `TRUST_PROXY_HEADERS=true` (enable when running behind a trusted reverse proxy)
   - `CORS_ORIGINS=<your-domain>`

### Docker Service

`Dockerfile` is included.

## Test

```bash
pytest -q
```

## Batch import menu JSON

Use the prepared payload (`imports/menu_202602_api_payload.json`) to upsert menu items and combo rules via API:

```bash
python scripts/import_menu_api.py --base-url http://127.0.0.1:8000 --username manager1 --password manager1234
```

Dry run (no write):

```bash
python scripts/import_menu_api.py --dry-run
```

Notes:

- `menu_items` are upserted by `name`.
- `combo_rules` are upserted by `code`.

## Next extensions

1. Redis pub/sub for multi-instance WebSocket fanout
2. Supplier and purchase order management
3. Multi-store support with `store_id`
4. Audit logs for sensitive changes
# 081-system
