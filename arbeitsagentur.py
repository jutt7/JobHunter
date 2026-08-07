"""Thin client for the free Arbeitsagentur (Federal Employment Agency) job API.

No signup needed — the API key below is a public, static key used by the
Jobsuche web app. Endpoint returns Germany's largest job database (1M+ offers).

Note on versions: the BA retired /pc/v4/jobs (it now 404s) and the web app uses
/pc/v6/jobs, which also renamed most response fields. The accessors at the
bottom of this module are the single place that knows those field names.
"""
import os
import requests

BASE = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v6/jobs"
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
    """Stable reference number — used as the de-duplication key in seen.json."""
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
