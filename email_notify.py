"""Sends the morning digest as an HTML email via Gmail's SMTP server.

Enabled only when GMAIL_ADDRESS and GMAIL_APP_PASSWORD are set — otherwise the
channel is skipped, so email is entirely optional alongside Telegram.

Use a Google **App Password**, not your normal account password: turn on 2-Step
Verification, then create one at https://myaccount.google.com/apppasswords.
EMAIL_TO is optional and defaults to sending the digest to yourself.
"""
import os
import smtplib
from email.message import EmailMessage

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


def enabled():
    """True when Gmail credentials are configured."""
    return bool(os.environ.get("GMAIL_ADDRESS") and os.environ.get("GMAIL_APP_PASSWORD"))


def send(subject, html_body):
    address = os.environ["GMAIL_ADDRESS"]
    password = os.environ["GMAIL_APP_PASSWORD"]
    to = os.environ.get("EMAIL_TO") or address

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = address
    msg["To"] = to
    # Plain-text fallback for clients that won't render HTML.
    msg.set_content("Your daily job digest is formatted in HTML — "
                    "enable HTML viewing to see it.")
    msg.add_alternative(html_body, subtype="html")

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as smtp:
        smtp.starttls()
        smtp.login(address, password)
        smtp.send_message(msg)
