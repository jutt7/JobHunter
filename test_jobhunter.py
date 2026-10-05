"""Offline tests: no network, no OpenAI key, no delivery.

    python -m unittest test_jobhunter -v

Everything here runs against testdata/ba_search.json, a trimmed capture of real
Arbeitsagentur search responses, so the fixtures are shaped like the real API
rather than like what the code happens to expect.

Several tests are named for a specific filter bug. Those are regressions: the
patterns they cover all silently dropped postings we wanted, and a plausible
"tidy-up" of the regexes reintroduces them.
"""
import contextlib
import io
import json
import os
import unittest
from pathlib import Path

os.environ.pop("OPENAI_API_KEY", None)   # nothing here may call the model

import arbeitsagentur
import config
import main
import screening
from ba import BASource
from sources import Posting, interleave

FIXTURE = json.loads((Path(__file__).parent / "testdata" / "ba_search.json").read_text("utf-8"))


def posting(title="Frontend Developer (m/w/d)", company="ACME GmbH", plz="50667",
            source="ba", source_id="REF-1", url="https://example.invalid/1"):
    return Posting(source=source, source_id=source_id, title=title, company=company,
                   location="Köln, Nordrhein-Westfalen", plz=plz, url=url)


class GenderMarkers(unittest.TestCase):
    def test_brief_variants_collapse(self):
        """The (m/w/d) family all reduce to the same bare title."""
        for t in ["Frontend Developer (m/w/d)", "Frontend Developer (all genders)",
                  "Frontend Developer (w/m/x)", "Frontend Developer (m/f/d)",
                  "Frontend Developer (all gender)"]:
            self.assertEqual(screening.strip_gender_suffix(t), "Frontend Developer", t)

    def test_unseparated_run(self):
        """(gn) and (mwd) have no slashes — a separator-only pattern misses them."""
        self.assertEqual(screening.strip_gender_suffix("Senior Software Developer (gn)"),
                         "Senior Software Developer")
        self.assertEqual(screening.strip_gender_suffix("Entwickler (mwd)"), "Entwickler")

    def test_inclusive_endings(self):
        for t, want in [("Frontend-Entwickler:in", "Frontend-Entwickler"),
                        ("Softwareentwickler*in Web", "Softwareentwickler Web"),
                        ("Entwickler_in", "Entwickler"),
                        ("Entwickler (in)", "Entwickler")]:
            self.assertEqual(screening.strip_gender_suffix(t), want, t)

    def test_does_not_eat_meaningful_parentheses(self):
        for t in ["Entwickler (Teilzeit)", "Developer (2 Stellen)",
                  "Entwickler (Remote)", "Consultant (SAP)"]:
            self.assertEqual(screening.strip_gender_suffix(t), t, t)


class Slugs(unittest.TestCase):
    def test_umlauts_fold_the_german_way(self):
        """Müller GmbH and Mueller GmbH are routinely the same employer."""
        self.assertEqual(screening.slug("Müller GmbH"), screening.slug("Mueller GmbH"))
        self.assertEqual(screening.slug("Müller GmbH"), "mueller-gmbh")
        self.assertEqual(screening.slug("Weiß & Söhne"), screening.slug("Weiss und Soehne").replace("und-", ""))

    def test_separators_normalise(self):
        self.assertEqual(screening.slug("Frontend-Entwickler"), screening.slug("Frontend  Entwickler"))


class DedupeKey(unittest.TestCase):
    def test_ignores_url_and_id(self):
        """The jobvector trap: a refreshed advert gets a new id/url, same job."""
        a = posting(source_id="REF-A", url="https://a.invalid")
        b = posting(source_id="REF-B", url="https://b.invalid")
        self.assertEqual(screening.dedupe_key(a), screening.dedupe_key(b))

    def test_collides_across_sources(self):
        """Same job from the BA and from an employer's ATS is one job."""
        ba = posting(title="Frontend Developer (m/w/d)")
        ats = posting(title="Frontend Developer (w/m/x)", source="ats:personio", source_id="99")
        self.assertEqual(screening.dedupe_key(ba), screening.dedupe_key(ats))

    def test_separates_different_jobs(self):
        self.assertNotEqual(screening.dedupe_key(posting()),
                            screening.dedupe_key(posting(company="Other GmbH")))
        self.assertNotEqual(screening.dedupe_key(posting()),
                            screening.dedupe_key(posting(plz="10115")))

    def test_is_opaque(self):
        """seen.json is committed to a public repo; keys must not leak employers."""
        key = screening.dedupe_key(posting(company="ACME GmbH"))
        self.assertNotIn("acme", key.lower())
        self.assertEqual(len(key), 40)


class SeenKeys(unittest.TestCase):
    def test_legacy_bare_refnr_still_matches(self):
        """seen.json predates this module and holds bare BA reference numbers.
        If this breaks, the first run after deploy re-sends everything in it."""
        p = posting(source="ba", source_id="10000-1207391408-S")
        self.assertIn("10000-1207391408-S", screening.seen_keys(p))

    def test_other_sources_are_qualified(self):
        """An ATS numbering postings 1,2,3 must not collide with a BA refnr."""
        ba = posting(source="ba", source_id="99")
        ats = posting(source="ats:personio", source_id="99", company="Zzz GmbH")
        self.assertFalse(screening.seen_keys(ba) & screening.seen_keys(ats))
        self.assertNotIn("99", screening.seen_keys(ats))


