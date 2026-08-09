#!/usr/bin/env python3
"""Interactive setup wizard for the Daily Job Agent.

What it automates:
  - validates your OpenAI key and Telegram bot token
  - AUTO-DETECTS your Telegram chat ID (no more copying getUpdates JSON)
  - optionally sets up email via Gmail (validates the app password over SMTP)
  - sends a test message/email so you know delivery works before the first run
  - writes a local .env for running on your machine
  - optionally pushes all secrets to your GitHub repo via the `gh` CLI

What it can't do (external, human-only; do these first):
  - create the Telegram bot   -> message @BotFather, send /newbot, copy the token
  - issue an OpenAI API key    -> https://platform.openai.com/api-keys
  - make a Gmail App Password  -> https://myaccount.google.com/apppasswords (2FA on)

Run it with:  python setup.py
"""
import os
import shutil
import smtplib
import subprocess
import time
from email.message import EmailMessage

import requests


def ask(prompt, current=None):
    hint = f" [keep {_mask(current)}]" if current else ""
    val = input(f"{prompt}{hint}: ").strip()
    return val or (current or "")


def _mask(v):
    return (v[:6] + "…") if v and len(v) > 8 else v


def validate_openai(key):
    try:
        from openai import OpenAI
        OpenAI(api_key=key).models.list()
        print("  ✓ OpenAI key works.")
        return True
    except Exception as e:
        print(f"  ✗ OpenAI key check failed: {e}")
        return False


def validate_bot(token):
    try:
        r = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=15)
        if r.ok and r.json().get("ok"):
            print(f"  ✓ Bot @{r.json()['result']['username']} reachable.")
            return True
    except Exception as e:
        print(f"  ✗ {e}")
        return False
    print("  ✗ Telegram rejected that bot token.")
    return False


def resolve_chat_id(token):
    print("\n→ Open Telegram, find your bot, and send it any message now.")
    input("  Press Enter once you've sent it… ")
    for _ in range(10):
        r = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=15)
        results = r.json().get("result", [])
        if results:
            chat_id = str(results[-1]["message"]["chat"]["id"])
            print(f"  ✓ Detected chat ID: {chat_id}")
            return chat_id
        print("  no message seen yet. Send your bot a message; retrying in 3s.")
        time.sleep(3)
    print("  ✗ Couldn't detect a message. Make sure you messaged the bot, then rerun.")
    return ""


def send_test(token, chat_id):
    r = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data={"chat_id": chat_id, "text": "Daily Job Agent: setup works!"},
        timeout=15,
    )
    print("  ✓ Test message sent. Check Telegram." if r.ok
          else f"  ✗ Test send failed: {r.text}")


def validate_gmail(address, password):
    """Try an SMTP login so a bad app password is caught before the first run."""
    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as smtp:
            smtp.starttls()
            smtp.login(address, password)
        print("  ✓ Gmail login works.")
        return True
    except Exception as e:
        print(f"  ✗ Gmail login failed: {e}")
        print("    Use a 16-char App Password (not your normal password), with "
              "2-Step Verification on: https://myaccount.google.com/apppasswords")
        return False


def send_test_email(address, password, to):
    msg = EmailMessage()
    msg["Subject"] = "Daily Job Agent: email setup works!"
    msg["From"] = address
    msg["To"] = to
    msg.set_content("Your Daily Job Agent email channel is configured correctly.")
    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as smtp:
            smtp.starttls()
            smtp.login(address, password)
            smtp.send_message(msg)
        print(f"  ✓ Test email sent to {to}. Check your inbox.")
    except Exception as e:
        print(f"  ✗ Test email failed: {e}")


def load_existing_env():
    env = {}
    if os.path.exists(".env"):
        for line in open(".env"):
            if "=" in line and not line.startswith("#"):
                k, _, v = line.strip().partition("=")
                env[k] = v
    return env


def write_env(values):
    with open(".env", "w") as f:
        for k, v in values.items():
            if v:
                f.write(f"{k}={v}\n")
    print("  ✓ Wrote .env (git-ignored, stays on your machine).")


def push_gh_secrets(values):
    if not shutil.which("gh"):
        print("\n`gh` CLI not installed, skipping GitHub secrets. Add them "
              "manually under Settings → Secrets and variables → Actions, or "
              "install gh (https://cli.github.com) and rerun.")
        return
    if input("\nPush these to your GitHub repo secrets via gh? [y/N]: ").strip().lower() != "y":
        return
    for k, v in values.items():
        if not v:
            continue
        try:
            subprocess.run(["gh", "secret", "set", k, "--body", v],
                           check=True, capture_output=True, text=True)
            print(f"  ✓ set {k}")
        except subprocess.CalledProcessError as e:
            print(f"  ✗ {k}: {e.stderr.strip() or e}")


def main():
    print("=== Daily Job Agent setup wizard ===\n")
    env = load_existing_env()

    print("1) OpenAI API key  (https://platform.openai.com/api-keys)")
    while not validate_openai(key := ask("   OPENAI_API_KEY", env.get("OPENAI_API_KEY"))):
        pass

    print("\n2) Telegram bot token  (create via @BotFather → /newbot)")
    while not validate_bot(token := ask("   TELEGRAM_BOT_TOKEN", env.get("TELEGRAM_BOT_TOKEN"))):
        pass

    chat_id = env.get("TELEGRAM_CHAT_ID") or resolve_chat_id(token)
    if chat_id:
        send_test(token, chat_id)

    print("\n3) Email digest via Gmail (optional, press Enter to skip)")
    gmail_addr = ask("   GMAIL_ADDRESS", env.get("GMAIL_ADDRESS"))
    gmail_pw = email_to = ""
    if gmail_addr:
        while not validate_gmail(gmail_addr,
                                 gmail_pw := ask("   GMAIL_APP_PASSWORD",
                                                 env.get("GMAIL_APP_PASSWORD"))):
            pass
        email_to = ask("   EMAIL_TO (recipient)", env.get("EMAIL_TO") or gmail_addr)
        send_test_email(gmail_addr, gmail_pw, email_to)

    values = {
        "OPENAI_API_KEY": key,
        "TELEGRAM_BOT_TOKEN": token,
        "TELEGRAM_CHAT_ID": chat_id,
        "GMAIL_ADDRESS": gmail_addr,
        "GMAIL_APP_PASSWORD": gmail_pw,
        "EMAIL_TO": email_to,
    }
    print()
    write_env(values)
    push_gh_secrets(values)

    print("\nAll set. Test a run locally with:  python main.py")


if __name__ == "__main__":
    main()
