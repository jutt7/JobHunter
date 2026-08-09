"""Score the same jobs with two models and compare.

Run: python ab_models.py
     python ab_models.py --n 20 --a gpt-4o-mini --b gpt-5.6-luna

Uses the real pipeline (same search, same advert text, same prompt), so the only
variable is the model. Prints a side-by-side table, the disagreements that would
actually change your digest, and the measured cost of each run.
"""
import argparse
import json
import os
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from openai import OpenAI

import scoring
from arbeitsagentur import description, employer, location_str, search, title
from config import MIN_SCORE, SEARCH_PROFILES

# USD per 1M tokens, from the OpenAI pricing page (August 2026).
PRICES = {
    "gpt-4o-mini":   (0.15, 0.60),
    "gpt-5.6-luna":  (0.20, 1.20),
    "gpt-5.6-terra": (2.00, 12.00),
    "gpt-5.4-nano":  (0.20, 1.25),
    "gpt-5.4-mini":  (0.75, 4.50),
    "gpt-5.4":       (2.50, 15.00),
}

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])


def score_with(model, cv, job, desc):
    """One scoring call. Returns (score, reason, in_tokens, out_tokens)."""
    prompt = scoring.PROMPT.format(
        cv=cv,
        title=title(job),
        employer=employer(job),
        location=location_str(job),
        description=desc[:scoring.MAX_DESC_CHARS] if desc else "(not available)",
    )
    kwargs = {
        "model": model,
        "response_format": {"type": "json_object"},
        "messages": [{"role": "user", "content": prompt}],
    }
    # Reasoning models (gpt-5.x) reject max_tokens and bill hidden reasoning as
    # output, so they need the newer parameter and a much larger ceiling.
    if model.startswith("gpt-4"):
        kwargs["max_tokens"] = 150
    else:
        kwargs["max_completion_tokens"] = 2000

    try:
        resp = client.chat.completions.create(**kwargs)
    except Exception as e:
        return None, "API error: %s" % str(e)[:80], 0, 0

    usage = resp.usage
    tin = getattr(usage, "prompt_tokens", 0) or 0
    tout = getattr(usage, "completion_tokens", 0) or 0
    raw = resp.choices[0].message.content
    if not raw:
        return None, "empty response (reasoning may have used the token budget)", tin, tout
    try:
        data = json.loads(raw)
        return int(data["score"]), str(data.get("reason", "")).strip(), tin, tout
    except Exception as e:
        return None, "unparseable: %s / %r" % (e, raw[:60]), tin, tout


def cost(model, tin, tout):
    if model not in PRICES:
        return None
    pin, pout = PRICES[model]
    return tin / 1e6 * pin + tout / 1e6 * pout


