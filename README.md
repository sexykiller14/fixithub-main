# FixIT Hub

A technical support knowledge base for Windows 10 and 11. It helps people
diagnose and fix PC problems themselves instead of opening a support ticket.

Everything is server-rendered with FastAPI and Jinja2, the knowledge base lives
in SQLite, and the only JavaScript is a small progressive-enhancement file.

---

## What it does

| Feature | Route | Notes |
| --- | --- | --- |
| Home page with search | `/` | Category cards, popular fixes, recently added |
| Full-text search | `/search` | Searches articles and stop codes together |
| Article library | `/articles`, `/category/<slug>` | 43 markdown guides, filterable |
| BSOD stop code lookup | `/bsod`, `/bsod/<NAME>` | 92 codes, by name, hex or decimal |
| Minidump analyzer | `/bsod/analyze` | Reads the bugcheck code from a .dmp in memory |
| Troubleshooting wizards | `/wizards` | 8 JSON decision trees with progress and Back |
| Network tools | `/tools/*` | DNS, public IP, port, HTTP status, latency |
| Driver help | `/drivers` | Vendor pages and Device Manager error codes |
| Hardware diagnostics | `/hardware` | RAM, storage, temperatures, PSU, beeps, battery |
| Diagnostic scripts | `/scripts` | Read-only scripts with every command explained |
| Downloadable tools | `/apps` | Admin-uploaded binaries as a screenshot card grid, each with a verified SHA-256 |
| Reader accounts | `/signup`, `/login`, `/account` | Optional, for commenting and gated downloads |
| Privacy notice | `/privacy` | What is stored, why, and how to have it deleted |
| Admin panel | `/admin` | Password protected article and stop code editing |
| SEO | `/sitemap.xml`, `/robots.txt` | Generated from the live database |
| Health probe | `/healthz`, `/health` | Used by Docker and load balancers |

---

## Requirements

- Python 3.11 or newer (developed on 3.12)
- No database server needed: SQLite is a file

---

## Quick start

```bash
# 1. Create a virtual environment
python -m venv .venv

# 2. Activate it
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS and Linux:
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Load the knowledge base and set an admin password
python seed.py --set-admin-password "choose-a-password"

# 5. Run the server
uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000>.

### The one-line run command

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

On Windows, if you prefer not to activate the environment:

```bash
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

---

## Running the seed script

`seed.py` loads the knowledge base into SQLite. It is an upsert, so running it
repeatedly is safe.

```bash
python seed.py                              # load articles and stop codes
python seed.py --reset                      # drop everything first
python seed.py --rebuild-search             # rebuild the full-text index
python seed.py --check                      # report what is in the database
python seed.py --no-content                 # stop codes only
python seed.py --set-admin-password "pw"    # hash and store a password
python seed.py --set-admin-password         # prompts for the password
```

Stop codes come from `data/bsod_codes.json` and articles from `content/*.md`, so
you can edit either and re-run the script. `--reset` destroys view counts and
feedback, so avoid it in production.

---

## Configuration

Every setting is an environment variable. The defaults work for local
development.

| Variable | Default | Purpose |
| --- | --- | --- |
| `FIXITHUB_SECRET_KEY` | random per process | Signs sessions and CSRF tokens. **Set this in production**, or sessions reset on every restart. |
| `FIXITHUB_ADMIN_PASSWORD` | unset | Admin password, hashed on the fly. Convenient for Docker. |
| `FIXITHUB_ADMIN_PASSWORD_HASH` | unset | A bcrypt hash. Takes priority over the saved file. |
| `FIXITHUB_DATABASE_URL` | `sqlite:///data/fixithub.db` | Any SQLAlchemy URL. |
| `FIXITHUB_ALLOW_REGISTRATION` | `0` | Set to `1` to accept reader sign-ups. Off by default, because turning it on means accepting comments from strangers. |
| `FIXITHUB_SMTP_HOST` | unset | Verification mail server. Unset means accounts need confirming by hand. |
| `FIXITHUB_SMTP_PORT` | `587` | `465` uses implicit TLS, anything else tries STARTTLS. |
| `FIXITHUB_SMTP_USER` / `FIXITHUB_SMTP_PASSWORD` | unset | SMTP credentials. |
| `FIXITHUB_SMTP_FROM` | unset | Envelope sender for verification mail. |
| `FIXITHUB_APPS_DIR` | `apps_download/` | Where admin-uploaded binaries are stored, in a `screenshots/` subdirectory alongside them. Point this at your persistent volume in production, or uploads are lost on redeploy. |
| `FIXITHUB_SITE_URL` | `http://localhost:8000` | Used for canonical URLs and the sitemap. |
| `FIXITHUB_DEBUG` | `0` | Set to `1` for tracebacks and verbose logging. |
| `FIXITHUB_SECURE_COOKIES` | `0` | Set to `1` when served over HTTPS. |
| `FIXITHUB_TRUST_PROXY` | `0` | Set to `1` **only** behind a proxy you control, so `X-Forwarded-For` is trusted for rate limiting. |
| `FIXITHUB_RATE_LIMIT_MAX` | `10` | Tool requests per window, per IP. |
| `FIXITHUB_RATE_LIMIT_WINDOW` | `60` | Window length in seconds. |

