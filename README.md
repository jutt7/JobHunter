# 🌅 Daily Job Agent

An automated job-hunting agent for the German market. Every morning it pulls
fresh postings from the **Arbeitsagentur** (Federal Employment Agency) public
API, uses an **LLM to score each posting against your CV** (0–10 with a one-line
reason), and delivers the best matches to your **Telegram** — sorted by fit,
deduplicated, with apply links.

Runs entirely on the **GitHub Actions free tier**. No server, no hosting bill —
just a scheduled workflow. The only running cost is a few cents of LLM calls per
day.

---

## Why it exists

Scrolling job boards every morning is repetitive and easy to skip. This turns it
into a single Telegram message: the handful of roles genuinely worth your time,
pre-ranked, waiting for you when you wake up.

## How it works

```
GitHub Actions cron (daily)
        │
        ▼
   main.py  ─────────────────────────────────────────────┐
     ├─ arbeitsagentur.py   query the free jobs API        │
     ├─ storage.py          drop postings already seen     │  runs on the
     ├─ scoring.py          LLM scores fit vs. your CV      │  GH Actions
     └─ notify.py           send a ranked Telegram digest   │  free tier
                                                            ┘
```

**Design choices worth noting:**
- **Deterministic where it should be, LLM where it counts.** Fetching, filtering
  and deduping are plain code — cheaper and more reliable than an LLM. The model
  is used only for the judgement call: how well does this role fit *this* CV.
- **Cost-bounded.** A per-run cap (`MAX_JOBS_TO_SCORE`) limits how many postings
  reach the LLM, so a flood of listings can never run up a bill.
- **Idempotent.** Seen postings are tracked in `seen.json` (committed back by the
  workflow), so you never get the same job twice.
- **Fail-safe delivery.** Jobs are only marked "seen" *after* a successful send,
  so a delivery hiccup re-tries tomorrow instead of silently dropping the day.
- **Secrets, not files.** API keys and even your CV are injected via GitHub
  Secrets — nothing sensitive lives in the repo.

## Tech

Python · GitHub Actions (cron) · OpenAI API · Telegram Bot API ·
Arbeitsagentur Jobsuche API

---

## Use it yourself (~15 min)

Everyone runs their own independent copy with their own keys — nothing is shared.

### 1. Fork this repo
Click **Fork** (top right). In your fork, open the **Actions** tab and click
**"I understand my workflows, go ahead and enable them"** — forks have Actions
off by default.

### 2. Create a Telegram bot
1. Message **@BotFather**, send `/newbot`, follow the prompts. Copy the **token**.
2. Open a chat with your new bot and send it any message (a bot can't message you
   first).
3. Visit `https://api.telegram.org/bot<TOKEN>/getUpdates` in a browser and read
   `"chat":{"id": ...}` — that number is your **chat ID**.

### 3. Get an OpenAI API key
From [platform.openai.com/api-keys](https://platform.openai.com/api-keys). Make
sure the account has billing/credits, or scoring calls fail.

### 4. Add secrets

Fastest way — the setup wizard does the fiddly parts for you (validates your
keys, **auto-detects your Telegram chat ID**, sends a test message, and can push
all secrets to GitHub via the [`gh` CLI](https://cli.github.com)):

```bash
pip install -r requirements.txt
python setup.py
```

Or add them by hand: your fork → **Settings → Secrets and variables → Actions →
New repository secret**:

| Secret name          | Value                                             |
|----------------------|---------------------------------------------------|
| `OPENAI_API_KEY`     | your OpenAI API key                               |
| `TELEGRAM_BOT_TOKEN` | the BotFather token                               |
| `TELEGRAM_CHAT_ID`   | your numeric chat ID                              |
| `CV_TEXT` (optional) | your full CV text — keeps it out of the repo      |

### 5. Add your profile & searches
- **CV:** either set the `CV_TEXT` secret (recommended), or edit `cv.txt` directly.
- **Searches:** edit `SEARCH_PROFILES` in `config.py` (keywords; add a `wo` city +
  `umkreis` radius to scope by location, or omit for all of Germany).

### 6. Run it
**Actions → Daily Job Agent → Run workflow.** You should get a Telegram digest
within a minute or two. After that it runs itself every morning.

---

## Configuration (`config.py`)

| Setting             | What it does                                        |
|---------------------|-----------------------------------------------------|
| `SEARCH_PROFILES`   | List of searches (keywords, optional city/radius).  |
| `DAYS_BACK`         | Only postings from the last N days.                 |
| `MIN_SCORE`         | Only send jobs scoring ≥ this (0–10).               |
| `MAX_JOBS_TO_SCORE` | Cost guard: max LLM calls per run.                  |
| `TOP_N`             | Max jobs per digest.                                |

Sharper (pricier) scoring: uncomment `OPENAI_MODEL: gpt-4o` in the workflow.
Send time: the cron `0 5 * * *` is UTC — adjust the hour to taste.

## Notes & limitations
- The Arbeitsagentur DB is huge, but some roles are posted only on company career
  pages and won't appear there.
- Broad, nationwide keyword searches return a lot — `MIN_SCORE` does the
  filtering. Raise it if your digest is too long.

## License
MIT — see [LICENSE](LICENSE).
