# Daily Job Agent

An automated job-hunting agent for the German market. Every morning it pulls
fresh postings from the Arbeitsagentur (Federal Employment Agency) public API,
scores each one against your CV with an LLM (0-10 plus a one-line reason), and
delivers the best matches to Telegram, email, or both: sorted by fit,
deduplicated, with apply links.

Each channel is independent: configure whichever you want. If both are set the
digest goes to both; it's marked "seen" as long as at least one delivery
succeeds.

Runs entirely on the GitHub Actions free tier. No server, no hosting bill, just
a scheduled workflow. The only running cost is a few cents of LLM calls per
day.

---

## Why it exists

Scrolling job boards every morning is repetitive and easy to skip. This turns it
into a single Telegram message or email: the handful of roles worth your time,
pre-ranked, waiting when you wake up.

## How it works

```
GitHub Actions cron (daily)
        │
        ▼
   main.py  ─────────────────────────────────────────────┐
     ├─ arbeitsagentur.py   query the free jobs API        │
     ├─ storage.py          drop postings already seen     │  runs on the
     ├─ scoring.py          LLM scores fit vs. your CV      │  GH Actions
     ├─ notify.py           send a ranked Telegram digest   │  free tier
     └─ email_notify.py     send the same digest via email  │
                                                            ┘
```

Notes on the design:
- Fetching, filtering and deduping are plain code. The LLM is used only for the
  judgement call: how well does this role fit this CV.
- `MAX_JOBS_TO_SCORE` caps how many postings reach the LLM per run, so a flood of
  listings can't run up a bill.
- Seen postings are tracked in `seen.json` (committed back by the workflow), so
  the same job never shows up twice.
- Jobs are marked seen only after a successful send, so a delivery failure
  retries on the next run instead of dropping the day.
- Telegram and email are independent senders behind a common `enabled()` /
  `send()` shape. Adding a channel is one small module.
- API keys and the CV are injected via GitHub Secrets, so nothing sensitive
  lives in the repo.

## Tech

Python · GitHub Actions (cron) · OpenAI API · Telegram Bot API ·
Gmail SMTP · Arbeitsagentur Jobsuche API

---

## Use it yourself

Everyone runs their own copy with their own keys. Nothing is shared.

### 1. Fork this repo
Click Fork (top right). In your fork, open the Actions tab and click
"I understand my workflows, go ahead and enable them". Forks have Actions off by
default.

### 2. Create a Telegram bot
1. Message **@BotFather**, send `/newbot`, follow the prompts. Copy the **token**.
2. Open a chat with your new bot and send it any message (a bot can't message you
   first).
3. Visit `https://api.telegram.org/bot<TOKEN>/getUpdates` in a browser and read
   `"chat":{"id": ...}`. That number is your chat ID.

### 2b. (Optional) Set up email via Gmail
Prefer email, or want both? Gmail needs an App Password, not your normal
password:
1. Turn on **2-Step Verification** at
   [myaccount.google.com/security](https://myaccount.google.com/security).
2. Create an App Password at
   [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords),
   then copy the 16-character code.
3. Set `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`, and optionally `EMAIL_TO` (the
   recipient; defaults to sending to yourself).

The setup wizard (below) can validate this and send you a test email.

### 3. Get an OpenAI API key
From [platform.openai.com/api-keys](https://platform.openai.com/api-keys). Make
sure the account has billing/credits, or scoring calls fail.

### 4. Add secrets

Fastest way is the setup wizard, which validates your keys, auto-detects your
Telegram chat ID, sends a test message, and can push all secrets to GitHub via
the [`gh` CLI](https://cli.github.com):

```bash
pip install -r requirements.txt
python setup.py
```

Or add them by hand in your fork under Settings -> Secrets and variables ->
Actions -> New repository secret:

| Secret name             | Value                                              |
|-------------------------|----------------------------------------------------|
| `OPENAI_API_KEY`        | your OpenAI API key                                |
| `TELEGRAM_BOT_TOKEN`    | the BotFather token *(Telegram channel)*           |
| `TELEGRAM_CHAT_ID`      | your numeric chat ID *(Telegram channel)*          |
| `GMAIL_ADDRESS`         | your Gmail address *(email channel)*               |
| `GMAIL_APP_PASSWORD`    | a 16-char Gmail App Password *(email channel)*     |
| `EMAIL_TO` (optional)   | recipient; defaults to `GMAIL_ADDRESS`             |
| `CV_TEXT`               | your full CV text, keeps it out of the repo        |

You need the secrets for at least one channel: the `TELEGRAM_*` pair, the
`GMAIL_*` pair, or both.

### 5. Add your profile & searches
- CV: set the `CV_TEXT` secret (recommended) or edit `cv.txt` directly. One of
  the two is required; without it the run stops with an error rather than
  scoring every job against the placeholder.
- Searches: edit `SEARCH_PROFILES` in `config.py` (keywords; add a `wo` city plus
  `umkreis` radius to scope by location, or omit for all of Germany).

### 6. Run it
Actions -> Daily Job Agent -> Run workflow. You should get the digest on each
channel you configured within a minute or two. After that it runs itself every
morning.

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
Send time: the cron `0 5 * * *` is UTC, so adjust the hour to taste.

## Delivery channels

Delivery is controlled by environment variables: a channel turns on when its
variables are present and is skipped otherwise. Configure Telegram, email, or
both. At least one is required.

| Channel      | Variables                                | Notes                                                        |
|--------------|------------------------------------------|--------------------------------------------------------------|
| Telegram | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | Both required. HTML digest, chunked under Telegram's limit.   |
| Email    | `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`    | Both required. Sent as an HTML email over Gmail SMTP (STARTTLS). |
| Email    | `EMAIL_TO` *(optional)*                  | Recipient address; defaults to `GMAIL_ADDRESS` (send to self). |

Gmail specifics: the email channel uses `smtp.gmail.com:587` and authenticates
with a Google App Password, not your normal account password. App Passwords
require 2-Step Verification to be on; create one at
[myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords).
Email is sent with the standard library, so there are no extra dependencies.

When both are on the digest goes to both. Jobs are marked seen as long as at
least one channel delivers; if every configured channel fails, nothing is marked
seen and the run retries on the next schedule.

## Notes and limitations
- The Arbeitsagentur DB is huge, but some roles are posted only on company career
  pages and won't appear there.
- Broad, nationwide keyword searches return a lot. `MIN_SCORE` does the
  filtering; raise it if your digest gets too long.

## License
MIT. See [LICENSE](LICENSE).
