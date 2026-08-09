"""Find the working job-detail endpoint.

Run: python probe_detail.py

The BA has moved this endpoint before. Tries a matrix of path versions against
reference-number encodings, reports which combination returns 200, and dumps the
JSON keys so DETAIL and _DESC_FIELDS in arbeitsagentur.py can be repointed. Also
dumps the search result's keys in case the advert text ever lands there and the
second request becomes unnecessary.
"""
import base64
import json
import urllib.parse

import requests

from arbeitsagentur import HEADERS, VERIFY_SSL, ref, search, title

PATHS = [
    "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v2/jobdetails/{}",
    "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobdetails/{}",
    "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v5/jobdetails/{}",
    "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v6/jobdetails/{}",
    "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v6/jobs/{}",
    "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/ed/v1/jobdetails/{}",
]


def encodings(r):
    b64 = base64.b64encode(r.encode()).decode()
    return [
        ("b64", b64),
        ("b64-nopad", b64.rstrip("=")),
        ("b64-urlsafe-nopad", base64.urlsafe_b64encode(r.encode()).decode().rstrip("=")),
        ("raw", r),
        ("raw-quoted", urllib.parse.quote(r, safe="")),
    ]


jobs = search(was="Frontend Developer React", veroeffentlichtseit=7, size=1)
if not jobs:
    raise SystemExit("No jobs returned. Try a wider veroeffentlichtseit.")

job = jobs[0]
r = ref(job)
print("job  : %s" % title(job))
print("ref  : %s\n" % r)

print("=" * 70)
print("SEARCH RESULT KEYS")
print("=" * 70)
for k, v in sorted(job.items()):
    preview = json.dumps(v, ensure_ascii=False)[:90] if not isinstance(v, str) else repr(v[:90])
    print("  %-32s %s" % (k, preview))

print()
print("=" * 70)
print("ENDPOINT PROBE")
print("=" * 70)
hits = []
for path in PATHS:
    for name, enc in encodings(r):
        url = path.format(enc)
        try:
            resp = requests.get(url, headers=HEADERS, verify=VERIFY_SSL, timeout=20)
            code = resp.status_code
        except Exception as e:
            print("  ERR  %-58s %s" % (path.split("/")[-2] + "/" + name, type(e).__name__))
            continue
        marker = "OK  " if code == 200 else "    "
        print("  %s%-20s %-20s -> %s" % (marker, path.split("/service/")[-1].split("/{")[0], name, code))
        if code == 200:
            hits.append((url, resp))
        # a 404 on the first encoding means the path itself is wrong
        if code == 404 and name == "b64":
            break

print()
if not hits:
    print("No combination returned 200. The detail API may need an OAuth token.")
    print("If the search keys above include a description field, use that")
    print("instead and drop the second request.")
else:
    url, resp = hits[0]
    print("WORKING: %s" % url)
    try:
        data = resp.json()
        print("top-level keys: %s" % sorted(data))
        for k, v in sorted(data.items()):
            if isinstance(v, str) and len(v) > 200:
                print("\n  candidate description field: %r (%d chars)" % (k, len(v)))
                print("  %r" % v[:200])
    except Exception as e:
        print("200 but not JSON: %s / %r" % (e, resp.text[:200]))