class TitleFilter(unittest.TestCase):
    def test_keeps_target_roles(self):
        for t in ["Frontend Developer (m/w/d)", "Fullstack Entwickler React (m/w/d)",
                  "Softwareentwickler Web", "React TypeScript Entwickler",
                  "Software Engineer (m/w/d)", "Next.js Developer"]:
            self.assertTrue(screening.title_ok(t), t)

    def test_regression_developer_stem(self):
        """`software.?(engineer|entwickl)` missed "Software Developer", and
        `web.?entwickl` missed "Web Developer" — two of the commonest English
        titles on German boards."""
        for t in ["Software Developer Python (m/w/d)", "(Junior) Software Developer Java (m/w/d)",
                  "Web Developer (m/w/d)", "Webapplication - Developer (m/w/d)"]:
            self.assertTrue(screening.title_ok(t), t)

    def test_regression_dual_needs_word_boundary(self):
        """Bare `dual` also matches Indivi(dual)software-Entwickler, a real title."""
        self.assertTrue(screening.title_ok("Individualsoftware-Entwickler (m/w/d)"))
        self.assertFalse(screening.title_ok("Dualer Student Informatik (m/w/d)"))

    def test_regression_parenthesised_seniority_is_open_level(self):
        """"(Senior) X" is German-advert shorthand for "mid or senior welcome"."""
        for t in ["(Senior) Full-Stack Software Engineer (m/w/d)",
                  "(Senior) Full Stack Product Engineer (m/w/d)",
                  "(Junior) Software Developer Java (m/w/d)"]:
            self.assertTrue(screening.title_ok(t), t)

    def test_bare_seniority_still_excluded(self):
        for t in ["Senior Web Developer (m/w/d)", "Senior Full Stack Engineer (m/w/d)",
                  "Lead Frontend Engineer (m/w/d)", "Principal Software Engineer (all genders)",
                  "#15064 Senior Java Full-Stack Developer (m/w/d)",
                  "Werkstudent Frontend (m/w/d)", "Praktikum Frontend Entwicklung"]:
            self.assertFalse(screening.title_ok(t), t)

    def test_offtarget_excluded(self):
        for t in ["Expert 3D-Artist (m/w/d)", "IT Consultant MS 365 (m/w/d)",
                  "Pflegefachkraft (m/w/d)"]:
            self.assertFalse(screening.title_ok(t), t)


class FilterMatchesSearches(unittest.TestCase):
    """config.py has two lists that must agree with each other.

    SEARCH_PROFILES decides what we ask the API for; TITLE_INCLUDE decides what
    we keep. When they drift we pay for searches whose results are then thrown
    away unscored — which is exactly what happened to the Next.js profile.
    """

    def test_every_search_profile_survives_its_own_filter(self):
        dropped = [p["was"] for p in config.SEARCH_PROFILES
                   if not screening.title_ok(p["was"])]
        self.assertEqual(dropped, [],
                         f"searched for but filtered out: {dropped}")


class LocationFilter(unittest.TestCase):
    def test_empty_allowlist_accepts_everything(self):
        self.assertEqual(config.PLZ_PREFIX_ALLOWLIST, [], "default must stay nationwide")
        self.assertTrue(screening.location_ok("50667"))
        self.assertTrue(screening.location_ok(""))

    def test_prefix_allowlist(self):
        original = config.PLZ_PREFIX_ALLOWLIST
        screening_module_list = ["67", "68"]
        config.PLZ_PREFIX_ALLOWLIST[:] = screening_module_list
        try:
            self.assertTrue(screening.location_ok("67655"))
            self.assertFalse(screening.location_ok("10115"))
            self.assertTrue(screening.location_ok(""), "no PLZ is not evidence of a bad location")
        finally:
            config.PLZ_PREFIX_ALLOWLIST[:] = original


class Normalisation(unittest.TestCase):
    """BASource turns real API payloads into Postings."""

    def setUp(self):
        self.rows = [j for rows in FIXTURE.values() for j in rows]

    def test_every_fixture_row_normalises(self):
        src = BASource()
        for raw in self.rows:
            p = src._to_posting(raw)
            self.assertEqual(p.source, "ba")
            self.assertTrue(p.source_id and p.title)
            self.assertIsInstance(p.plz, str)

    def test_multi_location_takes_the_first_plz(self):
        multi = [r for r in self.rows if len(r.get("stellenlokationen") or []) > 1]
        self.assertTrue(multi, "fixture should contain a multi-location posting")
        p = BASource()._to_posting(multi[0])
        self.assertEqual(p.plz, multi[0]["stellenlokationen"][0]["adresse"]["plz"])

    def test_prefers_employer_url(self):
        ext = [r for r in self.rows if r.get("externeURL")]
        self.assertTrue(ext, "fixture should contain an externeURL posting")
        self.assertEqual(BASource()._to_posting(ext[0]).url, ext[0]["externeURL"])

    def test_falls_back_to_ba_detail_page(self):
        plain = [r for r in self.rows if not r.get("externeURL")][0]
        self.assertIn("arbeitsagentur.de", BASource()._to_posting(plain).url)


