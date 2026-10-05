"""Arbeitsagentur as a FeedSource.

Thin adapter: arbeitsagentur.py stays the HTTP client that knows the v6 field
names, this turns what it returns into Postings. Keeping them apart means the
dev scripts (ab_models.py, check_description.py, probe_detail.py) that import
those accessors directly go on working.
"""
from __future__ import annotations

from typing import Iterable, Iterator

import arbeitsagentur as api
from config import DAYS_BACK, SEARCH_PROFILES
from sources import Posting, interleave


def _plz(job) -> str:
    """Postal code of the first listed location, "" if absent.

    First only: ~7% of postings list several (one advert gave eight cities), and
    a single PLZ is what the dedupe key wants. The cost is that a nationwide
    advert won't dedupe against the same job posted city-by-city elsewhere.
    """
    lokationen = job.get("stellenlokationen") or []
    if not lokationen:
        return ""
    return (lokationen[0].get("adresse", {}) or {}).get("plz") or ""


class BASource:
    """The Bundesagentur für Arbeit jobs API."""

    name = "ba"

    def fetch(self) -> Iterator[Posting]:
        """Run every search profile, round-robin the results together.

        Profiles overlap heavily (a React role matches four of them), so the
        same refnr arrives repeatedly; dropped here rather than downstream,
        since within one feed source_id is authoritative.
        """
        per_profile: list[list[Posting]] = []
        for prof in SEARCH_PROFILES:
            try:
                jobs = api.search(
                    was=prof["was"],
                    wo=prof.get("wo"),
                    umkreis=prof.get("umkreis", 25),
                    arbeitszeit=prof.get("arbeitszeit"),
                    veroeffentlichtseit=DAYS_BACK,
                )
            except Exception as e:
                print(f"  ba: search failed for {prof}: {e}")
                continue
            per_profile.append([self._to_posting(j) for j in jobs if api.ref(j)])

        emitted: set[str] = set()
        for posting in interleave(per_profile):
            if posting.source_id in emitted:
                continue
            emitted.add(posting.source_id)
            yield posting

    def _to_posting(self, job) -> Posting:
        return Posting(
            source=self.name,
            source_id=api.ref(job),
            title=api.title(job),
            company=api.employer(job),
            location=api.location_str(job),
            plz=_plz(job),
            # Already prefers the employer's own externeURL over the BA detail
            # page where the advert carries one (about 1 in 9 do).
            url=api.job_url(job),
        )

    def describe(self, posting: Posting) -> str:
        """One extra HTTP request per posting. Returns "" on any failure."""
        return api.description_by_ref(posting.source_id)
