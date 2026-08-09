"""Sends the digest to a Telegram chat, HTML formatted and chunked under
Telegram's ~4096 char limit.

Active only when TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are set, otherwise the
channel is skipped."""
import html
import os

import requests


def enabled():
    """True when Telegram credentials are configured."""
    return bool(os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"))


def esc(s):
    return html.escape(str(s or ""))


def send(text):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    api = f"https://api.telegram.org/bot{token}/sendMessage"
    for chunk in _chunks(text, 3800):
        resp = requests.post(
            api,
            data={
                "chat_id": chat_id,
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
