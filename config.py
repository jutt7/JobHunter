"""Everything you'll want to tweak lives here.

Each entry in SEARCH_PROFILES is one API search. Add as many as you like:
different keywords, cities, or a remote-only search. Results are merged and
de-duplicated across all profiles before scoring.
"""

SEARCH_PROFILES = [
    # No "wo" (city) => searches all of Germany. Keyword variants that match the
    # stack, in both English and German, since postings use both.

    # Frontend
    {"was": "Frontend Developer React"},
    {"was": "React TypeScript Entwickler"},
    {"was": "Frontend Entwickler React"},
    {"was": "Frontend Engineer TypeScript"},
    {"was": "Next.js Developer"},

    # Fullstack
    {"was": "Fullstack Developer TypeScript"},
    {"was": "Fullstack Entwickler React"},
    {"was": "Full Stack Engineer JavaScript"},
    {"was": "Fullstack Entwickler Java React"},

    # Generic titles that often hide React/fullstack roles in the description
    {"was": "Software Engineer React"},
    {"was": "Softwareentwickler Web"},
]

# Wider than one day on purpose: jobs deferred by MAX_JOBS_TO_SCORE must still
# be inside the window on the next run to get picked up. seen.json filters the
# repeats, so the extra days cost nothing.
DAYS_BACK = 3            # only postings published in the last N days
MIN_SCORE = 6           # only send jobs the model scores >= this (0-10)
MAX_JOBS_TO_SCORE = 40  # cost guard: max OpenAI calls per run
TOP_N = 15              # max jobs included in the morning message
