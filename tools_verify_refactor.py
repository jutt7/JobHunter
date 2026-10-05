"""One-time check that the FeedSource refactor did not change the digest.

Replays the pre-refactor main.py and the current one over the same captured
Arbeitsagentur responses, with scoring stubbed, and diffs the rendered digest.

    python tools_verify_refactor.py

Three stages, because only the first should be byte-identical:
  A  refactor alone          -> digest must be unchanged
  B  + content dedupe        -> collapses jobs the old refnr key missed
  C  + title filter          -> deliberately drops off-target postings

Kept for the record. Only meaningful while PRE_REFACTOR is the commit before the
refactor; ongoing protection against digest changes lives in test_jobhunter.py.
"""
import difflib
import importlib.util
import json
import os
import subprocess
import sys
import warnings

warnings.filterwarnings("ignore")

PRE_REFACTOR = "ce2444a"      # last commit before the FeedSource refactor
REPO = os.path.dirname(os.path.abspath(__file__))
TMP = os.path.join(os.environ.get("TMPDIR", "/tmp"), "jobhunter-verify")

sys.path.insert(0, REPO)
os.environ.setdefault("OPENAI_API_KEY", "stub")   # never used; nothing scores

FIXTURE = json.load(open(os.path.join(REPO, "testdata", "ba_search.json"), encoding="utf-8"))

os.makedirs(TMP, exist_ok=True)
OLD = os.path.join(TMP, "old_main_%s.py" % PRE_REFACTOR)
if not os.path.exists(OLD):
    if subprocess.call(f'cd "{REPO}" && git show {PRE_REFACTOR}:main.py > "{OLD}"', shell=True):
        sys.exit(f"could not extract main.py from {PRE_REFACTOR}")

import arbeitsagentur
import screening
from config import MAX_JOBS_TO_SCORE, MIN_SCORE, TOP_N

arbeitsagentur.search = lambda was, **kw: FIXTURE.get(was, [])   # offline


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


new_main = load(os.path.join(REPO, "main.py"), "new_main")
old_main = load(OLD, "old_main")
new_main.SOURCES[0].describe = lambda p: ""      # no detail requests


def fake_score(ref):
    """Deterministic stand-in for the model, keyed so both sides agree."""
    return sum(ref.encode()) % 11, f"stubbed reason for {ref}"


def old_digest():
    found = old_main.collect_new_jobs(set())
    scored = [(*fake_score(ref), job) for ref, job in list(found.items())[:MAX_JOBS_TO_SCORE]]
    scored.sort(key=lambda x: x[0], reverse=True)
    top = [t for t in scored if t[0] >= MIN_SCORE][:TOP_N]
    return (old_main.format_message(top), old_main.format_email(top),
            [t[2]["referenznummer"] for t in top])


def new_digest():
    cands, stats = new_main.collect(set())
    scored = [(*fake_score(p.source_id), p) for p in cands[:MAX_JOBS_TO_SCORE]]
    scored.sort(key=lambda x: x[0], reverse=True)
    top = [t for t in scored if t[0] >= MIN_SCORE][:TOP_N]
    return (new_main.format_message(top), new_main.format_email(top),
            [t[2].source_id for t in top], stats)


def report(stage, old, new, stats=None):
    om, oe, orefs = old
    nm, ne, nrefs = new
    print(f"\n{'=' * 72}\n{stage}\n{'=' * 72}")
    if stats:
        print(f"  stats: {stats}")
    print(f"  jobs in digest: old={len(orefs)} new={len(nrefs)}")
    print(f"  telegram HTML byte-identical: {om == nm}")
    print(f"  email    HTML byte-identical: {oe == ne}")
    if om != nm:
        print("  --- first differing lines ---")
        for line in list(difflib.unified_diff(om.splitlines(), nm.splitlines(),
                                              "old", "new", lineterm="", n=0))[:12]:
            print("   ", line)
    if set(orefs) != set(nrefs):
        print(f"  only in old: {sorted(set(orefs) - set(nrefs))[:5]}")
        print(f"  only in new: {sorted(set(nrefs) - set(orefs))[:5]}")
    return om == nm and oe == ne and orefs == nrefs


old = old_digest()
keep_passes, keep_keys = screening.passes, screening.seen_keys

screening.passes = lambda p: (True, "")
screening.seen_keys = lambda p: {p.source_id}
*new, stats = new_digest()
a_ok = report("STAGE A - refactor only (content dedupe OFF, title filter OFF)", old, new, stats)

screening.seen_keys = keep_keys
*new, stats = new_digest()
report("STAGE B - + content dedupe (title filter still OFF)", old, new, stats)

screening.passes = keep_passes
*new, stats = new_digest()
report("STAGE C - + title filter (the shipped pipeline)", old, new, stats)

print(f"\n{'=' * 72}")
print("STAGE A:", "PASS - refactor is behaviour-preserving" if a_ok
      else "FAIL - the refactor changed the digest")
print(f"{'=' * 72}")
sys.exit(0 if a_ok else 1)
