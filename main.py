"""Daily job agent: fetch new German job postings, score them against your CV,
send the best ones to Telegram and/or email.

Pipeline, in order:

    fetch (every FeedSource)
      -> drop already-seen
      -> dedupe within the run
      -> cheap filter        pure Python, no tokens
      -> scoring budget cut
      -> fetch advert bodies only for what's left
      -> LLM score
      -> rank
      -> digest

The filter sits before the budget cut on purpose: noise gets discarded for free,
so the budget is spent on plausible roles rather than used up by whatever the
search happened to return first.
"""
try:  # load a local .env for running on your machine (no-op in GitHub Actions)
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import argparse
from dataclasses import replace

import email_notify
import notify
import scoring
import screening
import storage
from ba import BASource
from config import MAX_JOBS_TO_SCORE, MIN_SCORE, TOP_N
from sources import interleave

# Every feed the digest draws from. Appending one here is the only wiring a new
# source needs; nothing below this line knows how many there are.
SOURCES = [BASource()]


def collect(seen):
    """Everything worth scoring today, best-first-ish, already filtered.

    Round-robins across feeds so one chatty source can't eat the whole scoring
    budget, then drops in three passes: already sent, duplicate of something
    earlier in this run, and finally the title/location gate.
    """
    stats = {"fetched": 0, "seen": 0, "dup": 0, "title": 0, "location": 0}
    kept, keys_this_run = [], set()

    for p in interleave([s.fetch() for s in SOURCES]):
        stats["fetched"] += 1
        keys = screening.seen_keys(p)

        if keys & seen:
            stats["seen"] += 1
            continue
        if keys & keys_this_run:
            # Same job from two feeds, or two adverts for one role. First wins,
            # and feeds are ordered so the one we'd rather link to comes first.
            stats["dup"] += 1
            continue

        ok, why = screening.passes(p)
        if not ok:
            stats[why] += 1
            continue

        keys_this_run |= keys
        kept.append(p)

    return kept, stats


def describe_all(postings):
    """Fill in advert bodies. One network request per posting, so this runs
    after the budget cut and never for a posting we've already discarded."""
    by_name = {s.name: s for s in SOURCES}
    out = []
    for p in postings:
        source = by_name.get(p.source)
        try:
            text = source.describe(p) if source else ""
        except Exception as e:
            print(f"  description fetch failed for {p.source_id}: {e}")
            text = ""
        out.append(replace(p, description=text))
    return out


def format_message(scored):
    """Telegram HTML digest (newline-separated, chunked by notify.send)."""
    lines = [f"<b>🌅 {len(scored)} job(s) for you today</b>", ""]
    for score, reason, p in scored:
        lines.append(f'<b>[{score}/10]</b> <a href="{notify.esc(p.url)}">{notify.esc(p.title)}</a>')
        lines.append(f"🏢 {notify.esc(p.company)}")
        lines.append(f"💡 {notify.esc(reason)}")
        lines.append("")
    return "\n".join(lines)


def format_email(scored):
    """Standalone HTML digest for email (block elements, not bare newlines)."""
    blocks = []
    for score, reason, p in scored:
        blocks.append(
            '<div style="margin:0 0 18px;line-height:1.5">'
            f'<div><b>[{score}/10]</b> <a href="{notify.esc(p.url)}">{notify.esc(p.title)}</a></div>'
            f'<div>🏢 {notify.esc(p.company)}</div>'
            f'<div>💡 {notify.esc(reason)}</div>'
            '</div>'
        )
    return (
        '<div style="font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif">'
        f'<h2>🌅 {len(scored)} job(s) for you today</h2>'
        + "".join(blocks)
        + '</div>'
    )


