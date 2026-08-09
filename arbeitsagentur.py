"""Client for the Arbeitsagentur (Federal Employment Agency) job API.

No signup needed; the API key below is the public static key the Jobsuche web
app uses.

Version skew to be aware of: search lives on /pc/v6/jobs, job details on
/pc/v4/jobdetails. v2, v5 and v6 detail paths all return 403, so the two
versions here are correct and not a typo. Field accessors at the bottom are the
only place that knows the v6 response names.
"""
import base64
import os
import re
from html.parser import HTMLParser

import requests

BASE = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v6/jobs"
DETAIL = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobdetails/{}"
HEADERS = {"X-API-Key": "jobboerse-jobsuche"}

# Some networks/certs are finicky; set VERIFY_SSL=false only if you hit SSL errors.
VERIFY_SSL = os.environ.get("VERIFY_SSL", "true").lower() != "false"


def search(was, wo=None, umkreis=25, veroeffentlichtseit=1,
           arbeitszeit=None, size=50):
    """Run one search. Returns a list of job dicts (may be empty).

    was              free-text query (job title / keywords), e.g. "React Entwickler"
    wo               city, e.g. "Berlin" (omit for nationwide)
    umkreis          radius in km around `wo`
    veroeffentlichtseit  only jobs published in the last N days (0-100)
    arbeitszeit      optional filter: "ho"=home office, "vz"=full-time,
                     "tz"=part-time. Join several with ";" e.g. "vz;ho".
    """
    params = {
        "was": was,
        "angebotsart": 1,          # 1 = regular employment (not training/etc.)
        "page": 1,
        "size": size,
        "veroeffentlichtseit": veroeffentlichtseit,
        "pav": "false",            # exclude private placement agencies
    }
    if wo:
        params["wo"] = wo
        params["umkreis"] = umkreis
    if arbeitszeit:
        params["arbeitszeit"] = arbeitszeit

    resp = requests.get(BASE, headers=HEADERS, params=params,
                        verify=VERIFY_SSL, timeout=60)
    resp.raise_for_status()
    return resp.json().get("ergebnisliste", []) or []


# --- field accessors (v6 names live here and nowhere else) -------------------

def ref(job):
    """Stable reference number, used as the de-duplication key in seen.json."""
    return job.get("referenznummer")


def title(job):
    return job.get("stellenangebotsTitel", "")


def employer(job):
    return job.get("firma", "")


def job_url(job):
    """Best clickable link for a posting: the employer's own URL if present,
    otherwise the Arbeitsagentur detail page."""
    if job.get("externeURL"):
        return job["externeURL"]
    return f"https://www.arbeitsagentur.de/jobsuche/jobdetail/{ref(job) or ''}"


def location_str(job):
    lokationen = job.get("stellenlokationen") or []
    if not lokationen:
        return ""
    adresse = lokationen[0].get("adresse", {}) or {}
    # v6 returns regions as enum-ish strings ("NORDRHEIN_WESTFALEN").
    region = (adresse.get("region") or "").replace("_", "-").title() or None
    parts = [adresse.get("ort"), region]
    return ", ".join(p for p in parts if p)


# --- advert text -------------------------------------------------------------
#
# Search results carry no posting text at all, so the full advert needs a second
# request per job. Best-effort by design: on any failure we return "" and the
# caller scores on title and location alone.

# First non-empty field wins. The others are older names, kept as fallbacks.
_DESC_FIELDS = (
    "stellenangebotsBeschreibung",
    "stellenbeschreibung",
    "arbeitgeberdarstellung",
    "beschreibung",
)

_MAX_DESC_CHARS = 6000


class _TextExtractor(HTMLParser):
    """Minimal HTML to text. Some adverts are HTML fragments and this avoids a
    BeautifulSoup dependency for one function."""

    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)

    def handle_starttag(self, tag, attrs):
        if tag in ("br", "p", "li", "div", "tr", "h1", "h2", "h3", "h4"):
            self.parts.append("\n")

    def text(self):
        return "".join(self.parts)


def _clean(raw):
    """Strip HTML, collapse whitespace, cap length."""
    if not raw:
        return ""
    text = str(raw)
    if "<" in text and ">" in text:
        parser = _TextExtractor()
        try:
            parser.feed(text)
            text = parser.text()
        except Exception:
            text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[ \t\xa0]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    text = "\n".join(line.strip() for line in text.split("\n")).strip()
    return text[:_MAX_DESC_CHARS]


def detail(job):
    """Raw detail payload for a job. Returns {} on any failure."""
    ref_nr = ref(job)
    if not ref_nr:
        return {}
    encoded = base64.b64encode(ref_nr.encode("utf-8")).decode("ascii")
    try:
        resp = requests.get(DETAIL.format(encoded), headers=HEADERS,
                            verify=VERIFY_SSL, timeout=30)
        if resp.status_code != 200:
            return {}
        data = resp.json()
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def description(job):
    """Advert text as plain text, or "" if unavailable."""
    data = detail(job)
    if not data:
        return ""
    for field in _DESC_FIELDS:
        cleaned = _clean(data.get(field))
        if cleaned:
            return cleaned
    return ""
