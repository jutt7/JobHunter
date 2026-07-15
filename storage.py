"""Tracks which job reference numbers we've already sent, so you never get
the same posting twice. Stored as a plain JSON list committed back to the repo
by the GitHub Action."""
import json
import os

SEEN_FILE = "seen.json"


def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(seen), f, indent=2)
