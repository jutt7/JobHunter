"""Everything you'll want to tweak lives here.

Each entry in SEARCH_PROFILES is one API search. Add as many as you like —
different keywords, cities, or a remote-only search. Results are merged and
de-duplicated across all profiles before scoring.
"""

SEARCH_PROFILES = [
    # City-based searches (umkreis = radius in km)
    {"was": "Frontend Developer React", "wo": "Berlin", "umkreis": 30},
    {"was": "Frontend Developer React", "wo": "München", "umkreis": 30},
    {"was": "Fullstack Developer TypeScript", "wo": "Frankfurt", "umkreis": 40},

    # Remote / home-office (no city, arbeitszeit "ho" = Homeoffice)
    {"was": "React TypeScript Entwickler", "arbeitszeit": "ho"},

    # Anything near you now
    {"was": "Software Engineer", "wo": "Kaiserslautern", "umkreis": 60},
]

DAYS_BACK = 1            # only postings published in the last N days
MIN_SCORE = 6           # only send jobs the model scores >= this (0-10)
MAX_JOBS_TO_SCORE = 40  # cost guard: max Claude calls per run
TOP_N = 15              # max jobs included in the morning message
