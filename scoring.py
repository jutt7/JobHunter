"""Uses the Claude API to score how well each job fits your CV (0-10) plus a
one-line reason. Defaults to Haiku (cheap + fast) since this is triage; bump
CLAUDE_MODEL to a Sonnet model if you want sharper judgement."""
import json
import os

from anthropic import Anthropic
from arbeitsagentur import location_str

client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5-20251001")

PROMPT = """You are screening job postings for a candidate. Rate how well this \
job fits from 0 (no fit) to 10 (excellent fit). Weigh role & seniority, tech \
stack overlap, and location/language requirements. Be strict — a 10 is rare.

CANDIDATE PROFILE:
{cv}

JOB POSTING:
Title: {title}
Employer: {employer}
Location: {location}

Respond with ONLY a JSON object and nothing else:
{{"score": <integer 0-10>, "reason": "<one short sentence>"}}"""


def load_cv():
    with open("cv.txt", encoding="utf-8") as f:
        return f.read()


def score_job(cv, job):
    prompt = PROMPT.format(
        cv=cv,
        title=job.get("titel", ""),
        employer=job.get("arbeitgeber", ""),
        location=location_str(job),
    )
    try:
        msg = client.messages.create(
            model=MODEL,
            max_tokens=150,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in msg.content if b.type == "text").strip()
        # strip accidental code fences
        text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        data = json.loads(text)
        return int(data.get("score", 0)), str(data.get("reason", "")).strip()
    except Exception as e:
        return 0, f"scoring error: {e}"
