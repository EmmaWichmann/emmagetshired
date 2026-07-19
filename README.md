# onemoretime

A tracker for starting over — log the small, unglamorous things (a job
application, getting out of bed, drinking water, practicing speaking out
loud) and watch a garden grow one coin at a time. Python + Flask +
SQLite backend, built specifically to practice SQL (SELECT, WHERE, GROUP
BY, JOIN, aggregate functions) while building something worth actually
using.

## The story

I built the first version of this when I was deep in a job search,
calling it "EmmaGetsHired." It only tracked one thing: did you apply
today. Somewhere in rebuilding it, I realized the job search wasn't
actually my whole problem — I'd left a doctorate program after one
semester because I recognized a pattern I didn't want to repeat, and
that was a harder thing to sit with than a rejection email. So I rebuilt
the app to track the whole picture: applying, getting up, moving,
speaking, taking care of yourself. Starting over isn't one big dramatic
comeback — it's a lot of small "one more times." The full story (and
the about page) are in the app itself at `/` and `/about`.

It's no longer just for me. Anyone can use it, privately, with no
account required — see **Multi-user, no login** below.

## Setup

```bash
pip install -r requirements.txt
python app.py
```

Then open **http://127.0.0.1:5000** — no password, no signup. The
database file (`onemoretime.db`) is created automatically on first run.

## Multi-user, no login

Every visitor gets a private space automatically, the first time they
load the app, via a random UUID stored in a browser cookie (`uid`). No
password, no account creation. Every table (`categories`, `logs`,
`rewards`, `moods`, `user_settings`) has a `user_id` column, and every
database query in `database.py` filters by it — one visitor's logs,
rewards, custom categories, and mood check-ins are invisible to every
other visitor, including whoever's running the server.

### Getting back into your own data

Since there's no password, your only "login" is that one browser
cookie. If you clear cookies or switch devices, you'd normally get a
brand-new empty space. To avoid that, set two environment variables
before running the app:

```bash
export OWNER_USER_ID="some-fixed-uuid-you-generate-once"
export OWNER_KEY="a long random string only you know"
```

Then visiting `https://yourapp.example.com/me?key=<OWNER_KEY>` logs
that browser into `OWNER_USER_ID` instead of creating a new random one
— your real progress stays attached to one fixed identity you control,
recoverable from any browser or device. Anyone hitting `/me` without
the right key gets a 404, same as if the route didn't exist.

If you don't set these, the app falls back to a default key baked into
`app.py` — fine for trying it out locally, but change both before
deploying somewhere public.

## Running the tests

```bash
pytest test_database.py -v
```

29 tests covering every database function, including a regression test
for a real bug (SQL's `SUM()` returns `NULL`, not `0`, on an empty
table) and a set of multi-user isolation tests confirming one user's
categories, logs, rewards, and moods never leak into another user's
queries. Tests run against a temporary throwaway database, so they
never touch your real data.

## Deploying it live (free)

1. Push this folder to a GitHub repo
2. Go to [render.com](https://render.com), sign up free, "New Web Service"
3. Connect your repo, it auto-detects the `Procfile`
4. Add environment variables `OWNER_USER_ID` and `OWNER_KEY` (see above)
5. Deploy — Render gives you a live `https://yourapp.onrender.com` link

That link is what goes on your resume/portfolio next to the GitHub link.

## What's in each file

| File | What it does |
|---|---|
| `database.py` | Every SQL query in the app, written out and commented, all scoped by `user_id` |
| `app.py` | Flask routes, cookie-based identity, logging, API endpoints |
| `card_generator.py` | Builds the shareable PNG recap/streak images with Pillow |
| `templates/cover.html` | Landing page — the story, shown before the tracker |
| `templates/about.html` | About page |
| `templates/` | Server-rendered HTML pages |
| `static/style.css` | Design system, including 4 theme packs + custom color |
| `sql_practice.sql` | Every query pulled into one annotated study file |
| `test_database.py` | pytest suite, 29 tests |
| `Procfile` | Tells a host like Render how to run the app in production |

## Features

- **Cover page + about page** — the story behind the app, shown before you get to the tracker
- **No login, private by default** — every visitor gets their own space via a cookie, no account needed
- **Growth bar, categories, rewards** — log daily things, earn points, watch a garden grow
- **9 categories out of the box** — job search, speech practice, coding practice, getting up & moving, self-care, water, reading, mindfulness, movement — all editable
- **Custom categories** — add your own, with any emoji, name, and point value
- **Custom theme** — 4 built-in packs (earth, cottagecore, dark academia, y2k) plus your own background color, saved to your private space
- **Speech practice** — rotates through 8 real interview/networking/confidence question sets
- **JSON API** (`/api/stats`, `/api/log/<category>`) — the same data the pages use, available for a future mobile app or script to call directly
- **Error logging** — every request error gets written to `app.log` with a timestamp
- **Mood check-in** — quick emoji tap each day, stored alongside your logs
- **"onemoretime wrapped"** — a Spotify-Wrapped-style monthly recap, generated as a real downloadable/shareable PNG image (`/card/wrapped`)
- **Streak card** — a shareable PNG of your current streak (`/card/streak`), Duolingo-style
- **Daily affirmation** — rotates a random affirmation on every page load
- **pytest test suite** — 29 tests covering the database layer, including multi-user isolation
- **Deployment-ready** — `Procfile` + `gunicorn` so it can go live on Render/Railway in a few clicks

## SQL concepts this app uses

`CREATE TABLE` with `FOREIGN KEY` (including composite keys on
`(user_id, id)`) · `INSERT`/`UPDATE`/`DELETE` with `WHERE` ·
`INSERT ... ON CONFLICT DO UPDATE` · `COUNT()`, `SUM()`,
`COUNT(DISTINCT ...)` · `COALESCE()` · `GROUP BY` (including combined
with `WHERE`) · `JOIN` and `LEFT JOIN` · `DISTINCT` · `INSERT OR
REPLACE` · SQLite date math and `strftime()` for month-grouping.

See `sql_practice.sql` for the core query patterns with plain-English
explanations, plus 5 practice prompts to try writing yourself
(simplified to a single-user schema for readability — the real app adds
`user_id` filtering everywhere, see `database.py`).

## Why raw SQL instead of an ORM (like SQLAlchemy)

On purpose — the goal was to see and write real SQL, not have it
abstracted away. Once these patterns feel automatic, moving to an ORM
is easy; going the other direction is harder.
