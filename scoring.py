"""Uses the OpenAI API to score how well each job fits your CV (0-10) plus a
one-line reason. Defaults to gpt-4o-mini (cheap + fast) since this is triage;
bump OPENAI_MODEL to gpt-4o if you want sharper judgement."""
import json
import os

from openai import OpenAI

from arbeitsagentur import location_str

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

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
