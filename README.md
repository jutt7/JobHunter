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
   main.py  ──────────────────────────────────────────────────┐
     ├─ sources.py             Posting + the FeedSource shape │
     ├─ ba.py                  Arbeitsagentur as a FeedSource │
     │   └─ arbeitsagentur.py  query the free jobs API        │  runs on the
     ├─ screening.py           dedupe + free title/PLZ filter │  GH Actions
     ├─ storage.py             drop postings already seen     │  free tier
     ├─ scoring.py             LLM scores fit vs. your CV     │
     ├─ notify.py              send a ranked Telegram digest  │
     └─ email_notify.py        send the same digest via email │
                                                              ┘
```

Pipeline order:

```
fetch (every FeedSource) -> drop seen -> dedupe -> cheap filter
   -> scoring budget cut -> fetch advert bodies -> LLM score -> rank -> digest
```

Notes on the design:
- Fetching, filtering and deduping are plain code. The LLM is used only for the
  judgement call: how well does this role fit this CV.
- Adding a job source means writing one class with `fetch()` and `describe()`
  (see `sources.py`) and appending it to `SOURCES` in `main.py`. Nothing in
  scoring, dedupe or the digest knows how many sources there are.
- The cheap filter in `screening.py` runs *before* the scoring budget is spent,
  so irrelevant postings cost nothing instead of costing a model call. Tune it
  with `TITLE_INCLUDE` / `TITLE_EXCLUDE` in `config.py`.
- Dedupe keys on company + gender-neutralised title + postal code, not on URL or
  date. Boards refresh a posting's date during its run and the same job reaches
  us from several feeds, so keying on either would resurface jobs already sent.
- `describe()` (the second HTTP request that fetches the advert body) runs only
  for postings that survive every filter and the budget cut.
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
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 setup.py
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

Scoring runs on `gpt-5.6-luna`. For sharper but pricier judgement, uncomment
`OPENAI_MODEL: gpt-5.6-terra` in the workflow.
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

## Testing

No test dependencies — everything is stdlib `unittest`. The commands below
assume the virtualenv from step 4 is active (`source .venv/bin/activate`);
without it, run them as `.venv/bin/python -m unittest ...` instead. The tests
import `main`, which pulls in `requests` and `openai`, so a bare system
interpreter won't do.

```bash
python3 -m unittest test_jobhunter -v
```

38 offline tests. No network, no OpenAI key, nothing sent. They run against
`testdata/ba_search.json`, a trimmed capture of real Arbeitsagentur search
responses, so the fixtures are shaped like the API rather than like whatever the
code expects. Covered: gender-marker stripping, dedupe-key invariants,
`seen.json` backward compatibility, the title/PLZ filter, normalisation of real
payloads, the pipeline's drop counts, HTML escaping in both digests, and the
invariant that no advert body is fetched for a posting that was going to be
discarded anyway.

Several tests are named for a specific filter bug and exist to stop it coming
back — `test_regression_developer_stem`, `test_regression_dual_needs_word_boundary`,
`test_regression_parenthesised_seniority_is_open_level`. There is also
`test_every_search_profile_survives_its_own_filter`, which fails if
`SEARCH_PROFILES` and `TITLE_INCLUDE` drift apart (paying to search for
something the filter then throws away).

To check the live wiring without spending anything:

```bash
python3 main.py --dry-run
```

Real API calls and real advert fetches, but no model calls, nothing sent, and
`seen.json` is never written — so it needs no `OPENAI_API_KEY`. It prints how
many postings were dropped at each stage and how many would have been scored.
`--limit N` controls how many advert bodies it fetches (default 5).

`tools_verify_refactor.py` is a one-off record that the FeedSource refactor left
the digest byte-identical; it replays the pre-refactor `main.py` out of git
alongside the current one.

## Notes and limitations
- The Arbeitsagentur DB is huge, but some roles are posted only on company career
  pages and won't appear there.
- Broad, nationwide keyword searches return a lot. `MIN_SCORE` does the
  filtering; raise it if your digest gets too long.

## License
MIT. See [LICENSE](LICENSE).
