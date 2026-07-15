# Daily Job Agent 🇩🇪

Every morning: pulls fresh German job postings from the **Arbeitsagentur** (Federal
Employment Agency) public API, has **Claude** score each one against your CV (0–10
with a one-line reason), and sends the best hits to your **Telegram** — sorted by
fit, deduplicated, with apply links.

Runs entirely on the **GitHub Actions free tier** — no server to keep alive.

---

## How it works

```
GitHub Actions cron  ──>  main.py
                           ├─ arbeitsagentur.py  fetch new jobs (free API)
                           ├─ storage.py         drop ones already seen
                           ├─ scoring.py         Claude rates fit 0–10
                           └─ notify.py          Telegram digest
```

The only paid piece is the Claude scoring — a handful of Haiku calls per day,
cents-level. Turn the cost knob with `MAX_JOBS_TO_SCORE` in `config.py`, or delete
the scoring step for a raw list.

---

## Setup (~15 min)

### 1. Create a Telegram bot
1. In Telegram, message **@BotFather**, send `/newbot`, follow the prompts.
2. Copy the **bot token** it gives you.
3. Get your **chat ID**: message your new bot once (say "hi"), then message
   **@userinfobot** — it replies with your numeric `Id`. That's your chat ID.
   *(Or open `https://api.telegram.org/bot<TOKEN>/getUpdates` in a browser after
   messaging the bot, and read `chat.id` from the JSON.)*

### 2. Get an Anthropic API key
From the [Claude Console](https://console.anthropic.com/) → API Keys.

### 3. Push this repo to GitHub, then add secrets
Repo → **Settings → Secrets and variables → Actions → New repository secret**:

| Secret name          | Value                     |
|----------------------|---------------------------|
| `ANTHROPIC_API_KEY`  | your Claude API key       |
| `TELEGRAM_BOT_TOKEN` | the BotFather token       |
| `TELEGRAM_CHAT_ID`   | your numeric chat ID      |

### 4. Personalise
- **`cv.txt`** — paste your real CV / summary. Sharper input = sharper scores.
- **`config.py`** — edit `SEARCH_PROFILES` (keywords, cities, remote), and the
  thresholds (`MIN_SCORE`, `TOP_N`, `DAYS_BACK`).

### 5. Test it
Go to the repo's **Actions** tab → **Daily Job Agent** → **Run workflow**. You
should get a Telegram message within a minute or two. After that it runs itself
every morning.

---

## Run locally (optional)

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...   TELEGRAM_BOT_TOKEN=...   TELEGRAM_CHAT_ID=...
python main.py
```

---

## Tuning notes

- **Too many / too few results?** Adjust `MIN_SCORE` and the search keywords.
- **Missing employer sites** (CHECK24, Bending Spoons, internal SAP transfers):
  those often post only on their own career pages and won't all appear in the
  Arbeitsagentur DB — keep those manual, or add per-site checks later.
- **Sharper scoring:** uncomment `CLAUDE_MODEL: claude-sonnet-5` in the workflow.
- **SSL errors** from the API on some networks: set env `VERIFY_SSL=false`.
- **Timezone:** the cron is UTC. `0 5 * * *` lands around 6–7am German time.
