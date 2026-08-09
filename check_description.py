"""Sanity check for the job-detail fetch.

Run: python check_description.py

If the char counts come back 0, the detail endpoint or its field names have
changed and scoring has quietly fallen back to title-only. Run probe_detail.py
to find the new endpoint.
"""
from arbeitsagentur import DETAIL, detail, description, ref, search, title

QUERY = "Frontend Developer React"

jobs = search(was=QUERY, veroeffentlichtseit=7, size=3)
print("search returned %d job(s) for %r\n" % (len(jobs), QUERY))

if not jobs:
    raise SystemExit("No jobs returned. Widen veroeffentlichtseit or change QUERY.")

ok = 0
for job in jobs:
    text = description(job)
    ok += bool(text)
    print("%-45s %6d chars" % (title(job)[:45], len(text)))
    print("   %r\n" % text[:120])

print("-" * 60)
if ok:
    print("OK: %d/%d jobs returned advert text." % (ok, len(jobs)))
else:
    print("FAILED: no advert text. Raw payload for the first job:")
    raw = detail(jobs[0])
    print("   endpoint : %s" % DETAIL.format("<base64 of %s>" % ref(jobs[0])))
    if not raw:
        print("   request failed or returned non-200 / non-JSON.")
    else:
        print("   top-level keys: %s" % sorted(raw))
