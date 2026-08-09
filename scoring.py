"""Scores how well each job fits your CV (0-10) with a one-line reason.

Defaults to gpt-4o-mini since this is triage; set OPENAI_MODEL to gpt-4o for
sharper judgement at higher cost."""
import json
import os

from openai import OpenAI

from arbeitsagentur import description, employer, location_str, title

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

# Advert text sent to the model. 4k chars is roughly 1k tokens, enough for
# requirements and stack while keeping per-job cost predictable.
MAX_DESC_CHARS = 4000

CV_FILE = "cv.txt"
# Marker that means cv.txt is still the shipped placeholder.
TEMPLATE_MARKER = "# TEMPLATE"

PROMPT = """You are screening job postings for a candidate. Rate how well this \
job fits from 0 (no fit) to 10 (excellent fit). Weigh role & seniority, tech \
stack overlap, and location/language requirements. Be strict; a 10 is rare.

Judge the posting on what it actually asks for. If the description is missing, \
score conservatively on the title alone and say so in the reason.

CANDIDATE PROFILE:
{cv}

JOB POSTING:
Title: {title}
Employer: {employer}
Location: {location}

Description:
{description}

Respond with ONLY a JSON object and nothing else:
{{"score": <integer 0-10>, "reason": "<one short sentence>"}}"""


def load_cv():
    """Return the candidate CV.

    Prefers the CV_TEXT env var (set from a repo secret in CI) so a public repo
    never has to commit a real CV, and falls back to cv.txt for local runs.
    Raises if neither holds a real CV, since scoring against the placeholder
    produces meaningless scores with no visible symptom.
    """
    env_cv = (os.environ.get("CV_TEXT") or "").strip()
    if env_cv:
        return env_cv

    if os.path.exists(CV_FILE):
        with open(CV_FILE, encoding="utf-8") as f:
            file_cv = f.read()
        if TEMPLATE_MARKER not in file_cv and file_cv.strip():
            return file_cv

    raise RuntimeError(
        "No CV found. Set the CV_TEXT secret (see README) or replace the "
        f"placeholder contents of {CV_FILE} with your real CV. Stopping rather "
        "than scoring every job against the template."
    )


def score_job(cv, job):
    desc = description(job)  # "" when the detail fetch fails
    prompt = PROMPT.format(
        cv=cv,
        title=title(job),
        employer=employer(job),
        location=location_str(job),
        description=desc[:MAX_DESC_CHARS] if desc else "(not available)",
    )
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            max_tokens=150,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}],
        )
        data = json.loads(resp.choices[0].message.content)
        return int(data.get("score", 0)), str(data.get("reason", "")).strip()
    except Exception as e:
        return 0, f"scoring error: {e}"
