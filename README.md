# FixIT Hub

**Diagnose and fix PC problems yourself.**

A server-rendered technical support knowledge base for Windows 10 and 11. A visitor
identifies a fault, learns what is causing it, and works through a fix without
opening a support ticket.

| | |
| --- | --- |
| Guides | 43 markdown troubleshooting articles across 5 categories |
| Stop codes | 92 BSOD bugchecks, searchable by name, hex or decimal |
| Wizards | 8 JSON-driven decision trees with back/restart |
| Network tools | 5 server-side tools, all behind SSRF validation |
| Scripts | 5 read-only `.bat` / `.ps1` diagnostics, shown in full before download |
| Admin | Full panel: moderation, SEO overrides, ads, audit log, backup/restore, TOTP 2FA |
| Runtime | No frontend framework, no client-side JavaScript requirement |

---

## Table of contents

- [Features](#features)
  - [Knowledge base](#knowledge-base)
  - [BSOD diagnosis](#bsod-diagnosis)
  - [Guided troubleshooting](#guided-troubleshooting)
  - [Hardware, drivers and scripts](#hardware-drivers-and-scripts)
  - [Network tools](#network-tools)
  - [Reader accounts and community](#reader-accounts-and-community)
  - [Admin panel](#admin-panel)
  - [Operations and SEO](#operations-and-seo)
- [Tech stack](#tech-stack)
- [Requirements](#requirements)
- [Installation](#installation)
  - [Local setup](#local-setup)
  - [Docker](#docker)
- [Usage](#usage)
  - [Seeding content](#seeding-content)
  - [Configuration](#configuration)
  - [JSON APIs](#json-apis)
  - [Authoring content](#authoring-content)
  - [Running the tests](#running-the-tests)
  - [Browser audits](#browser-audits)
  - [Deployment](#deployment)
- [Project structure](#project-structure)
- [Security model](#security-model)
- [Accessibility and SEO](#accessibility-and-seo)
- [License](#license)

---

## Features

Everything is server-rendered with Jinja2. There is no client-side framework and
no page requires JavaScript to work — `site.js` and `ask-widget.js` are
progressive enhancement only.

### Knowledge base

| Feature | Route | Notes |
| --- | --- | --- |
| Home page | `/` | Category cards, popular fixes, recent guides, popular stop codes |
| Full-text search | `/search` | Guides and stop codes in one result set, with typeahead at `/api/search/suggest` |
| Article library | `/articles` | 43 guides, filterable by category, difficulty and free text |
| Category pages | `/category/<slug>` | `hardware`, `network`, `windows`, `drivers`, `bsod` |
| Article detail | `/articles/<slug>` | Rendered markdown, table of contents, copy buttons, helpful/not-helpful vote |
| About / Privacy | `/about`, `/privacy` | What the site stores, why, and how to have it deleted |

### BSOD diagnosis

| Feature | Route | Notes |
| --- | --- | --- |
| Stop code index | `/bsod` | All 92 codes with meaning, causes and repair steps |
| Stop code lookup | `/bsod/lookup` | Resolves a name, `0x1A` or a decimal to a single code |
| Stop code detail | `/bsod/<NAME>` | Repair guide plus related guides |
| Minidump analyzer | `/bsod/analyze` | Parses the bugcheck code straight out of an uploaded `.dmp` |
| Dump limits endpoint | `/api/dump/validate` | Reports the size cap and accepted signatures, so the UI never hard-codes them |
| Stop code feedback | `POST /bsod/<name>/feedback` | Helpful / not helpful votes, stored per stop code |

### Guided troubleshooting

| Feature | Route | Notes |
| --- | --- | --- |
| Wizard index | `/wizards` | 8 symptom-driven decision trees |
| Wizard step | `/wizards/<id>` | Progress, per-step options, terminal step pointing at the relevant guide |
| Back / restart | `/wizards/<id>/back`, `/wizards/<id>/restart` | Traversal state lives in the signed session cookie |

Trees are plain JSON in `data/wizards/`, so a new wizard is a new file, not a code
change.

### Hardware, drivers and scripts

| Feature | Route | Notes |
| --- | --- | --- |
| Hardware topics | `/hardware` | RAM, storage, temperatures, PSU, beep codes, battery, SSD/RAM upgrades, sleep faults |
| Hardware topic | `/hardware/<slug>` | Blurb, linked article, and any matching diagnostic script |
| Driver help | `/drivers`, `/drivers/<vendor>` | NVIDIA, AMD, Intel, Realtek, Lenovo, MSI, ASUS, Microsoft, DDU |
| Device Manager codes | `/drivers` | Yellow-bang explanations with concrete fixes and difficulty ratings |
| Diagnostic scripts | `/scripts`, `/scripts/<slug>` | 5 read-only scripts, each rendered in full with every command explained |

### Network tools

All five execute server-side. Every target is resolved and validated before a
connection is attempted.

| Tool | Page | JSON API |
| --- | --- | --- |
| DNS lookup | `/tools/dns` | `POST /api/dns` |
| Public IP | `/tools/ip` | — (server-rendered only) |
| Port check | `/tools/port` | `POST /api/port` |
| HTTP status | `/tools/status` | `POST /api/status` |
| TCP latency | `/tools/latency` | `POST /api/latency` |

Port checks are restricted to a fixed allowlist of 30 common ports
(`ALLOWED_PORTS` in `app/config.py`). Anything else is rejected outright.

### Reader accounts and community

Disabled by default. Enable with `FIXITHUB_ALLOW_REGISTRATION=1`.

| Feature | Route | Notes |
| --- | --- | --- |
| Sign up / log in / out | `/signup`, `/login`, `/logout` | Optional — needed for comments and gated downloads |
| Email verification | `/verify/<token>` | SMTP is optional; an admin can confirm an address by hand |
| Account area | `/account` | Profile, plus real deletion of the account and its comments |
| Moderated comments | `POST /comments` | `pending` → `approved` / `rejected`; never rendered as markdown |
| "Ask us anything" | `POST /api/ask`, `GET /api/ask/<id>` | Anonymous question, answered by a human from `/admin/questions` |

A reader account carries no admin privilege. The admin panel is guarded by a
separate cookie (`fixithub_admin`) and a separate password from the reader cookie
(`fixithub_user`).

### Admin panel

Password-protected, optional TOTP two-factor, and covered by an audit log of every
state-changing action.

| Feature | Route |
| --- | --- |
| Login, optional 2FA step | `/admin`, `/admin/login`, `/admin/login/2fa` |
| Dashboard with counters and trends | `/admin/dashboard` |
| Guide CRUD with markdown preview | `/admin/articles`, `/admin/articles/new`, `/admin/articles/<slug>/edit` |
| Per-article analytics | `/admin/articles/<slug>/analytics` |
| Stop code CRUD | `/admin/stop-codes` |
| Binary and screenshot uploads | `/admin/apps`, `/admin/apps/new`, `/admin/apps/<slug>/edit` |
| Comment moderation queue | `/admin/comments` |
| Question answering | `/admin/questions` |
| Reader account deletion | `POST /admin/users/<id>/delete` |
| Site announcement banner | `/admin/announcement` |
| AdSense settings, units and `ads.txt` | `/admin/ads` |
| Per-page SEO overrides and site defaults | `/admin/seo` |
| Link inventory | `/admin/links` |
| Email send log | `/admin/emails` |
| Audit log of admin writes | `/admin/audit` |
| SQLite backup and restore | `/admin/backup`, `/admin/restore` |
| TOTP enrolment and recovery codes | `/admin/two-factor` |
| Admin password change | `/admin/change-password` |

### Operations and SEO

| Feature | Route |
| --- | --- |
| Health probes | `/healthz`, `/health` |
| XML sitemap | `/sitemap.xml` |
| Robots policy | `/robots.txt` |
| Served `ads.txt` | `/ads.txt` |

Static assets are served from `/static`. The interactive OpenAPI docs are disabled
(`docs_url=None`, `redoc_url=None`, `openapi_url=None`), so the only JSON surface
is the `/api/*` set listed above.

---

## Tech stack

| Layer | Choice |
| --- | --- |
| Web framework | FastAPI (`>=0.115.0`) on Starlette |
| ASGI server | Uvicorn (`>=0.30.0`, `uvicorn[standard]`) |
| Templating | Jinja2 (`>=3.1.4`), server-side rendering only |
| ORM | SQLAlchemy 2.x (`>=2.0.30`), declarative `Mapped` / `mapped_column` |
| Database | SQLite by default (WAL, foreign keys on); PostgreSQL via `psycopg2-binary` |
| Search | SQLite FTS5 with `bm25` ranking, automatic `LIKE` fallback |
| Markdown | `markdown-it-py` (`>=3.0.0`) + `PyYAML` frontmatter |
| HTML sanitising | Hand-written allowlist sanitiser in `app/services/markdown.py` |
| Password hashing | `bcrypt` (`>=4.1.3`) at cost 12 |
| Signed sessions | `itsdangerous` (`>=2.2.0`) via Starlette `SessionMiddleware` |
| DNS | `dnspython` (`>=2.6.1`) |
| HTTP client | `httpx` (`>=0.27.0`) |
| Minidump parsing | `minidump==0.0.24`, with a manual `struct` parser as fallback |
| Forms and uploads | `python-multipart` |
| TOTP | Implemented in `app/services/totp.py` on `hmac` / `hashlib` / `struct` — no `pyotp` |
| Object storage | Supabase Storage REST API via `httpx` (optional), otherwise local disk |
| Styling | Tailwind CSS via CDN plus `app/static/css/site.css` |
| JavaScript | `app/static/js/site.js`, `app/static/js/ask-widget.js` — enhancement only |
| Testing | `pytest` (`>=8.0.0`), 25 test modules, fully offline |
| Browser audits | Node, `lighthouse` + `puppeteer-core` (dev only) |
| Packaging | Multi-stage non-root `Dockerfile`, `docker-compose.yml`, `render.yaml`, Vercel entrypoint at `api/index.py` |

No subprocess is spawned anywhere in the codebase.

---

## Requirements

- **Python 3.11 or newer** — developed on 3.12; the container image is `python:3.12-slim`
- **No database server.** SQLite is a single file.
- **Node.js is optional** and only needed for the browser audit scripts.

---

## Installation

### Local setup

```bash
# 1. Create and activate a virtual environment
python -m venv .venv

# Windows PowerShell
.venv\Scripts\Activate.ps1
# macOS / Linux
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Load the knowledge base and set an admin password
python seed.py --set-admin-password "choose-a-password"

# 4. Run the server
uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000>. The admin panel is at `/admin`.

On Windows, without activating the environment:

```bash
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Bind to all interfaces:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

The `lifespan` hook creates the schema and, on an empty database, auto-seeds all
content — so a fresh clone runs without a manual step.

### Docker

```bash
# Build and run
docker compose up --build

# Then seed and set a password
docker compose exec app python seed.py --set-admin-password "your-password"
```

`docker-compose.yml` requires `FIXITHUB_SECRET_KEY` in the environment or a `.env`
file, mounts named volumes for `/app/data` and `/app/apps_download`, and declares
a healthcheck against `/healthz`. Plain Docker:

```bash
docker build -t fixithub .
docker run -d --name fixithub -p 8000:8000 \
  -e FIXITHUB_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')" \
  -e FIXITHUB_ADMIN_PASSWORD="a-long-password" \
  -v fixithub-data:/app/data \
  -v fixithub-apps:/app/apps_download \
  fixithub
```

The image is multi-stage — dependencies are built into a virtualenv in the builder
and copied into the runtime, so the runtime needs no compiler — and the container
runs as a non-root `fixithub` user.

---

## Usage

### Seeding content

`seed.py` upserts the markdown guides and stop codes, so running it repeatedly is
safe.

```bash
python seed.py                              # load guides and stop codes
python seed.py --reset                      # drop every table first
python seed.py --rebuild-search             # rebuild the FTS5 index
python seed.py --check                      # report what is in the database
python seed.py --no-content                 # stop codes only
python seed.py --set-admin-password "pw"    # hash and store a password
python seed.py --set-admin-password         # prompts instead
```

Guides come from `content/*.md`; stop codes come from `data/bsod_codes.json`. Edit
either and re-run the script. `--reset` destroys view counts and feedback, so
avoid it in production. If `FIXITHUB_ADMIN_PASSWORD_HASH` is set in the
environment, the script warns that it takes priority over the file it just wrote.

### Configuration

Every setting is an environment variable. Defaults are fine for local development.

| Variable | Default | Purpose |
| --- | --- | --- |
| `FIXITHUB_SECRET_KEY` | random per process | Signs sessions and CSRF tokens. **Set this in production** — unset in production mode is a hard boot failure, not a warning. |
| `FIXITHUB_ENV` | unset | Set to `production` to treat the process as a real deployment. Secure cookies also imply production. |
| `FIXITHUB_ADMIN_PASSWORD` | unset | Admin password, hashed on the fly. Convenient for Docker. Only used when `data/admin.json` does not exist. |
| `FIXITHUB_ADMIN_PASSWORD_HASH` | unset | A bcrypt hash. Takes priority over the saved file. |
| `FIXITHUB_DISABLE_2FA` | `0` | `1` is the escape hatch if TOTP enrolment is lost and every recovery code is spent. |
| `FIXITHUB_DATABASE_URL` | `sqlite:///data/fixithub.db` | Any SQLAlchemy URL. Falls back to `POSTGRES_URL`, then `DATABASE_URL`. |
| `FIXITHUB_ALLOW_REGISTRATION` | `0` | `1` accepts reader sign-ups. Off by default, because turning it on means accepting content from strangers. |
| `FIXITHUB_SMTP_HOST` | unset | Verification mail server. Unset means accounts are confirmed by hand. |
| `FIXITHUB_SMTP_PORT` | `587` | `465` uses implicit TLS, anything else attempts STARTTLS. |
| `FIXITHUB_SMTP_USER` / `FIXITHUB_SMTP_PASSWORD` | unset | SMTP credentials. |
| `FIXITHUB_SMTP_FROM` | unset | Envelope sender for verification mail. |
| `FIXITHUB_APPS_DIR` | `apps_download/` | Where admin-uploaded binaries live, with a `screenshots/` subdirectory beside them. Point this at a persistent volume in production. |
| `FIXITHUB_STORAGE_URL` | unset | `https://<project-ref>.supabase.co`. Enables the Supabase Storage backend for `/apps`. |
| `FIXITHUB_STORAGE_KEY` | unset | Supabase **service-role** key, not the anon key. |
| `FIXITHUB_STORAGE_BUCKET` | `fixithub-apps` | Must be a private bucket. |
| `FIXITHUB_SITE_URL` | `http://localhost:8000` | Canonical URLs and the sitemap. |
| `FIXITHUB_DEBUG` | `0` | `1` enables tracebacks and debug logging. |
| `FIXITHUB_SECURE_COOKIES` | `0` | `1` when served over HTTPS. Also enables HSTS and production mode. |
| `FIXITHUB_TRUST_PROXY` | `0` | `1` **only** behind a proxy you control, so `X-Forwarded-For` can be trusted for rate limiting. |
| `FIXITHUB_RATE_LIMIT_MAX` | `10` | Tool requests per window, per IP. |
| `FIXITHUB_RATE_LIMIT_WINDOW` | `60` | Window length in seconds. |
| `FIXITHUB_GITHUB_TOKEN` | unset | Fine-grained token (`Contents: read and write`) for the content mirror. |
| `FIXITHUB_GITHUB_REPO` | unset | `owner/name`, required with the token. |
| `FIXITHUB_GITHUB_BRANCH` | `main` | Mirror target branch. |

Fixed limits, not configurable: 5 MB minidump cap, 50 MB binary cap, 4 MB
screenshot cap, 500-character question limit, 200-character search query limit,
100-character suggestion query limit.

Example production environment:

```bash
export FIXITHUB_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
export FIXITHUB_SITE_URL="https://fixithub.example.com"
export FIXITHUB_SECURE_COOKIES=1
export FIXITHUB_TRUST_PROXY=1
export FIXITHUB_ADMIN_PASSWORD="a-long-password"
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### JSON APIs

The four network-tool endpoints share one response shape —
`{"ok": bool, "data": ..., "error": str}` — where `ok: false` returns HTTP 502 for
an upstream failure and 422 for rejected input. Each accepts a JSON or form body
and is rate limited like the HTML pages. `/api/search/suggest`, `/api/ask` and
`/api/dump/validate` return their own shapes.

```bash
# Typeahead suggestions
curl "http://127.0.0.1:8000/api/search/suggest?q=blue+screen"

# DNS lookup
curl -X POST http://127.0.0.1:8000/api/dns \
  -H 'Content-Type: application/json' \
  -d '{"host": "example.com", "record_type": "A"}'

# Port check (allowlisted ports only)
curl -X POST http://127.0.0.1:8000/api/port \
  -H 'Content-Type: application/json' \
  -d '{"host": "example.com", "port": 443}'

# HTTP status
curl -X POST http://127.0.0.1:8000/api/status \
  -H 'Content-Type: application/json' \
  -d '{"url": "https://example.com"}'

# TCP latency
curl -X POST http://127.0.0.1:8000/api/latency \
  -H 'Content-Type: application/json' \
  -d '{"host": "example.com", "port": 443}'

# Ask a question. The reply token is returned once; keep it to poll for an answer.
curl -X POST http://127.0.0.1:8000/api/ask \
  -H 'Content-Type: application/json' \
  -d '{"prompt": "My PC blue screens with CRITICAL_PROCESS_DIED. What should I check?"}'

curl "http://127.0.0.1:8000/api/ask/<id>?token=<token>"

# Minidump upload limits and accepted signatures
curl http://127.0.0.1:8000/api/dump/validate

# Analyze a minidump (POST the file to the analyzer form)
curl -F "dump_file=@C:/Windows/Minidump/091120-14478-01.dmp" \
  http://127.0.0.1:8000/bsod/analyze

# Health check -> "ok", or 503 "unhealthy"
curl http://127.0.0.1:8000/healthz
```

### Authoring content

Guides are markdown files in `content/`. Editing one and re-running
`python seed.py` is the entire workflow.

```markdown
---
title: Fix high CPU and GPU temperatures
category: hardware          # hardware | network | windows | drivers | bsod
tags: [temperature, fan, thermal paste]
difficulty: moderate        # easy | moderate | hard | advanced
os_version: Windows 10/11
featured: true
---

Opening paragraph, used as the summary when the frontmatter does not set one.

## A heading becomes a table of contents entry

Commands go in fenced blocks, which get a copy button:

```text
DISM /Online /Cleanup-Image /RestoreHealth
```

Warnings are callouts with a marker:

> [!WARNING]
> This step erases your data.
```

The renderer recognises `> [!WARNING]`, `> [!DANGER]`, `> [!TIP]`, `> [!NOTE]` and
`> [!IMPORTANT]` inside blockquotes. Editing an article in `/admin` writes the
markdown back to `content/`, rebuilds the search index and keeps a `.bak` copy.

Stop codes live in `data/bsod_codes.json`. Wizards are JSON decision trees in
`data/wizards/`; each step offers options, and a terminal step points at the
relevant guide.

### Running the tests

```bash
pytest -q
```

Everything runs offline against a temporary SQLite database, a temporary admin hash
file and a temporary upload directory, so a test run never touches your own data.
`conftest.py` also resets every rate limiter and the login lockout between tests.

| Area | Covered by |
| --- | --- |
| Stop codes, minidump signatures, parsing | `test_bsod.py` |
| SSRF refusal of private and reserved ranges, allowlists, request pinning, TLS SNI | `test_validation.py` |
| Sliding window behaviour, thread safety, HTTP limits, login throttling | `test_rate_limit.py` |
| Admin login, CSRF, hashing, article and stop code CRUD, path traversal defence | `test_admin.py` |
| Markdown sanitising, frontmatter, page status codes, SEO and security headers | `test_pages.py` |
| bcrypt hashing, cached admin hash, login lockout, IP sanitising | `test_security.py` |
| Registration, email validation, password rules, session revocation, account deletion, the reader/admin boundary | `test_accounts.py` |
| Comment moderation, escaping, the gated download | `test_comments.py` |
| Upload validation: extensions, magic bytes, filenames, checksums | `test_apps.py` |
| Admin upload round trip and download headers | `test_apps_routes.py` |
| Question submission, identity, the one-off reply token, admin replies, rate limiting | `test_ask.py` |
| Admin password change paths, throttle, session invalidation | `test_admin_password.py` |
| Postgres URL normalisation and engine construction | `test_database_url.py` |
| Adversarial checks on CSRF, path traversal and access controls | `test_security_recheck.py` |
| TOTP against the RFC's own published vectors | `test_totp.py` |
| Admin two-factor: enrol, wrong code, missing step, single-use recovery codes | `test_two_factor.py` |
| Admin dashboard, pagination, shared shell | `test_admin_dashboard.py`, `test_admin_pagination.py`, `test_admin_shell.py` |
| Ads: no admin-supplied HTML, script only when enabled, never on admin or error pages | `test_ads.py` |
| Admin audit log | `test_audit_log.py` |
| Backup and restore of a real archive | `test_restore.py` |
| Additive schema repair on SQLite and Postgres | `test_schema_drift.py` |
| GitHub content mirror, including save succeeding when the push fails | `test_content_mirror.py` |
| Editing an uploaded app without clearing its stored file metadata | `test_app_edit_roundtrip.py` |

### Browser audits

Optional Node tooling for looking at what a visitor actually sees. Start the server
first, then:

```bash
npm install
npm run audit:shots       # screenshots at three viewports into .screenshots/
npm run audit:measure     # find what overflows the viewport
npm run audit:lighthouse  # headline scores into .lighthouse/
```

All three scripts target `http://127.0.0.1:8000` and expect a local Chrome install.
This exists only to drive Lighthouse and headless Chrome; the site itself is Python.

### Deployment

| Platform | Works as written | Notes |
| --- | --- | --- |
| Docker, systemd, Render, Railway, Fly.io | Yes | A persistent disk keeps SQLite and file-backed markdown edits |
| Vercel | Yes | Serverless ASGI via `api/index.py`. SQLite falls back to `/tmp`, or point at external Postgres |
| Netlify, Cloudflare Pages, AWS Lambda | Needs an adapter | Serverless container platforms |

**PostgreSQL.** `_resolve_database_url` in `app/config.py` reads, in order of
preference, `FIXITHUB_DATABASE_URL`, `POSTGRES_URL`, then `DATABASE_URL`, so the
Supabase and Neon Vercel Marketplace integrations work without manual copying.
Bare `postgresql://` and `postgres://` URLs are rewritten to
`postgresql+psycopg2://`, matching the driver in `requirements.txt`, and
`sslmode=require` is added when a managed URL omits it.

Two PostgreSQL-specific behaviours are worth knowing:

- **Search is unranked.** `fts_available()` probes for SQLite FTS5, throws on
  PostgreSQL, is caught and returns `False`, so search falls back to the `LIKE`
  scan. Results are correct but unranked, with no prefix matching. Fine at this
  content size.
- **Schema changes are additive only.** There is no migration tool. `create_all`
  creates whole tables and `_add_missing_columns` fills gaps with
  `ALTER TABLE ... ADD COLUMN` through SQLAlchemy's inspector, so the same loop
  runs on both backends. Nothing is dropped, renamed or retyped.

For Supabase, use the **connection pooler** string on port `6543` rather than a
direct connection: the pooler collapses SQLAlchemy's per-instance pool into a
small fixed number of real connections, and Supabase direct connections are
IPv6-only while Vercel function egress is often IPv4-only.

**Vercel.** Import the repository at <https://vercel.com/new> and set the variables
above. `api/index.py` is the serverless entrypoint: it exports the FastAPI `app`
instance and installs a small pure-ASGI middleware that restores the original
request path if the platform rewrites it. Without a database configured, Vercel
runs SQLite in `/tmp` and the app auto-seeds all content on cold start — fine for a
read-only demo, but comments, reader accounts and feedback are lost on every
deploy. Anything file-backed behaves as follows:

| Feature | Where it lives on a serverless host |
| --- | --- |
| Admin two-factor | The `admin_two_factor` table. An existing `data/admin_2fa.json` is imported on first read. |
| `/apps` uploads | Supabase Storage via `app/services/storage.py`. With no storage configured the same code writes to `apps_download/`, so Docker and Render are unaffected. |
| Admin article editing | The database row is the record; the markdown is mirrored to GitHub through the Contents API. |
| Admin backup / restore | SQLite only. `_sqlite_db_path()` returns `None` on a non-SQLite URL and the routes say so. On Postgres, use `pg_dump`. |

The **content mirror** is a mirror, not a source of truth: the save is committed to
the database first and the push happens afterwards, so an unreachable GitHub leaves
the article saved and records the failure in the audit log. Each commit triggers a
Vercel rebuild, so point `FIXITHUB_GITHUB_BRANCH` at a branch Vercel does not watch
if frequent edits are a problem. Because the push requires a repo-write token,
give the admin password real strength before enabling it.

CLI deployment:

```bash
npx vercel link
npx vercel env pull .env.local     # optional: confirm what the project sees
npx vercel --prod
```

A committed `.env` file will not reach Vercel — both `.gitignore` and
`.vercelignore` exclude it. The dashboard is the source of truth for these values.

**Render.** `render.yaml` is a ready-made blueprint with a 1 GB disk at
`/app/data`. In the dashboard choose New > Blueprint, point it at the repository,
set `FIXITHUB_SITE_URL` and `FIXITHUB_ADMIN_PASSWORD`, then seed once over SSH:

```bash
render ssh fixithub -- python seed.py --rebuild-search
```

The free plan has no persistent disk, so the database and your admin password are
lost on every deploy.

**Railway.**

```bash
railway init
railway up
railway volume add --mount-path /app/data   # required before the first deploy
railway variables set \
  FIXITHUB_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')" \
  FIXITHUB_SITE_URL="https://your-app.up.railway.app" \
  FIXITHUB_SECURE_COOKIES=1 \
  FIXITHUB_TRUST_PROXY=1 \
  FIXITHUB_ADMIN_PASSWORD="a-long-password"
railway run python seed.py --rebuild-search
```

**systemd and nginx.**

```ini
# /etc/systemd/system/fixithub.service
[Unit]
Description=FixIT Hub
After=network.target

[Service]
User=fixithub
WorkingDirectory=/opt/fixithub
Environment="FIXITHUB_SECRET_KEY=replace-with-a-long-random-string"
Environment="FIXITHUB_SITE_URL=https://fixithub.example.com"
Environment="FIXITHUB_SECURE_COOKIES=1"
ExecStart=/opt/fixithub/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

```nginx
server {
    listen 443 ssl http2;
    server_name fixithub.example.com;

    ssl_certificate     /etc/letsencrypt/live/fixithub.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/fixithub.example.com/privkey.pem;

    # Uploads: 5 MB minidumps, 50 MB binaries, 4 MB screenshots.
    client_max_body_size 52m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

**Multiple workers.** The rate limiter and the login throttle keep their counters
inside the process, so `--workers 4` multiplies every limit by four. Either run a
single worker or replace `app/rate_limit.py` with a shared store before scaling
out. The `Dockerfile`, `docker-compose.yml` and `render.yaml` all pin
`--workers 1` for this reason.

---

## Project structure

```
.
├── app/
│   ├── main.py            # application factory, middleware, error handlers, health probes
│   ├── config.py          # settings, category/vendor tables, port allowlist, DB URL resolution
│   ├── db.py              # engine, sessions, FTS5 search with LIKE fallback, additive migrations
│   ├── models.py          # SQLAlchemy models
│   ├── security.py        # bcrypt, signed cookies, CSRF, client IP, admin login lockout
│   ├── rate_limit.py      # in-process sliding window limiter
│   ├── templates.py       # Jinja2 environment and render helpers
│   ├── deps.py            # shared template context and list queries
│   ├── routes/            # one module per area of the site
│   │   ├── pages.py         # home, categories, about, privacy
│   │   ├── search.py        # search page and suggestions
│   │   ├── articles.py      # article library, detail, feedback
│   │   ├── bsod.py          # stop codes, lookup, minidump analyzer
│   │   ├── wizards.py       # decision-tree traversal
│   │   ├── tools.py         # the five network tools and their JSON APIs
│   │   ├── drivers.py       # vendor pages, Device Manager codes
│   │   ├── scripts.py       # diagnostic script pages and downloads
│   │   ├── hardware.py      # hardware topic index
│   │   ├── apps.py          # public tool pages, screenshots, downloads
│   │   ├── accounts.py      # signup, login, verification, account deletion
│   │   ├── comments.py      # comment submission
│   │   ├── ask.py           # "Ask us anything" endpoints
│   │   ├── admin.py         # the whole admin panel
│   │   └── seo.py           # sitemap.xml, robots.txt, ads.txt
│   ├── services/          # domain logic, no HTTP
│   │   ├── markdown.py      # rendering, allowlist sanitising, TOC, callouts
│   │   ├── content.py       # markdown files and YAML frontmatter
│   │   ├── stopcodes.py     # stop code normalisation, sync, resolution
│   │   ├── wizards.py       # JSON decision trees
│   │   ├── ssrf.py          # input validation and address filtering
│   │   ├── nettools.py      # DNS, public IP, port, HTTP status, latency
│   │   ├── minidump.py      # dump signature checks and bugcheck extraction
│   │   ├── search.py        # full-text search over guides and stop codes
│   │   ├── apps.py          # upload validation, magic bytes, checksums
│   │   ├── storage.py       # local disk or Supabase Storage backend
│   │   ├── accounts.py      # validation, tokens, sessions, verification email
│   │   ├── ads.py           # AdSense settings and tag rendering
│   │   ├── audit.py         # admin audit log
│   │   ├── totp.py          # RFC 6238 TOTP
│   │   ├── github.py        # content mirror to GitHub
│   │   └── scripts_catalog.py
│   ├── templates/         # 66 Jinja templates, including the admin shell
│   └── static/            # css/site.css, js/site.js, js/ask-widget.js, favicon.svg
├── content/               # 43 markdown guides
├── data/
│   ├── bsod_codes.json    # 92 stop codes
│   ├── wizards/           # 8 decision trees
│   └── admin.json         # bcrypt hash, created by seed.py (gitignored)
├── scripts_download/      # the 5 downloadable .bat and .ps1 files
├── apps_download/         # admin-uploaded binaries and screenshots (gitignored, created at runtime)
├── scripts/               # Node browser-audit tooling (dev only)
├── tests/                 # 25 pytest modules plus conftest.py
├── api/index.py           # Vercel serverless entrypoint
├── seed.py                # content seeding and admin password CLI
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── render.yaml
├── vercel.json
└── pytest.ini
```

Database tables, all defined in `app/models.py`:

| Table | Purpose |
| --- | --- |
| `articles`, `article_views` | Guides and their per-day view counters |
| `stop_codes` | BSOD bugcheck reference |
| `feedback`, `search_queries` | Helpful votes and popular search tracking |
| `dump_uploads` | Minidump analysis metadata (never the file bytes) |
| `app_downloads` | Uploaded tool metadata and recorded checksums |
| `users`, `auth_tokens` | Reader accounts and hashed verification/reset/session tokens |
| `comments` | Moderated reader comments |
| `questions` | "Ask us anything" questions and the admin's reply |
| `ad_settings`, `ad_units` | AdSense configuration |
| `seo_overrides`, `site_seo_settings` | Per-page and site-wide SEO metadata |
| `announcements`, `email_log`, `admin_audit_log`, `admin_two_factor` | Site banner, mail log, admin audit trail, TOTP enrolment |

---

## Security model

This is a site about fixing computers, so a few decisions are worth knowing.

### Nothing is executed

No code on this server runs anything on a visitor's PC, and nothing the app serves
runs on this server either. The diagnostic scripts are plain text, shown in full on
their page before download. Uploads are stored and hashed — never extracted,
executed, or inspected beyond their first few header bytes.

The downloadable tools are the exception: they are program binaries an admin
uploads. Every upload records a SHA-256 at upload time, the hash is re-checked on
every view, a mismatch disables the download rather than serving the file, and each
page states the publisher, version and checksum so a visitor can verify what they
received. **Uploads are not scanned by antivirus software.** Only upload a binary
you have checked yourself, and prefer a vendor's own signed download where one
exists.

Screenshots are images an admin attaches so a visitor can recognise a tool. The site
never decodes or rewrites them, only reads the file header to confirm the type. They
are gated behind the same published check as the binaries, served with
`X-Content-Type-Options: nosniff` and
`Content-Security-Policy: default-src 'none'; sandbox`, and SVG is refused on
upload, because a browser would run an SVG as a document rather than display it.

### Minidumps are never stored

The analyzer reads the file in memory, parses the bugcheck header, and discards the
bytes. Uploads are size-capped at 5 MB, and the `PMDMP`, `PAGEDU`, `PAGE` and
`FULL` signatures are checked before any parser sees the data. Only upload metadata
is recorded.

### The network tools cannot scan your network

- Hostnames are resolved and every returned address is checked against the private,
  loopback, link-local, carrier-grade, multicast and reserved ranges. A hostname
  resolving to `127.0.0.1` or `169.254.169.254` is refused outright, including when
  one address in a set is public and another is not.
- Requests then connect to the already-validated IP, with the original `Host` header
  and TLS SNI preserved, which closes the DNS rebinding window between checking and
  connecting.
- Only `http` and `https` are accepted, redirects are not followed, environment proxy
  variables are ignored, and the response body is never read into memory.

### Accounts, sessions and moderation

- Reader sessions live in the database as hashed tokens, so logging out and an admin
  deleting a reader both genuinely end access.
- Passwords are bcrypt-hashed at cost 12. Admin and reader passwords both require at
  least 10 characters. The admin cap is 72 bytes, because bcrypt reads only the
  first 72; reader passwords are capped at 200 characters.
- Only SHA-256 hashes of verification, reset, session and question tokens are
  stored. The raw value is returned exactly once.
- Comments and questions are plain text, escaped by Jinja. There is no path from a
  reader's words to injected markup on an article page.
- New comments are `pending` and visible only to their author and in the admin queue.
- The admin panel is a separate cookie and a separate password. A test asserts that a
  signed-in reader cannot reach it.
- Admin 2FA is TOTP with single-use hashed recovery codes, implemented against
  RFC 6238.
- The admin audit log records every state-changing action, with IPs hashed.

### Content is sanitised

Markdown is rendered and then passed through an allowlist sanitiser, so raw HTML in a
content file cannot inject scripts, event handlers or `javascript:` URLs. Outbound
links get `rel="noopener noreferrer nofollow"`.

### Headers

Every response carries `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
`Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy`,
`Cross-Origin-Opener-Policy: same-origin` and a `Content-Security-Policy` defaulting
to `default-src 'self'`. HSTS is added only when secure cookies are enabled, so HTTP
development is not locked out. When ads are on, the policy extends `script-src`,
`img-src` and `frame-src` with the Google syndication domains; with ads off it
returns to strict self-only.

### Warnings are deliberate

Guides involving registry edits, BIOS changes or opening a PC carry an explicit
warning. The site's own advice is never to open a power supply, never to mix modular
cables between power supplies, and never to change a storage controller mode after
installing Windows.

---

## Accessibility and SEO

- Semantic landmarks, a skip link, labelled form controls, `aria-label` on icon
  buttons, `aria-current` on the active nav item, and a visible focus ring
- Dark and light themes applied before first paint so there is no flash, following the
  system preference until the visitor chooses
- `prefers-reduced-motion` respected
- Per-page titles, meta descriptions, canonical URLs, Open Graph and Twitter card
  tags, and JSON-LD `TechArticle` markup on article and stop code pages
- Generated `sitemap.xml` covering every article, stop code, wizard and script, and a
  `robots.txt` that keeps `/admin` and API paths out of the index
- Per-page SEO overrides and site-wide defaults editable at `/admin/seo`
- Mobile-first layout with no JavaScript required for any page to work

---

## License

This repository ships **no `LICENSE` file and states no formal license grant**. The
only licensing note in the project is this one:

> Written as a reference project. Product names and vendor links are the property of
> their respective owners. FixIT Hub is not affiliated with Microsoft, NVIDIA, AMD,
> Intel, Realtek or any other vendor.

Treat the code as all rights reserved until the author adds a license. Vendor names,
driver download links and troubleshooting advice referencing commercial products
remain the property of their respective owners and are used for identification only.