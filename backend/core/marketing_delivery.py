"""Explicit marketing transports. Acceptance is never reported as delivery."""
import os
import re
import smtplib
import ssl
from email.message import EmailMessage

import httpx


def configured(channel):
    if channel == "email":
        return bool(re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", os.getenv("NXTDEAL_PRIVATEEMAIL_USERNAME", ""))) and bool(os.getenv("NXTDEAL_PRIVATEEMAIL_PASSWORD"))
    if channel == "sms":
        return all(re.fullmatch(prefix + r"[0-9a-fA-F]{32}", os.getenv(key, "")) for key, prefix in (("TWILIO_ACCOUNT_SID", "AC"), ("TWILIO_API_KEY_SID", "SK"), ("TWILIO_MESSAGING_SERVICE_SID", "MG"))) and bool(os.getenv("TWILIO_API_KEY_SECRET"))
    return False


def send(action):
    channel = action["channel"]
    if not configured(channel):
        raise ValueError("Transport is not configured")
    if channel == "email":
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", action["to"] or ""):
            raise ValueError("Invalid email recipient")
        message = EmailMessage()
        message["From"] = os.environ["NXTDEAL_PRIVATEEMAIL_USERNAME"]
        message["To"] = action["to"]
        message["Subject"] = action["subject"]
        reference = "<" + action["id"] + "@" + os.environ["NXTDEAL_PRIVATEEMAIL_USERNAME"].split("@")[1] + ">"
        message["Message-ID"] = reference
        if action.get("unsubscribe_url"):
            message["List-Unsubscribe"] = "<" + action["unsubscribe_url"] + ">"
            message["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
        message.set_content(action["body"])
        if action.get("html_body"):
            message.add_alternative(action["html_body"], subtype="html")
        with smtplib.SMTP_SSL("mail.privateemail.com", 465, timeout=15, context=ssl.create_default_context()) as smtp:
            smtp.login(os.environ["NXTDEAL_PRIVATEEMAIL_USERNAME"], os.environ["NXTDEAL_PRIVATEEMAIL_PASSWORD"])
            if smtp.send_message(message):
                raise RuntimeError("Recipient was refused")
        return {"provider": "privateemail", "provider_reference": reference}
    if not re.fullmatch(r"\+[1-9][0-9]{7,14}", action["to"] or ""):
        raise ValueError("SMS requires an international phone number")
    account = os.environ["TWILIO_ACCOUNT_SID"]
    with httpx.Client(timeout=15, follow_redirects=False) as client:
        response = client.post(f"https://api.twilio.com/2010-04-01/Accounts/{account}/Messages.json", auth=(os.environ["TWILIO_API_KEY_SID"], os.environ["TWILIO_API_KEY_SECRET"]), data={"To": action["to"], "MessagingServiceSid": os.environ["TWILIO_MESSAGING_SERVICE_SID"], "Body": action["body"]})
        response.raise_for_status()
        data = response.json()
    if data.get("account_sid") != account or data.get("to") != action["to"] or not re.fullmatch(r"SM[0-9a-fA-F]{32}", data.get("sid", "")):
        raise RuntimeError("Provider acknowledgement did not match the request")
    return {"provider": "twilio", "provider_reference": data["sid"]}
