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


# --- cheap filter (runs before the LLM, costs nothing) -----------------------
#
# A title must match TITLE_INCLUDE and must not match TITLE_EXCLUDE to reach the
# model. Measured on 101 real postings pulled from the search profiles above,
# this keeps about two thirds and drops a third unscored.
#
# Both are compiled with re.X (whitespace and # comments ignored) and re.I, and
# are matched after the (m/w/d)-style markers have been stripped off the title.

TITLE_INCLUDE = r"""
      front.?end | full.?stack | react | typescript | javascript
    # next.js is one of the SEARCH_PROFILES above; without it here we'd pay to
    # search for Next.js roles and then throw the results away unscored.
    | next .? js
    # "develop" as a stem so Developer / Development / Developer:in all match.
    # Without it "Software Developer" and "Web Developer" — two of the most
    # common English titles on German boards — fall through the gate.
    | web      .? (entwickl | develop | engineer | applikat | applicat)
    | software .? (entwickl | develop | engineer)
"""

# Note on seniority: a *parenthesised* "(Senior)" is stripped before this runs.
# German adverts use "(Senior) Full-Stack Engineer" to mean the role is open at
# mid level too, so excluding those would throw away on-target postings; a bare
# "Senior Full-Stack Engineer" still gets dropped.
TITLE_EXCLUDE = r"""
      senior | \b lead \b | principal | head .? of | architekt
    | praktikum | praktikant | werkstudent | ausbildung | azubi
    # \b matters: bare "dual" also matches Indivi(dual)software-Entwickler,
    # which is a real German job title and a role we actually want.
    | \b dual
"""

# Pure-backend roles are deliberately NOT in TITLE_INCLUDE: the target profile is
# frontend/full-stack, so "Java-Entwickler" and "Java Backend Developer" are now
# dropped unscored (4 of 108 in a sample run). If you want the model to judge
# those too, add this alternation to TITLE_INCLUDE:
#     | java | spring.?boot | backend

# Empty = anywhere in Germany, which is the default: relocation is open, so a
# postal-code gate would only throw away good postings. Fill it with PLZ
# prefixes to narrow, e.g. ["67", "68", "69"] for the Rhine-Neckar area.
PLZ_PREFIX_ALLOWLIST: list[str] = []
