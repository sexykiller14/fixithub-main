# FixIT Hub

**Diagnose and fix PC problems yourself.**

A server-rendered technical support knowledge base for Windows 10 and 11. It
helps visitors work out what is wrong with their computer and what to do about
it, instead of opening a support ticket.

- Short description: a FastAPI + Jinja2 application that publishes a searchable
  library of markdown repair guides, a BSOD stop-code reference with an in-memory
  minidump analyzer, guided troubleshooting wizards, driver and hardware
  references, a set of read-only diagnostic scripts, and a small set of safe
  network diagnostic tools.
- Everything renders on the server. The only JavaScript is progressive
  enhancement — no page needs it to work.
- No database server required: SQLite is a file. Postgres works too, and is what
  you need on a serverless host.
- No content management system, no build step, no bundler, no SPA.

Full configuration, deployment and maintenance guidance lives in
**[DEPLOYMENT.md](DEPLOYMENT.md)**.

---

## Features

### Knowledge base

| Feature | Route | Notes |
| --- | --- | --- |
| Home page | `/` | Search, category cards, popular fixes, recently added |
| Full-text search | `/search` | Articles and stop codes together; `LIKE` fallback when FTS5 is unavailable |
| Article library | `/articles`, `/category/<slug>` | 43 markdown guides, filterable by category and difficulty |
| Article pages | `/articles/<slug>` | Table of contents, copyable command blocks, callout warnings, related guides |
| Helpful / not helpful voting | `POST /articles/<slug>/feedback` | One vote per IP per target, stored as a hash |

### Blue screen (BSOD) diagnosis

| Feature | Route | Notes |
| --- | --- | --- |
| Stop code index | `/bsod` | 92 codes, sorted, with popularity |
| Code lookup | `/bsod/<NAME>` | Accepts name, `0x7E` or the decimal value |
| Quick lookup | `/bsod/lookup` | Single-field lookup |
| Minidump analyzer | `/bsod/analyze` | Reads the bugcheck code out of an uploaded `.dmp` |
| Upload pre-check | `/api/dump/validate` | Signature and size validation |

The analyzer parses `PMDMP`, `PAGEDU`, `PAGE` and `FULL` dumps in memory, extracts
the bugcheck code, its four parameters, the OS version and build, and plain-English
hints for thirteen common codes. Uploads are capped at 5 MB while streaming and
**the bytes are never written to disk or executed**.

### Guided troubleshooting

| Feature | Route | Notes |
| --- | --- | --- |
| Wizard index | `/wizards` | 8 decision trees |
| Wizard flow | `/wizards/<id>` | Question/answer steps with progress, Back, and restart |
| Wizard results | `/wizards/<id>/step` | A diagnosis with numbered steps, warnings and a linked guide |

Progress lives in the signed session cookie, so a half-finished wizard survives a
page reload.

### Diagnostics

| Feature | Route | Notes |
| --- | --- | --- |
| Tools index | `/tools` | Five network tools |
| DNS lookup | `/tools/dns` | A, AAAA, MX, NS, TXT, CNAME, SOA, CAA |
| Public IP | `/tools/ip` | Address plus city, country, ISP and ASN |
| Port check | `/tools/port` | Allowlisted ports only, with a plain-English verdict |
| HTTP status | `/tools/status` | HTTPS only; does not follow redirects |
| TCP latency | `/tools/latency` | Min / max / average / median / jitter |
| JSON endpoints | `/api/dns`, `/api/port`, `/api/status`, `/api/latency` | Same checks, JSON responses |
| Hardware diagnostics | `/hardware`, `/hardware/<slug>` | RAM, storage, temperatures, PSU, beeps, battery |
| Device Manager codes | `/drivers`, `/drivers/<slug>` | Error codes and vendor download pages |
| Diagnostic scripts | `/scripts`, `/scripts/<slug>` | 5 `.ps1`/`.bat` files shown in full before download, with every command explained |

