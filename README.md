# bloom (Python + SQL edition)

The same life/job-search tracker, rebuilt with a Python backend and a real
SQLite database instead of browser localStorage — built specifically to
practice SQL (SELECT, WHERE, GROUP BY, JOIN, aggregate functions) while
building something I'd actually use. Since the first version, it's grown
into a small full-stack project: auth, a JSON API, tests, deployment
config, and a couple of just-for-fun touches (shareable recap cards,
mood check-ins, theme packs).

## Why two versions

The original [bloom](../bloom) is vanilla HTML/CSS/JS, for frontend practice.
This version is Flask + SQLite, for backend/database/full-stack practice.
Same product, two different stacks — worth mentioning both in interviews
since it shows range.

## Setup

```bash
pip install -r requirements.txt
python app.py
```

Then open **http://127.0.0.1:5000** — it'll ask for a password (see below).

The database file (`bloom.db`) is created automatically on first run.

### Setting your password

By default the password is `bloom2026`. To set your own, before running:

```bash
export BLOOM_PASSWORD="whatever you want"     # Mac/Linux
set BLOOM_PASSWORD=whatever you want           # Windows cmd
$env:BLOOM_PASSWORD="whatever you want"         # Windows PowerShell
```

## Running the tests

```bash
pytest test_database.py -v
```

17 tests covering every database function — including a regression test
for a real bug (SQL's `SUM()` returns `NULL`, not `0`, on an empty table).
Tests run against a temporary throwaway database, so they never touch
your real data.

## Deploying it live (free)

To get a real working link for your resume:

1. Push this folder to a GitHub repo
2. Go to [render.com](https://render.com), sign up free, "New Web Service"
3. Connect your repo, it auto-detects the `Procfile`
4. Add an environment variable: `BLOOM_PASSWORD` = your chosen password
5. Deploy — Render gives you a live `https://yourapp.onrender.com` link

That link is what goes on your resume/portfolio next to the GitHub link.

## What's in each file

| File | What it does |
|---|---|
| `database.py` | Every SQL query in the app, written out and commented |
| `app.py` | Flask routes, auth, logging, API endpoints |
| `card_generator.py` | Builds the shareable PNG recap/streak images with Pillow |
| `templates/` | Server-rendered HTML pages |
| `static/style.css` | Design system, including 4 theme packs |
| `sql_practice.sql` | Every query pulled into one annotated study file |
| `test_database.py` | pytest suite, 17 tests |
| `Procfile` | Tells a host like Render how to run the app in production |

## Features

- **Growth bar, categories, rewards** — same core tracker as the JS version
- **Speech practice** — rotates through 8 real interview/networking/confidence question sets
- **Password-protected** — simple session-based login, not enterprise-grade but shows the auth pattern
- **JSON API** (`/api/stats`, `/api/log/<category>`) — the same data the pages use, available for a future mobile app or script to call directly
- **Error logging** — every request error gets written to `app.log` with a timestamp
- **Mood check-in** — quick emoji tap each day, stored alongside your logs
- **"bloom wrapped"** — a Spotify-Wrapped-style monthly recap, generated as a real downloadable/shareable PNG image (`/card/wrapped`)
- **Streak card** — a shareable PNG of your current streak (`/card/streak`), Duolingo-style
- **Daily affirmation** — rotates a random affirmation on every page load
- **4 theme packs** — earth (default), cottagecore, dark academia, y2k — switchable in Settings
- **pytest test suite** — 17 tests covering the database layer
- **Deployment-ready** — `Procfile` + `gunicorn` so it can go live on Render/Railway in a few clicks

## SQL concepts this app uses

`CREATE TABLE` with `FOREIGN KEY` · `INSERT`/`UPDATE`/`DELETE` with `WHERE` ·
`COUNT()`, `SUM()`, `COUNT(DISTINCT ...)` · `COALESCE()` ·
`GROUP BY` (including combined with `WHERE`) · `JOIN` and `LEFT JOIN` ·
`DISTINCT` · `INSERT OR REPLACE` · SQLite date math and `strftime()` for
month-grouping.

See `sql_practice.sql` for every query with plain-English explanations,
plus 5 practice prompts to try writing yourself.

## Why raw SQL instead of an ORM (like SQLAlchemy)

On purpose — the goal was to see and write real SQL, not have it
abstracted away. Once these patterns feel automatic, moving to an ORM
is easy; going the other direction is harder.
