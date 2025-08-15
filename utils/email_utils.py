import smtplib
from email.mime.text import MIMEText
from config import Config
from datetime import datetime
from typing import Optional, Dict, Any
from utils.db import db

_email_collection = db.email_notifications

def send_email(subject: str, recipient: str, body: str, meta: Optional[Dict[str, Any]] = None):
    # Attempt SMTP but do not break request if email fails; log to DB either way
    smtp_ok = True
    try:
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = Config.SMTP_USER
        msg['To'] = recipient

        server = smtplib.SMTP(Config.SMTP_SERVER, Config.SMTP_PORT, timeout=10)
        server.ehlo()
        server.starttls()
        server.login(Config.SMTP_USER, Config.SMTP_PASSWORD)
        server.sendmail(Config.SMTP_USER, recipient, msg.as_string())
        server.quit()
    except Exception:
        smtp_ok = False  # do not raise

    doc = {
        "from": Config.SMTP_USER,
        "recipient": recipient,
        "subject": subject,
        "message": body,
        "read": False,
        "timestamp": datetime.utcnow().isoformat(),
        "smtp_sent": smtp_ok,
    }
    if meta and isinstance(meta, dict):
        doc.update({
            "status": meta.get("status"),
            "task_id": meta.get("task_id"),
            "title": meta.get("title"),
            "employee_id": meta.get("employee_id"),
            "username": meta.get("username"),
        })
        doc["meta"] = meta

    try:
        _email_collection.insert_one(doc)
    except Exception:
        # last resort: do nothing; avoid breaking API on logging failure
        pass