The network tools validate every target before use and cannot be turned into a
scanner for private ranges — see the safety notes in
[DEPLOYMENT.md](DEPLOYMENT.md#the-network-tools-cannot-be-used-to-scan-your-network).

### Tools and downloads

| Feature | Route | Notes |
| --- | --- | --- |
| Tool library | `/apps`, `/apps/<slug>` | Admin-uploaded binaries with version, vendor and checksum |
| Integrity | — | SHA-256 recorded at upload and re-verified on every download |
| Screenshot preview | `/apps/<slug>/screenshot` | SVG refused on upload |

Uploads are limited to `.exe`, `.msi` and `.zip`, 50 MB, and are checked by
magic bytes before anything is stored.

### Community

| Feature | Route | Notes |
| --- | --- | --- |
| Reader accounts | `/signup`, `/login`, `/account` | Off by default; for commenting and gated downloads |
| Email verification | `/verify/<token>` | Optional — works without SMTP, confirmed by hand |
| Comments | `POST /comments` | Moderated; new comments are never public until approved |
| Ask the admins anything | `POST /api/ask` | Anonymous by default, answered by a person from `/admin/questions` |
| Account deletion | `POST /account/delete` | Deletes the account and every comment it wrote |

### Admin panel

Single-password panel at `/admin`, with a separate cookie and a separate
privilege boundary from reader accounts.

- Dashboard with counts, trends and recent activity
- Article and stop-code editors with live preview
- Tool upload and metadata editing
- Comment moderation, question answering, reader deletion
- AdSense settings and placements, SEO overrides, announcement banner
- Email delivery log, outbound link list, per-article analytics
- Database backup and restore
- Admin password change, and optional TOTP two-factor with recovery codes
- Audit log of every state-changing action

### Platform

| Feature | Route | Notes |
| --- | --- | --- |
| Health probe | `/healthz`, `/health` | Checks the database; used by Docker and load balancers |
| Sitemap | `/sitemap.xml` | Generated from the live database |
| Robots policy | `/robots.txt` | Keeps `/admin` and API paths out of the index |
| ads.txt | `/ads.txt` | Served from the admin-configured value |
| Security headers | every response | CSP, `nosniff`, frame denial, referrer policy, HSTS over HTTPS |

---

## Tech stack

| Layer | Choice |
| --- | --- |
| Language | Python 3.12 |
| Web framework | FastAPI (`>=0.115.0`) |
| ASGI server | Uvicorn (`uvicorn[standard]`) |
| Templates | Jinja2 (`>=3.1.4`) |
| ORM | SQLAlchemy 2.x (`DeclarativeBase`, `Mapped`, `mapped_column`) |
| Database | SQLite by default, PostgreSQL via `psycopg2-binary` |
| Migrations | None. `create_all` plus an additive `ALTER TABLE ADD COLUMN` repair pass |
| Markdown | `markdown-it-py` (CommonMark, plus tables and strikethrough) |
| Frontmatter | PyYAML, `safe_load` only |
| Passwords | `bcrypt`, cost 12 |
| Signatures | `itsdangerous` (`URLSafeTimedSerializer`) and Starlette `SessionMiddleware` |
| DNS | `dnspython` |
| HTTP client | `httpx` |
| Minidump parsing | `minidump==0.0.24`, with a built-in `struct` parser as fallback |
| TOTP | Implemented in-house on `hmac`/`hashlib`/`struct` (RFC 6238) |
| Email | `smtplib` from the standard library |
| Uploads | `python-multipart` |
| HTML sanitising | In-house allowlist sanitiser applied after rendering |
| Styling | Tailwind CSS from its CDN, plus a hand-written `site.css` |
| JavaScript | None required; two vanilla progressive-enhancement files |
| Tests | pytest |
| Browser auditing | Node, `lighthouse` and `puppeteer-core` (dev-only) |
| Containers | Multi-stage `python:3.12-slim` Dockerfile, `docker-compose.yml` |

There are no `subprocess` calls and no shell-outs anywhere in the codebase.

---

## Installation

### Local development

```bash
git clone <repository-url>
cd fixithub-main

python -m venv .venv

# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS and Linux:
source .venv/bin/activate

pip install -r requirements.txt

python seed.py --set-admin-password "choose-a-password"

uvicorn app.main:app --reload
```

Then open <http://127.0.0.1:8000>.

### Docker

```bash
docker compose up --build

# Seed the database and set the admin password once the container is up
docker compose exec app python seed.py --set-admin-password "your-password"
```

Open <http://127.0.0.1:8000>. The compose file mounts named volumes for
`/app/data` and `/app/apps_download`, so the database and uploaded binaries
survive a rebuild. `FIXITHUB_SECRET_KEY` is required and Compose will refuse to
start without it.

---

## Usage examples

### Run the server

```bash
# Development, with auto-reload
uvicorn app.main:app --reload

# Bound to all interfaces, fixed port
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

On Windows, without activating the environment:

```bash
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Run **one worker**. The rate limiter and the login throttle keep their counters
inside the process, so extra workers multiply both limits.

### Manage the knowledge base

```bash
python seed.py                              # load articles and stop codes
python seed.py --reset                      # drop everything first
python seed.py --rebuild-search             # rebuild the full-text index
python seed.py --check                      # report what is in the database
python seed.py --no-content                 # stop codes only
python seed.py --set-admin-password         # prompt for the password
```

Articles come from `content/*.md` and stop codes from `data/bsod_codes.json`.
Both are upserts, so the script is safe to re-run after every edit. `--reset`
destroys view counts and feedback.

Add an article by dropping a file into `content/`:

```markdown
---
title: Fix a noisy fan
category: hardware
tags: [fan, noise, cooling]
difficulty: easy
---

The summary is taken from the opening paragraph unless you set one explicitly.

## Disconnect the power first

> [!WARNING]
> A spinning blade is never safe to touch.
```

Then run `python seed.py` to index it.

### Configure

Every setting is an environment variable, and the defaults are fine for local
work. The ones that matter in production:

```bash
export FIXITHUB_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
export FIXITHUB_SITE_URL="https://fixithub.example.com"
export FIXITHUB_SECURE_COOKIES=1
export FIXITHUB_TRUST_PROXY=1        # only behind a proxy you control
export FIXITHUB_ADMIN_PASSWORD="a-long-password"

uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Start with `FIXITHUB_SECRET_KEY` unset and the app boots on a key generated at
startup, which means every restart invalidates every session and other workers
reject each other's cookies. Set `FIXITHUB_ENV=production` to turn that into a
boot failure instead of a warning.

The full table, including Supabase Storage and the GitHub content mirror, is in
[DEPLOYMENT.md](DEPLOYMENT.md#configuration).

### Use the API endpoints

Under `/tools` and `/api`:

```bash
curl -X POST http://127.0.0.1:8000/api/dns \
  -H 'Content-Type: application/json' \
  -d '{"host": "example.com", "record_type": "A"}'

curl -X POST http://127.0.0.1:8000/api/port \
  -H 'Content-Type: application/json' \
  -d '{"host": "example.com", "port": 443}'

curl -X POST http://127.0.0.1:8000/api/status \
  -H 'Content-Type: application/json' \
  -d '{"url": "https://example.com"}'

curl "http://127.0.0.1:8000/api/search/suggest?q=wifi"
```

Rate limited to 10 requests per minute per IP by default.

### Build your own image

```bash
docker build -t fixithub .
docker run -d --name fixithub -p 8000:8000 \
  -e FIXITHUB_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')" \
  -e FIXITHUB_ADMIN_PASSWORD="a-long-password" \
  -v fixithub-data:/app/data \
  fixithub
```

### Run the tests

```bash
pytest -q
```

Fully offline. The fixtures point at a temporary SQLite database, a temporary
admin hash file and a temporary upload directory, so your own data is never
touched.

### Audit the rendered pages in a real browser

```bash
npm install
npm run audit:measure      # find what overflows the viewport, per page and viewport
npm run audit:shots        # screenshots
npm run audit:lighthouse   # Lighthouse runs
```

These drive a locally installed Chrome or Edge against a running instance on
`http://127.0.0.1:8000`. The site itself needs no Node.js.

### Check the deployment

```bash
curl -i http://127.0.0.1:8000/healthz   # 200 "ok", or 503 if the database is unreachable
```

---

## Project structure

```
.
├── app/
│   ├── main.py            # application factory, security headers, error handlers, /healthz
│   ├── config.py          # settings from the environment, category and vendor tables
│   ├── db.py              # engine, sessions, additive schema repair, FTS5 search with a LIKE fallback
│   ├── models.py          # SQLAlchemy models (see below)
│   ├── security.py        # bcrypt, signed admin cookie, CSRF, client IP
│   ├── rate_limit.py      # thread-safe sliding window limiter
│   ├── templates.py       # Jinja environment and shared helpers
│   ├── deps.py            # shared template context
│   ├── routes/            # one module per area of the site
│   │   ├── pages.py       #   home, category, about, privacy
│   │   ├── articles.py    #   article library and feedback
│   │   ├── search.py      #   search and suggestions
│   │   ├── bsod.py        #   stop codes, minidump analyzer, dump validation
│   │   ├── wizards.py     #   troubleshooting decision trees
│   │   ├── tools.py       #   the five network tools, form and JSON
│   │   ├── drivers.py     #   vendor pages and Device Manager codes
│   │   ├── hardware.py    #   hardware diagnostics topics
│   │   ├── scripts.py     #   diagnostic script catalogue and downloads
│   │   ├── apps.py        #   downloadable tools and downloads
│   │   ├── accounts.py    #   reader signup, login, verification, deletion
│   │   ├── comments.py    #   moderated reader comments
│   │   ├── ask.py         #   the "ask us anything" widget endpoints
│   │   ├── admin.py       #   the entire admin panel
│   │   └── seo.py         #   sitemap.xml, robots.txt, ads.txt
│   ├── services/          # domain logic, no HTTP
│   │   ├── content.py     #   markdown files and frontmatter
│   │   ├── markdown.py    #   rendering, sanitising, table of contents
│   │   ├── stopcodes.py   #   stop code loading and lookup
│   │   ├── search.py      #   search, query logging, feedback
│   │   ├── wizards.py     #   decision-tree traversal and progress
│   │   ├── ssrf.py        #   input validation and address filtering
│   │   ├── nettools.py    #   DNS, public IP, port, status, latency
│   │   ├── minidump.py    #   Windows dump parsing
│   │   ├── apps.py        #   upload validation and checksums
│   │   ├── storage.py     #   local disk or Supabase Storage backend
│   │   ├── accounts.py    #   accounts, tokens, sessions, email
│   │   ├── totp.py        #   RFC 6238 two-factor
│   │   ├── ads.py         #   AdSense markup generation
│   │   ├── audit.py       #   audit log writes and IP hashing
│   │   ├── github.py      #   content mirror to GitHub
│   │   └── scripts_catalog.py  #   the downloadable script metadata
│   ├── templates/         # 66 Jinja templates
│   └── static/
│       ├── css/site.css
│       └── js/            # site.js, ask-widget.js (both optional)
├── api/
│   └── index.py           # Vercel serverless entry point
├── content/               # 43 markdown guides
├── data/
│   ├── bsod_codes.json    # 92 stop codes
│   └── wizards/           # 8 decision trees
├── scripts_download/      # the 5 downloadable .ps1 and .bat files
├── tests/                 # 25 pytest modules
├── scripts/               # Node browser-audit tooling
├── seed.py                # content loader and admin password tool
├── Dockerfile
├── docker-compose.yml
├── render.yaml            # Render blueprint
├── vercel.json
├── requirements.txt
├── package.json           # dev-only audit tooling
└── pytest.ini
```

### Data model

`app/models.py` defines `Article`, `StopCode`, `Feedback`, `SearchQuery`,
`DumpUpload`, `User`, `AuthToken`, `Comment`, `Question`, `AdSettings`,
`AdUnit`, `AppDownload`, `ArticleView`, `SeoOverride`, `SiteSeoSettings`,
`EmailLog`, `AdminAuditLog`, `Announcement` and `AdminTwoFactor`.

Two conventions run through it: tokens and admin secrets are stored as hashes,
and IP addresses are stored salted and truncated rather than in the clear.

### Adding a page

1. Add a route in the matching `app/routes/*.py` module
2. Add a template in `app/templates/`
3. Link it from `app/templates/base.html` if it belongs in the navigation

---

## Deployment

Works unchanged on any host with a persistent filesystem — Docker, Render
(via the `render.yaml` blueprint), Railway, Fly.io, systemd behind nginx — and on
Vercel as a serverless function, where mutable files move to Postgres and
Supabase Storage.

See [DEPLOYMENT.md](DEPLOYMENT.md) for per-platform instructions.

---

## License

**No license has been granted for this project.**

There is no `LICENSE` file in this repository and no open-source license has
been applied, so the default copyright applies: the code is not licensed for
use, modification or redistribution, and no permission is granted to anyone
beyond what the copyright holder has stated directly.

The project is presented as a reference implementation.

Product names, trademarks and vendor links referenced in the content belong to
their respective owners. FixIT Hub is not affiliated with, endorsed by, or
sponsored by Microsoft, NVIDIA, AMD, Intel, Realtek, Lenovo, MSI, ASUS or any
other vendor, and every download link points at the vendor's own site.