class Interleave(unittest.TestCase):
    def test_round_robin(self):
        self.assertEqual(list(interleave([[1, 2, 3], ["a", "b"]])), [1, "a", 2, "b", 3])

    def test_tolerates_empty(self):
        self.assertEqual(list(interleave([[], [1], []])), [1])


class Pipeline(unittest.TestCase):
    """main.collect() over the fixture, with the API stubbed out."""

    def setUp(self):
        self._search = arbeitsagentur.search
        arbeitsagentur.search = lambda was, **kw: FIXTURE.get(was, [])
        self.addCleanup(lambda: setattr(arbeitsagentur, "search", self._search))

    def test_in_feed_dedupe(self):
        """Search profiles overlap heavily; one refnr must be yielded once."""
        ids = [p.source_id for p in BASource().fetch()]
        self.assertEqual(len(ids), len(set(ids)))

    def test_collect_counts_add_up(self):
        kept, st = main.collect(set())
        self.assertEqual(st["fetched"],
                         len(kept) + st["seen"] + st["dup"] + st["title"] + st["location"])
        self.assertTrue(kept, "fixture should yield some candidates")

    def test_filter_actually_drops_something(self):
        _, st = main.collect(set())
        self.assertGreater(st["title"], 0, "fixture includes senior/backend titles")

    def test_already_seen_are_dropped(self):
        kept, _ = main.collect(set())
        again, st = main.collect({p.source_id for p in kept})
        self.assertEqual(st["seen"], len(kept))
        self.assertLess(len(again), len(kept))

    def test_nothing_survives_a_fully_seen_run(self):
        kept, _ = main.collect(set())
        seen = set().union(*[screening.seen_keys(p) for p in kept])
        self.assertEqual(main.collect(seen)[0], [])


class LazyDescriptions(unittest.TestCase):
    """The invariant the whole design rests on: no advert body is fetched for a
    posting that dedupe, the filter or the budget was going to discard."""

    def setUp(self):
        self._search = arbeitsagentur.search
        arbeitsagentur.search = lambda was, **kw: FIXTURE.get(was, [])
        self.addCleanup(lambda: setattr(arbeitsagentur, "search", self._search))

    def test_describe_called_only_for_the_scored_batch(self):
        calls = []
        src = main.SOURCES[0]
        original = src.describe
        src.describe = lambda p: (calls.append(p.source_id), "body")[1]
        self.addCleanup(lambda: setattr(src, "describe", original))

        kept, st = main.collect(set())
        batch = kept[:3]
        out = main.describe_all(batch)

        self.assertEqual(len(calls), len(batch))
        self.assertEqual(calls, [p.source_id for p in batch])
        self.assertTrue(all(p.description == "body" for p in out))
        self.assertGreater(st["title"], 0)
        self.assertNotIn("", calls)

    def test_a_failing_describe_does_not_sink_the_run(self):
        src = main.SOURCES[0]
        original = src.describe
        src.describe = lambda p: (_ for _ in ()).throw(RuntimeError("502"))
        self.addCleanup(lambda: setattr(src, "describe", original))
        log = io.StringIO()
        with contextlib.redirect_stdout(log):      # the warning is expected
            out = main.describe_all([posting()])
        self.assertEqual(out[0].description, "")
        self.assertIn("502", log.getvalue())


class Digest(unittest.TestCase):
    def setUp(self):
        self.scored = [
            (9, "Strong React/TypeScript overlap", posting(title="Frontend Developer (m/w/d)")),
            (7, "Good fit, German B2 wanted", posting(title="Fullstack Engineer",
                                                     company="Beta & Co <GmbH>",
                                                     url="https://x.invalid/?a=1&b=2")),
        ]

    def test_telegram_digest(self):
        msg = main.format_message(self.scored)
        self.assertIn("<b>🌅 2 job(s) for you today</b>", msg)
        self.assertIn("<b>[9/10]</b>", msg)
        self.assertIn("Frontend Developer (m/w/d)", msg)
        self.assertIn("Strong React/TypeScript overlap", msg)

    def test_html_is_escaped(self):
        """Employer names and URLs go straight into HTML; Telegram rejects
        malformed markup, which would fail the whole send."""
        msg = main.format_message(self.scored)
        self.assertIn("Beta &amp; Co &lt;GmbH&gt;", msg)
        self.assertNotIn("<GmbH>", msg)
        self.assertIn("a=1&amp;b=2", msg)

    def test_email_digest_is_self_contained(self):
        html = main.format_email(self.scored)
        self.assertTrue(html.startswith("<div"))
        self.assertIn("<h2>🌅 2 job(s) for you today</h2>", html)
        self.assertIn("Beta &amp; Co &lt;GmbH&gt;", html)
        self.assertNotIn("\n", html.strip().replace("\n", ""))

    def test_empty_digest(self):
        self.assertIn("0 job(s)", main.format_message([]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
