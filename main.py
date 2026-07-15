"""Daily job agent: fetch new German job postings, score them against your CV
with OpenAI, and send the best ones to Telegram."""
import notify
import scoring
import storage
from arbeitsagentur import job_url, search
from config import (DAYS_BACK, MAX_JOBS_TO_SCORE, MIN_SCORE, SEARCH_PROFILES,
                    TOP_N)


def collect_new_jobs(seen):
    """Run every search profile, merge results, drop anything already seen."""
    found = {}
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
        for j in jobs:
            ref = j.get("refnr")
            if ref and ref not in seen and ref not in found:
                found[ref] = j
    return found


def format_message(scored):
    lines = [f"<b>🌅 {len(scored)} job(s) for you today</b>", ""]
    for score, reason, job in scored:
        url = notify.esc(job_url(job))
        title = notify.esc(job.get("titel"))
        emp = notify.esc(job.get("arbeitgeber"))
        lines.append(f'<b>[{score}/10]</b> <a href="{url}">{title}</a>')
        lines.append(f"🏢 {emp}")
        lines.append(f"💡 {notify.esc(reason)}")
        lines.append("")
    return "\n".join(lines)


def main():
    seen = storage.load_seen()
    new_jobs = collect_new_jobs(seen)
    print(f"{len(new_jobs)} new job(s) found across {len(SEARCH_PROFILES)} searches")

    if not new_jobs:
        print("Nothing new today.")
        return

    cv = scoring.load_cv()
    scored = []
    for i, (ref, job) in enumerate(new_jobs.items()):
        if i < MAX_JOBS_TO_SCORE:
            s, reason = scoring.score_job(cv, job)
            scored.append((s, reason, job))
        seen.add(ref)  # mark seen regardless, so it won't recur tomorrow

    scored.sort(key=lambda x: x[0], reverse=True)
    top = [t for t in scored if t[0] >= MIN_SCORE][:TOP_N]
    print(f"{len(top)} job(s) scored >= {MIN_SCORE}")

    if top:
        notify.send(format_message(top))
        print("Digest sent.")
    else:
        print("No jobs above threshold; nothing sent.")

    storage.save_seen(seen)


if __name__ == "__main__":
    main()