Example for production:

```bash
export FIXITHUB_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
export FIXITHUB_SITE_URL="https://fixithub.example.com"
export FIXITHUB_SECURE_COOKIES=1
export FIXITHUB_ADMIN_PASSWORD="a-long-password"
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

---

## Choosing a host

FixIT Hub runs either as a traditional persistent process (Docker, Render, Railway) or as a serverless application on **Vercel**.

| Platform | Works as written | Notes |
| --- | --- | --- |
| Vercel | Yes | Native serverless support via `vercel.json` & `api/index.py`. Auto-seeds SQLite in `/tmp`, or connects to external Postgres |
| Docker, systemd, Render, Railway, Fly.io | Yes | Persistent disk keeps the SQLite file and file-backed markdown edits |
| Netlify, Cloudflare Pages, AWS Lambda | Requires adapter | Serverless container platforms |

---

## Vercel

FixIT Hub is configured to run on Vercel as a serverless ASGI application using the `@vercel/python` runtime.

### Quick Start: Deploying to Vercel

1. **Push your code to GitHub / GitLab / Bitbucket**.
2. Go to [vercel.com/new](https://vercel.com/new) and **Import** your repository.
3. In the **Environment Variables** section, add the following variables:
   - `FIXITHUB_SECRET_KEY`: A long random string (generate one with `python -c "import secrets; print(secrets.token_urlsafe(48))"`).
   - `FIXITHUB_SITE_URL`: Your Vercel deployment URL (e.g. `https://your-app.vercel.app`).
   - `FIXITHUB_SECURE_COOKIES`: Set to `1`.
   - `FIXITHUB_ADMIN_PASSWORD`: Your admin panel password (e.g. `choose-a-strong-password`).