def deliver(top):
    """Send the digest to every configured channel.

    Returns the number of channels that succeeded. Raises if no channel is
    configured or if all of them fail, so main() leaves the jobs unseen and they
    get retried on the next run."""
    channels = []
    if notify.enabled():
        channels.append(("Telegram", lambda: notify.send(format_message(top))))
    if email_notify.enabled():
        subject = f"🌅 {len(top)} job(s) for you today"
        channels.append(("Email", lambda: email_notify.send(subject, format_email(top))))

    if not channels:
        raise RuntimeError(
            "No delivery channel configured. Set TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID "
            "and/or GMAIL_ADDRESS/GMAIL_APP_PASSWORD."
        )

    sent, errors = 0, []
    for name, fn in channels:
        try:
            fn()
            print(f"  ✓ {name} digest sent.")
            sent += 1
        except Exception as e:
            print(f"  ✗ {name} send failed: {e}")
            errors.append(f"{name}: {e}")

    if sent == 0:
        raise RuntimeError("all delivery channels failed: " + "; ".join(errors))
    return sent


def dry_run(limit):
    """Everything except the model and the senders.

    Fetches and filters for real, so it proves the live wiring, but makes no
    OpenAI call, sends nothing, and never writes seen.json. Needs no
    OPENAI_API_KEY. Prints what a real run would have scored.
    """
    seen = storage.load_seen()
    candidates, stats = collect(seen)
    print(f"{stats['fetched']} posting(s) fetched from {len(SOURCES)} source(s); "
          f"dropped {stats['seen']} seen, {stats['dup']} duplicate, "
          f"{stats['title']} on title, {stats['location']} on location")
    print(f"{len(candidates)} candidate(s) would be scored "
          f"({min(len(candidates), MAX_JOBS_TO_SCORE)} this run, "
          f"{max(0, len(candidates) - MAX_JOBS_TO_SCORE)} deferred)\n")

    shown = candidates[:limit]
    for p in describe_all(shown):
        flag = "" if p.description else "   [no advert text]"
        print(f"  {len(p.description):5} chars  {p.plz:5}  {p.title[:52]:54}{flag}")
        print(f"         {p.company[:60]}")
    print(f"\n{len(shown)} advert body(ies) fetched. "
          f"No model calls, nothing sent, seen.json untouched.")
    print(f"Telegram configured: {notify.enabled()} | email configured: {email_notify.enabled()}")


def main():
    seen = storage.load_seen()
    candidates, stats = collect(seen)
    print(
        f"{stats['fetched']} posting(s) fetched from {len(SOURCES)} source(s); "
        f"dropped {stats['seen']} seen, {stats['dup']} duplicate, "
        f"{stats['title']} on title, {stats['location']} on location"
    )
    print(f"{len(candidates)} candidate(s) left for scoring")

    if not candidates:
        print("Nothing new today.")
        return

    cv = scoring.load_cv()
    # Only scored postings get marked seen. Anything past the budget stays
    # unseen so the next run picks it up (see DAYS_BACK in config.py).
    batch = candidates[:MAX_JOBS_TO_SCORE]
    deferred = len(candidates) - len(batch)
    if deferred:
        print(f"  scoring budget reached, {deferred} posting(s) deferred to the next run")

    scored = []
    for p in describe_all(batch):
        s, reason = scoring.score_job(cv, p)
        scored.append((s, reason, p))
        seen |= screening.seen_keys(p)

    scored.sort(key=lambda x: x[0], reverse=True)
    top = [t for t in scored if t[0] >= MIN_SCORE][:TOP_N]
    print(f"{len(top)} job(s) scored >= {MIN_SCORE}")

    if top:
        deliver(top)  # raises unless at least one channel succeeds
        storage.save_seen(seen)  # only mark seen after a successful send
    else:
        storage.save_seen(seen)
        print("No jobs above threshold; nothing sent.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true",
                    help="fetch and filter only: no model calls, no send, no state write")
    ap.add_argument("--limit", type=int, default=5, metavar="N",
                    help="with --dry-run, how many advert bodies to fetch (default 5)")
    args = ap.parse_args()
    dry_run(args.limit) if args.dry_run else main()