def spearman(xs, ys):
    """Rank correlation, no scipy. Returns None if fewer than 3 usable pairs."""
    pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    if len(pairs) < 3:
        return None

    def ranks(vals):
        order = sorted(range(len(vals)), key=lambda i: vals[i])
        r = [0.0] * len(vals)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and vals[order[j + 1]] == vals[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r

    rx, ry = ranks([p[0] for p in pairs]), ranks([p[1] for p in pairs])
    n = len(pairs)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = sum((a - mx) ** 2 for a in rx) ** 0.5
    dy = sum((b - my) ** 2 for b in ry) ** 0.5
    return num / (dx * dy) if dx and dy else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20, help="how many jobs to compare")
    ap.add_argument("--a", default="gpt-4o-mini", help="baseline model")
    ap.add_argument("--b", default="gpt-5.6-luna", help="challenger model")
    ap.add_argument("--days", type=int, default=7, help="posting age window")
    args = ap.parse_args()

    cv = scoring.load_cv()

    print("collecting jobs...")
    jobs, seen_refs = [], set()
    for prof in SEARCH_PROFILES:
        if len(jobs) >= args.n:
            break
        try:
            found = search(was=prof["was"], veroeffentlichtseit=args.days, size=20)
        except Exception as e:
            print("  search failed for %s: %s" % (prof, e))
            continue
        for j in found:
            r = j.get("referenznummer")
            if r and r not in seen_refs:
                seen_refs.add(r)
                jobs.append(j)
            if len(jobs) >= args.n:
                break

    if not jobs:
        sys.exit("No jobs found. Try --days 14.")
    print("comparing %d job(s): %s vs %s\n" % (len(jobs), args.a, args.b))

    rows = []
    tok = {args.a: [0, 0], args.b: [0, 0]}
    for i, job in enumerate(jobs, 1):
        desc = description(job)
        sa, ra, ia, oa = score_with(args.a, cv, job, desc)
        sb, rb, ib, ob = score_with(args.b, cv, job, desc)
        tok[args.a][0] += ia; tok[args.a][1] += oa
        tok[args.b][0] += ib; tok[args.b][1] += ob
        rows.append((title(job), employer(job), len(desc), sa, ra, sb, rb))
        print("  %2d/%d  %-42s  %s: %-4s  %s: %-4s" % (
            i, len(jobs), title(job)[:42], args.a, sa, args.b, sb))

    print("\n" + "=" * 100)
    print("SIDE BY SIDE  (MIN_SCORE = %s)" % MIN_SCORE)
    print("=" * 100)
    print("%-40s %6s %6s %6s %7s  %s" % ("JOB", "DESC", args.a[:6], args.b[:6], "DELTA", "VERDICT"))
    print("-" * 100)
    flips = []
    for t, emp, dlen, sa, ra, sb, rb in rows:
        if sa is None or sb is None:
            verdict = "error"
            delta = ""
        else:
            delta = "%+d" % (sb - sa)
            pa, pb = sa >= MIN_SCORE, sb >= MIN_SCORE
            if pa != pb:
                verdict = "FLIP: %s sends, %s drops" % (
                    (args.a if pa else args.b), (args.b if pa else args.a))
                flips.append((t, sa, ra, sb, rb))
            else:
                verdict = "both send" if pa else "both drop"
        print("%-40s %6d %6s %6s %7s  %s" % (
            t[:40], dlen, sa, sb, delta, verdict))

    scores_a = [r[3] for r in rows]
    scores_b = [r[5] for r in rows]
    ok = [(a, b) for a, b in zip(scores_a, scores_b) if a is not None and b is not None]

    print("\n" + "=" * 100)
    print("SUMMARY")
    print("=" * 100)
    if ok:
        ma = sum(a for a, _ in ok) / len(ok)
        mb = sum(b for _, b in ok) / len(ok)
        mad = sum(abs(a - b) for a, b in ok) / len(ok)
        print("  scored ok            : %d/%d" % (len(ok), len(rows)))
        print("  mean score           : %s %.2f   |   %s %.2f" % (args.a, ma, args.b, mb))
        print("  mean abs difference  : %.2f points" % mad)
        rho = spearman(scores_a, scores_b)
        print("  rank correlation     : %s" % ("%.3f" % rho if rho is not None else "n/a"))
        print("  threshold flips      : %d of %d  <-- the number that matters" % (len(flips), len(ok)))
    else:
        print("  no jobs scored successfully by both models")

    for m in (args.a, args.b):
        tin, tout = tok[m]
        c = cost(m, tin, tout)
        per_day = (c / max(len(rows), 1)) * 40 if c is not None else None
        print("  %-14s tokens in/out %6d/%6d   run $%s   projected $%s/month at 40 jobs/day" % (
            m, tin, tout,
            ("%.4f" % c) if c is not None else "?",
            ("%.2f" % (per_day * 30)) if per_day is not None else "?"))

    if flips:
        print("\n" + "=" * 100)
        print("DISAGREEMENTS WORTH READING (these change what lands in your digest)")
        print("=" * 100)
        for t, sa, ra, sb, rb in flips:
            print("\n%s" % t)
            print("  %-13s %s/10  %s" % (args.a, sa, ra))
            print("  %-13s %s/10  %s" % (args.b, sb, rb))

    with open("ab_results.json", "w", encoding="utf-8") as f:
        json.dump([{
            "title": t, "employer": emp, "desc_chars": dlen,
            args.a: {"score": sa, "reason": ra},
            args.b: {"score": sb, "reason": rb},
        } for t, emp, dlen, sa, ra, sb, rb in rows], f, indent=2, ensure_ascii=False)
    print("\nfull output written to ab_results.json")


if __name__ == "__main__":
    main()
