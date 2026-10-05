"""Free filtering: dedupe and a title/location gate, both pure Python.

Everything here runs before the LLM. That ordering is the whole point — the
scoring budget is spent on postings that survive this, so noise costs nothing
instead of costing a token call.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata

from config import PLZ_PREFIX_ALLOWLIST, TITLE_EXCLUDE, TITLE_INCLUDE
from sources import Posting

_INCLUDE_RE = re.compile(TITLE_INCLUDE, re.I | re.X)
_EXCLUDE_RE = re.compile(TITLE_EXCLUDE, re.I | re.X)

# German adverts almost never say just "Frontend Developer". They say
# "Frontend Developer (m/w/d)" or "Frontend-Entwickler:in", and the same job
# syndicated to two boards often picks a different one of these. Stripping them
# is what makes the dedupe key stable across sources.
_GENDER_TAG = re.compile(
    r"""\(\s*(?:
          # The + allows unseparated runs: (gn) and (mwd) as well as (m/w/d).
          [mwfdxgn]+(?:\s*[/|,\-]\s*[mwfdxgn]+)*   # (m/w/d) (w/m/x) (f/m/d) (gn) (d)
        | all[\s\-]*genders?                      # (all genders) (all gender)
        | alle[\s\-]*geschlechter
        | in                                      # (in)
      )\s*\)""",
    re.I | re.X,
)
# Gender-neutral German word endings: Entwickler:in, Entwickler*in, Entwickler_in
_INCLUSIVE_ENDING = re.compile(r"[:*_]in\b", re.I)

_UMLAUTS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
                          "Ä": "ae", "Ö": "oe", "Ü": "ue"})


def strip_gender_suffix(title: str) -> str:
    """Drop the (m/w/d)-family markers and :in endings from a title."""
    out = _GENDER_TAG.sub(" ", title or "")
    out = _INCLUSIVE_ENDING.sub("", out)
    return re.sub(r"\s+", " ", out).strip(" -–—,;:/")


def slug(s: str) -> str:
    """Lowercase ASCII skeleton of a string, for comparing names.

    Folds umlauts the German way (ü -> ue) before stripping accents, so
    "Müller GmbH" and "Mueller GmbH" collapse to the same thing — they are
    routinely the same employer typed two ways.
    """
    s = (s or "").translate(_UMLAUTS)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return "-".join(re.findall(r"[a-z0-9]+", s))


def dedupe_key(p: Posting) -> str:
    """Identity of the *job*, not of the advert.

    Deliberately excludes the URL and any date. jobvector-style boards refresh a
    posting's date during its run, and the same job reaches us under different
    URLs from different feeds; keying on either resurfaces jobs we already sent.

    Hashed rather than stored readable because seen.json is committed to a
    public repo — the digest of who is hiring for what stays opaque.
    """
    basis = f"{slug(p.company)}|{slug(strip_gender_suffix(p.title))}|{p.plz}"
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()


# The one source whose ids are already in seen.json unqualified, from before
# this module existed. Only it gets the bare-id compatibility key; qualifying
# everything else keeps a future feed with small integer ids (an ATS board
# numbering postings 1, 2, 3) from colliding with an unrelated BA refnr.
_LEGACY_BARE_ID_SOURCE = "ba"


def seen_keys(p: Posting) -> set[str]:
    """Every key under which this posting counts as already-sent.

    `dedupe_key` is the cross-source identity we want going forward;
    `<source>:<id>` pins a posting within its own feed even when the content
    hash can't match (a retitled advert). Checking and writing both means the
    existing seen.json keeps working with no migration step, instead of
    silently re-sending everything in it on the first run after this change.
    """
    keys = {dedupe_key(p), f"{p.source}:{p.source_id}"}
    if p.source == _LEGACY_BARE_ID_SOURCE:
        keys.add(p.source_id)
    return keys


# "(Senior) Full-Stack Engineer" is a German-advert convention for "we'll take
# mid or senior", so the bracketed form must not trip the seniority exclusion
# the way a bare "Senior Full-Stack Engineer" should.
_OPTIONAL_LEVEL = re.compile(r"\(\s*(?:senior|junior|jr|sr)\.?\s*\)", re.I)


def title_ok(title: str) -> bool:
    """Title looks like a role worth paying the model to judge."""
    t = _OPTIONAL_LEVEL.sub(" ", strip_gender_suffix(title))
    return bool(_INCLUDE_RE.search(t)) and not _EXCLUDE_RE.search(t)


def location_ok(plz: str) -> bool:
    """Postal-code gate. Empty allowlist means all of Germany, which is the
    default because relocating anywhere is in the target profile."""
    if not PLZ_PREFIX_ALLOWLIST:
        return True
    if not plz:
        return True          # no PLZ is not evidence of a bad location
    return any(plz.startswith(prefix) for prefix in PLZ_PREFIX_ALLOWLIST)


def passes(p: Posting) -> tuple[bool, str]:
    """(keep?, why not) — the reason string is for the run log."""
    if not title_ok(p.title):
        return False, "title"
    if not location_ok(p.plz):
        return False, "location"
    return True, ""
