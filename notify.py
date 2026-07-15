"""Sends the morning digest to your Telegram chat. Uses HTML formatting and
chunks long messages under Telegram's ~4096 char limit."""
import html
import os

import requests

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
API = f"https://api.telegram.org/bot{TOKEN}/sendMessage"


def esc(s):
    return html.escape(str(s or ""))


def send(text):
    for chunk in _chunks(text, 3800):
        resp = requests.post(
            API,
            data={
                "chat_id": CHAT_ID,
                "text": chunk,
                "parse_mode": "HTML",
                "disable_web_page_preview": "true",
            },
            timeout=30,
        )
        resp.raise_for_status()


def _chunks(text, limit):
    """Split on line boundaries so we never cut a link in half."""
    buf, size = [], 0
    for line in text.split("\n"):
        if size + len(line) + 1 > limit and buf:
            yield "\n".join(buf)
            buf, size = [], 0
        buf.append(line)
        size += len(line) + 1
    if buf:
        yield "\n".join(buf)
