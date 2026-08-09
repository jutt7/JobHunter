"""Daily job agent: fetch new German job postings, score them against your CV,
send the best ones to Telegram and/or email."""
try:  # load a local .env for running on your machine (no-op in GitHub Actions)
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from itertools import zip_longest

import email_notify
import notify
import scoring
import storage
from arbeitsagentur import employer, job_url, ref as job_ref, search, title
from config import (DAYS_BACK, MAX_JOBS_TO_SCORE, MIN_SCORE, SEARCH_PROFILES,
                    TOP_N)


def collect_new_jobs(seen):
    """Run every search profile, merge results, drop anything already seen.

    Results are interleaved round-robin rather than concatenated. The scoring
    budget cuts off the tail of this dict, so concatenating would always defer
    the last profiles in SEARCH_PROFILES; interleaving spreads the cut evenly.
    """
    per_profile = []
    for prof in SEARCH_PROFILES:
        try:
            jobs = search(
                was=prof["was"],
                wo=prof.get("wo"),
                umkreis=prof.get("umkreis", 25),
                arbeitszeit=prof.get("arbeitszeit"),
                veroeffentlichtseit=DAYS_BACK,
            )
        except Exception as e:
            print(f"  search failed for {prof}: {e}")
            continue
        per_profile.append(jobs)

    found = {}
    for row in zip_longest(*per_profile):
        for j in row:
            if j is None:
                continue
            ref = job_ref(j)
            if ref and ref not in seen and ref not in found:
                found[ref] = j
    return found


def format_message(scored):
    """Telegram HTML digest (newline-separated, chunked by notify.send)."""
    lines = [f"<b>🌅 {len(scored)} job(s) for you today</b>", ""]
    for score, reason, job in scored:
        url = notify.esc(job_url(job))
        job_title = notify.esc(title(job))
        emp = notify.esc(employer(job))
        lines.append(f'<b>[{score}/10]</b> <a href="{url}">{job_title}</a>')
        lines.append(f"🏢 {emp}")
        lines.append(f"💡 {notify.esc(reason)}")
        lines.append("")
    return "\n".join(lines)


def format_email(scored):
    """Standalone HTML digest for email (block elements, not bare newlines)."""
    blocks = []
    for score, reason, job in scored:
        url = notify.esc(job_url(job))
        job_title = notify.esc(title(job))
        emp = notify.esc(employer(job))
        blocks.append(
            '<div style="margin:0 0 18px;line-height:1.5">'
            f'<div><b>[{score}/10]</b> <a href="{url}">{job_title}</a></div>'
            f'<div>🏢 {emp}</div>'
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


def main():
    seen = storage.load_seen()
    new_jobs = collect_new_jobs(seen)
    print(f"{len(new_jobs)} new job(s) found across {len(SEARCH_PROFILES)} searches")

    if not new_jobs:
        print("Nothing new today.")
        return

    cv = scoring.load_cv()
    scored = []
    # Only scored jobs get marked seen. Anything past the budget stays unseen so
    # the next run picks it up (see DAYS_BACK in config.py).
    batch = list(new_jobs.items())[:MAX_JOBS_TO_SCORE]
    skipped = len(new_jobs) - len(batch)
    if skipped:
        print(f"  scoring budget reached, {skipped} job(s) deferred to the next run")

    for ref, job in batch:
        s, reason = scoring.score_job(cv, job)
        scored.append((s, reason, job))
        seen.add(ref)

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
    main()