4. (Optional) **Persistent Database**:
   - By default, Vercel uses SQLite in `/tmp`. On cold starts, FixIT Hub automatically seeds all 43 guides, 92 stop codes, and wizards in less than a second.
   - For persistent comments, reader registrations, and feedback votes, attach a free cloud PostgreSQL database (e.g. [Neon](https://neon.tech), [Supabase](https://supabase.com), or Vercel Postgres) and set:
     `FIXITHUB_DATABASE_URL` = `postgresql://user:password@host/database?sslmode=require`
5. Click **Deploy**.

### CLI Deployment

If you prefer using the Vercel CLI:

```bash
# Install / run Vercel CLI
npx vercel

# Deploy to production with environment variables
npx vercel --prod
```

## Render

`render.yaml` is a ready-to-use blueprint. In the Render dashboard choose New >
Blueprint and point it at your repository.

1. Set `FIXITHUB_SITE_URL` to your deployed origin
2. Set `FIXITHUB_ADMIN_PASSWORD` in Environment. `FIXITHUB_SECRET_KEY` is
   generated for you
3. Deploy, then seed once over SSH:

```bash
render ssh fixithub -- python seed.py --rebuild-search
```

The blueprint attaches a 1 GB disk at `/app/data`, which is where the database
lives. Without it the database is discarded on every deploy.

> [!IMPORTANT]
> The free plan has no persistent disk, so the database is lost on each deploy
> and your admin password with it. Use a paid plan, or accept that the site
> comes back empty after every restart.

## Railway

```bash
railway init
railway up
railway volume add --mount-path /app/data   # required, see below
railway variables set \
  FIXITHUB_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')" \
  FIXITHUB_SITE_URL="https://your-app.up.railway.app" \
  FIXITHUB_SECURE_COOKIES=1 \
  FIXITHUB_TRUST_PROXY=1 \
  FIXITHUB_ADMIN_PASSWORD="a-long-password"
```

Railway needs the volume added before the first deploy, otherwise the app starts
against an ephemeral disk. Seed once with `railway run python seed.py --rebuild-search`.

---

## Docker

```bash
# Build and run
docker compose up --build

# Then seed the database and set a password
docker compose exec app python seed.py --set-admin-password "your-password"
```

The compose file mounts a named volume for `/app/data`, so the database and the
admin password hash survive a rebuild. It declares a healthcheck against
`/healthz`, so `docker compose ps` shows when the app is ready.

Plain Docker without compose:

```bash
docker build -t fixithub .
docker run -d --name fixithub -p 8000:8000 \
  -e FIXITHUB_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')" \
  -e FIXITHUB_ADMIN_PASSWORD="a-long-password" \
  -v fixithub-data:/app/data \
  fixithub
```

The container runs as a non-root user.

---

## Deploying without Docker

### systemd

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

```bash
sudo systemctl enable --now fixithub
```

### nginx in front

```nginx
server {
    listen 443 ssl http2;
    server_name fixithub.example.com;

    ssl_certificate     /etc/letsencrypt/live/fixithub.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/fixithub.example.com/privkey.pem;

    # The minidump analyzer accepts uploads up to 5 MB.
    client_max_body_size 6m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

server {
    listen 80;
    server_name fixithub.example.com;
    return 301 https://$host$request_uri;
}
```

> If you use a reverse proxy, set `FIXITHUB_TRUST_PROXY=1` so rate limiting counts
> the real client rather than the proxy's address. Only do this when the proxy
> is the only path to the app, or a client could spoof the header.

### Notes for multiple workers

The rate limiter keeps state in each process, so with `--workers 4` a client can
effectively make 40 requests per minute. Either run a single worker, or replace
`app/rate_limit.py` with a Redis-backed limiter before scaling out.

---

## Reader accounts

Registration is **off by default**. Turn it on with `FIXITHUB_ALLOW_REGISTRATION=1`.

An account lets a reader comment and download the uploaded tools. It carries no
other privilege: the admin panel is guarded by a separate cookie and a separate
password, and a test asserts that a signed-in reader cannot reach it.

Three design decisions are worth knowing about.

**Sessions live in the database, not the cookie.** The cookie holds an opaque
random token; only its SHA-256 is stored. That is what lets logging out, and an
admin deleting a reader, both genuinely end access, which a self-contained
cookie cannot do. Signing in again also invalidates any earlier session.

**Comments are moderated.** A new comment is `pending` and is visible only to its
author and in the admin queue at `/admin/comments`. With open registration, an
unmoderated comment box becomes a spam relay, and that cost lands on readers
rather than on the spammer.

**Comment bodies never reach the markdown renderer.** They are plain text,
escaped by Jinja. There is no path from a comment to injected markup on an
article page.

Set `FIXITHUB_SMTP_*` to send verification mail through any SMTP server, using
the standard library rather than a new dependency. With no SMTP configured the
site still works: accounts are created, commenting works, and the admin confirms
addresses by hand.

---

## The "Ask us anything" widget

A floating button in the bottom-right of every page opens a small panel. The
visitor writes a question, and an admin answers it from `/admin/questions` or
straight from the dashboard. All of the widget's text, its endpoint and its
character limit are in one `CONFIG` object at the top of
`app/static/js/ask-widget.js`, so the wording can be changed without touching the
logic. Set `endpoint: ''` to turn the request off and get a local thank-you
message with no backend involved.

The accent colour is a CSS variable: change `--ask-accent` in
`app/static/css/site.css` and the whole widget follows.

Four decisions are worth knowing about.

**Questions are answered by a person, not a model.** `POST /api/ask` stores the
question and returns. There is deliberately no automatic answer, because an open
unauthenticated endpoint that reaches a language model is a relay for whatever
that model will say about your site.

**The sender is anonymous unless they already had an account.** The widget asks
for no personal detail and there is no field inviting one. If the visitor was
signed in, the route reads their email from the session cookie rather than the
request body, so a caller cannot attach an address they do not own.

**Reading a reply needs the token from submission.** Submission returns a random
token once; only its SHA-256 is stored. `GET /api/ask/{id}?token=...` answers
404 rather than 403 for a wrong token, because a 403 would confirm that an id
exists and let anyone walk the queue. The trade-off is that only the sender's
browser holds the key, so clearing site data means a later answer will not reach
them. The admin still sees it.

**Polling only runs while the panel is open.** It checks once on open, then every
`CONFIG.pollIntervalMs` while the panel stays open, and stops for good once the
question is answered or the token stops working. A closed tab costs nothing.

Readers can delete their own account and every comment they wrote from
`/account`. That is a real deletion, not an anonymisation, and `/privacy`
describes exactly what is held and for how long.

---

## Changing the admin password

`/admin/change-password` takes the current password, a new one and a
confirmation. The new password is hashed with the same bcrypt cost the rest of
the site uses and written to `data/admin.json`.

The new password must be at least **10 characters**, which is the same rule
reader accounts get, and no longer than **72 bytes**, because bcrypt reads only
the first 72. Length is the requirement rather than a mix of character types,
for the reason already documented in `validate_password`: composition rules push
people toward `Password1!`, which is barely better than a dictionary word.

Changing the password **signs out every other admin session**. Admin sessions
are signed cookies with no database row, so `admin.json` also records when the
password last changed and every cookie carries that timestamp. A cookie whose
timestamp no longer matches is rejected. The admin who made the change is
immediately issued a fresh cookie, so they stay signed in.

Two environment settings override the saved file, and the page accounts for
both rather than pretending a change took effect:

- `FIXITHUB_ADMIN_PASSWORD_HASH` is checked first, so it wins over anything
  written here. The form is replaced with an explanation when it is set.
- `FIXITHUB_ADMIN_PASSWORD` is only used when `admin.json` does not exist.

Attempts are throttled at 5 per 5 minutes, separately from the login throttle,
because each attempt costs a bcrypt verify.

## Ads and AdSense

The admin panel has an **Ads** page at `/admin/ads`.

**What is stored.** One row of settings in `ad_settings`: master on/off, the
publisher id, whether Auto Ads is on, and the contents of `ads.txt`. Any number
of ad units in `ad_units`: label, slot id, format, placement, which pages they
appear on, which devices they appear on, and a per-unit enable switch.

**What is rendered.** The AdSense script ships in the `<head>` once per page,
only when ads are enabled and a valid publisher id is set. Each unit renders as
a `<div>` containing an `<ins class="adsbygoogle">` tag, with a `min-height`
placeholder so Google's iframe does not push other content down when it loads.
Push scripts are deferred until the slot is near the viewport via
IntersectionObserver. The sidebar placement lands in the article aside, and the
inside-content placement is injected after the Nth paragraph of an article
body. Below-fold slots get the same treatment.

**Where they appear.** Nothing is ever injected onto `/admin`, `/login`,
`/signup`, `/account`, `/logout`, `/verify` or any error page. The show-on rule
is checked per unit at render time, so a unit switched off or a page that
wasn't listed never renders.

**What is never stored.** Admin markup is never pasted, saved or echoed back.
The admin chooses structured fields (format, placement, slot id), and the site
assembles the tag server-side. The only JavaScript that exists is the AdSense
script you set up in your AdSense account plus a small IntersectionObserver
wrapper that defers the activation push. Nothing admin-supplied is ever run.

**The CSP.** When ads are enabled, the Content-Security-Policy extends
`script-src` with the AdSense script domains, `img-src` with the Google
syndication domains, and `frame-src` to the Google syndication domains. When
ads are switched off, the policy returns to strict `default-src 'self'`.

**ads.txt.** Anything you put in the settings textarea is served at `/ads.txt`
exactly as entered. Google fetches this file to verify which sellers are
allowed to serve your inventory, so it needs to contain at least the one line
for your own publisher id. It is served from the application, so it overrides
any static file you previously had at `public/ads.txt`; do not create both.

**Compliance notes** appear in the admin UI itself: never click your own ads,
follow AdSense placement policies, and if your visitors are in the EU or UK you
need a certified consent-management message before ads are loaded.

## Running the tests

```bash
pytest -q
```

All offline. They use a temporary SQLite database, a temporary admin hash file
and a temporary upload directory, so running them never touches your own data.

Coverage by area:

| File | What it covers |
| --- | --- |
| `tests/test_bsod.py` | Stop code lookup by name, hex, decimal and name variants; minidump signature, size and parse validation |
| `tests/test_validation.py` | SSRF refusal of private and reserved ranges, URL and port allowlists, request pinning, TLS SNI |
| `tests/test_rate_limit.py` | Sliding window behaviour, thread safety, the 10-per-minute HTTP limit, login throttling |
| `tests/test_admin.py` | Login, CSRF enforcement, password hashing, article and stop code CRUD, path traversal defence |
| `tests/test_pages.py` | Markdown sanitising, frontmatter, every page returning 200, SEO and security headers |
| `tests/test_security.py` | bcrypt hashing, the cached admin-hash path, login lockout, IP sanitising |
| `tests/test_accounts.py` | Registration, email validation, password rules, token hashing, session revocation, account deletion, the closed-registration gate, and the reader/admin privilege boundary |
| `tests/test_comments.py` | Comment moderation states, comment escaping, the gated download, and the vendor escape hatch |
| `tests/test_apps.py` | Upload validation: extension allowlist, magic bytes, filename sanitising, checksums |
| `tests/test_apps_routes.py` | The full admin upload round trip and the download response headers |
| `tests/test_ask.py` | Question submission, anonymous vs signed-in identity, the one-off reply token, admin replying, and rate limiting |
| `tests/test_admin_password.py` | Every refusal path, CSRF and auth enforcement, the throttle, a successful change followed by signing in with the new password, and other sessions being signed out |

---

## Project layout

```
.
├── app/
│   ├── main.py            # application factory, middleware, error handlers
│   ├── config.py          # settings and the category and vendor tables
│   ├── db.py              # engine, sessions, FTS5 search with a LIKE fallback
│   ├── models.py          # Article, StopCode, Feedback, SearchQuery, DumpUpload,
│   │                      #   AppDownload, Comment, User, Question
│   ├── security.py        # bcrypt, signed cookies, CSRF, client IP
│   ├── rate_limit.py      # sliding window limiter
│   ├── templates.py       # Jinja environment
│   ├── deps.py            # shared template context
│   ├── routes/            # one module per area of the site
│   ├── services/          # domain logic, no HTTP
│   │   ├── markdown.py    # rendering, sanitising, table of contents
│   │   ├── content.py     # markdown files and frontmatter
│   │   ├── stopcodes.py   # stop code lookup
│   │   ├── wizards.py     # decision trees
│   │   ├── ssrf.py        # input validation and address filtering
│   │   ├── nettools.py    # the five network tools
│   │   ├── minidump.py    # dump parsing
│   │   ├── search.py      # full-text search and feedback
│   │   ├── apps.py        # upload validation, checksums, storage
│   │   └── scripts_catalog.py
│   ├── templates/         # Jinja templates
│   └── static/            # CSS, JavaScript, favicon
├── content/               # 43 markdown guides
├── data/
│   ├── bsod_codes.json    # 92 stop codes
│   ├── wizards/           # 8 decision trees
│   └── admin.json         # bcrypt hash, created by seed.py
├── scripts_download/      # the downloadable .bat and .ps1 files
├── apps_download/         # admin-uploaded binaries, not in git
├── tests/
├── seed.py
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```

---

## How content works

Articles are markdown files in `content/`. Editing a file and re-running
`python seed.py` is the whole workflow.

```markdown
---
title: Fix high CPU and GPU temperatures
category: hardware          # hardware | network | windows | drivers | bsod
tags: [temperature, fan, thermal paste]
difficulty: moderate        # easy | moderate | hard | advanced
os_version: Windows 10/11
featured: true
---

Opening paragraph, used as the summary if none is set in the frontmatter.

## A heading becomes a table of contents entry

Commands go in fenced blocks, which get a copy button:

```text
DISM /Online /Cleanup-Image /RestoreHealth
```

Warnings are blockquotes with a marker:

> [!WARNING]
> This step erases your data.
```

Two custom blocks are recognised inside callouts: `> [!WARNING]`,
`> [!DANGER]`, `> [!TIP]`, `> [!NOTE]` and `> [!IMPORTANT]`.

Editing an article in `/admin` writes the markdown file back to `content/` and
rebuilds the search index, so the files stay the source of truth.

---

## Safety notes

This is a site about fixing computers. A few decisions are worth knowing about.

### Nothing runs on your machine

No code on this server executes anything on a visitor's PC, and nothing the app
serves is ever run on this server either. Uploads are stored as files and
hashed, never extracted, executed or inspected beyond their first few header
bytes.

Tool screenshots are the one place this needs qualifying. They are images an
admin attaches so a visitor can recognise a tool before downloading, and this
site never decodes or rewrites them: only the file header is read to confirm
the type. They are served with `nosniff` and a locked-down CSP, and SVG is
refused on upload, because a browser would run an SVG as a document rather than
display it as a picture. Even so, a visitor's browser does decode these pixels,
so it is worth knowing that a screenshot is the only uploaded content here that
something downstream actually interprets.

The [diagnostic scripts](/scripts) are plain text, shown in full on their page
before download with every command explained. Those remain the safest thing
this site hands you.

The [downloadable tools](/apps) are different: they are program binaries an
admin uploads. You cannot read their source. To keep that as safe as it can be,
every upload records a SHA-256 at upload time, that hash is re-checked on each
download, a mismatch disables the download rather than serving the file, and
each page states the publisher, version and checksum so a visitor can verify
what they received.

**Uploads are not scanned by antivirus software.** Nothing in the pipeline
inspects an upload's contents. Only upload a binary you have checked yourself,
and prefer a vendor's own signed download where one exists.

> [!WARNING]
> Windows will warn you before running anything from this site, because these
> files are unsigned and the publisher is not a name Windows recognises. That
> warning is expected and is not evidence of a problem. Conversely, a file that
> asks you to disable Defender is always a problem.

### Minidump uploads are never stored

The minidump analyzer reads the file in memory, parses the bugcheck header, and
discards the bytes. Uploads are size-capped at 5 MB while streaming, and the
`PMDMP`, `PAGEDU`, `PAGE` and `FULL` signatures are checked before any parser
sees the data. A dump file is data, not a program, and nothing in it is executed.
Only upload metadata is recorded, so abuse is visible in the admin panel.

This applies only to minidumps. Binaries an admin uploads through `/admin/apps`
are stored on disk, because that is the entire point of the feature.

### The network tools cannot be used to scan your network

Each tool validates its target before use:

- Hostnames are resolved, and every returned address is checked against the
  private, loopback, link-local, carrier-grade, multicast and reserved ranges.
  A hostname resolving to `127.0.0.1` or `169.254.169.254` is refused outright,
  including when one address in a set is public and another is not.
- Requests then connect to the already-validated IP, with the original `Host`
  header and TLS SNI preserved. This closes the DNS rebinding window between
  checking and connecting.
- Only `http` and `https` URLs are accepted, redirects are not followed,
  environment proxy variables are ignored, and the response body is never read
  into memory.
- Port checks are limited to a fixed allowlist of about 30 common ports.

No subprocess is spawned anywhere in the codebase. DNS uses `dnspython`, HTTP
uses `httpx`, and sockets use the standard library.

### Content is sanitised

Markdown is rendered and then passed through an allowlist sanitiser, so raw HTML
in a content file cannot inject scripts, event handlers or `javascript:` URLs.
Outbound links get `rel="noopener noreferrer nofollow"`.

### Warnings are deliberate

Guides that involve registry edits, BIOS changes or opening a PC carry an
explicit warning. The site's own advice is never to open a power supply, never
to mix modular cables between power supplies, and never to change a storage
controller mode after installing Windows.

---

## Accessibility and SEO

- Semantic landmarks, a skip link, labelled form controls, `aria-label` on icon
  buttons, `aria-current` on the active nav item, and a visible focus ring
- Dark and light themes, applied before first paint so there is no flash, and
  following the system preference until the visitor chooses
- `prefers-reduced-motion` respected
- Per-page titles, meta descriptions, canonical URLs, Open Graph and Twitter card
  tags, and JSON-LD `TechArticle` markup on articles and stop code pages
- Generated `sitemap.xml` covering every article, stop code, wizard and script,
  and a `robots.txt` that keeps `/admin` and API paths out of the index
- Mobile-first layout with no JavaScript required for any page to work

---

## Licence

Written as a reference project. Product names and vendor links are the property
of their respective owners. FixIT Hub is not affiliated with Microsoft, NVIDIA,
AMD, Intel, Realtek or any other vendor.
