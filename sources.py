"""The interface every job feed plugs into.

One normalised `Posting` and one `FeedSource` protocol, so the rest of the
pipeline (dedupe, filtering, scoring, digest) never learns where a job came
from. Adding a feed means writing one class here-shaped and appending it to
SOURCES in main.py; nothing else changes.

Two deliberate departures from the obvious design:

`description` is not filled in by fetch(). For the Arbeitsagentur every advert
body costs a second HTTP request, and the pipeline throws most postings away
before scoring (already seen, duplicate, title filtered, over the scoring
budget). So fetch() returns postings with an empty description and the pipeline
calls describe() only for the handful that actually reach the model. A feed that
already has the text in its search response just returns it.

No EnrichmentSource / CompanySource protocols yet. They were designed for
make-it-in-germany and the regional registries; until something implements one,
an unused Protocol is just a guess about a shape we haven't met.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import zip_longest
from typing import Iterable, Iterator, Protocol


@dataclass(frozen=True)
class Posting:
    """One job advert, normalised away from any feed's field names."""

    source: str        # which feed: "ba", later "ats:personio", ...
    source_id: str     # stable id within that feed (BA: referenznummer)
    title: str
    company: str
    location: str      # human-readable "Ort, Region", for the digest
    plz: str           # postal code, "" when the feed doesn't give one
    url: str           # best link; employer-direct beats aggregator
    description: str = ""   # advert body, filled in later by describe()


class FeedSource(Protocol):
    """A feed that yields postings."""

    name: str

    def fetch(self) -> Iterable[Posting]:
        """Every currently-advertised posting this feed knows about.

        Cheap fields only. Must not raise: a feed that is down should log and
        yield nothing rather than take the whole run with it.
        """
        ...

    def describe(self, posting: Posting) -> str:
        """Advert body for one of this feed's own postings, "" if unavailable.

        Called at most once per posting, only for postings that survive to
        scoring, so it is allowed to make a network request.
        """
        ...


def interleave(iterables: Iterable[Iterable]) -> Iterator:
    """Round-robin instead of concatenate.

    The scoring budget cuts off the tail of whatever order the pipeline is
    handed, so concatenating would permanently starve whichever feed (or search
    profile) happens to be last. Round-robin spreads the cut evenly. Used both
    across feeds and, inside the BA feed, across its search profiles.
    """
    for row in zip_longest(*[iter(it) for it in iterables]):
        for item in row:
            if item is not None:
                yield item
