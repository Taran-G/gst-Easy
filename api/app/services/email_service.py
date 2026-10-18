import email
from email.header import decode_header
import imaplib
import logging
import os
from pathlib import Path
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from app.core.config import settings

logger = logging.getLogger(__name__)

# In-memory prototype store for email watcher and demonstration
PROTOTYPE_INBOX: List[Dict[str, Any]] = []
PROTOTYPE_SENT: List[Dict[str, Any]] = []

def decode_mime_words(s: str) -> str:
    """Decodes MIME encoded header strings."""
    if not s:
        return ""
    decoded_fragments = decode_header(s)
    result = []
    for frag, enc in decoded_fragments:
        if isinstance(frag, bytes):
            result.append(frag.decode(enc or "utf-8", errors="replace"))
        else:
            result.append(str(frag))
    return "".join(result)

class EmailService:
    def __init__(self):
        self.mode = settings.EMAIL_MODE
        self.imap_server = settings.EMAIL_IMAP_SERVER
        self.imap_port = settings.EMAIL_IMAP_PORT
        self.smtp_server = settings.EMAIL_SMTP_SERVER
        self.smtp_port = settings.EMAIL_SMTP_PORT
        self.username = settings.EMAIL_USERNAME
        self.password = settings.EMAIL_PASSWORD

    def fetch_unread_emails(self) -> List[Dict[str, Any]]:
        """
        Polls for unread emails with invoices.
        Uses real Gmail IMAP if configured, otherwise checks prototype inbox.
        """
        if self.mode == "live_gmail" and self.username and self.password:
            return self._fetch_live_gmail()
        return self._fetch_prototype_emails()

    def _fetch_prototype_emails(self) -> List[Dict[str, Any]]:
        """Returns unread emails from the prototype inbox."""
        return [eml for eml in PROTOTYPE_INBOX if not eml.get("is_read")]

    def _fetch_live_gmail(self) -> List[Dict[str, Any]]:
        """Fetches UNSEEN messages from real Gmail via IMAP SSL."""
        emails = []
        try:
            mail = imaplib.IMAP4_SSL(self.imap_server, self.imap_port)
            mail.login(self.username, self.password)
            mail.select("INBOX")
            
            status, messages = mail.search(None, "UNSEEN")
            if status != "OK" or not messages[0]:
                mail.close()
                mail.logout()
                return []

            os.makedirs(settings.DATA_DIR, exist_ok=True)
            msg_ids = messages[0].split()

            for msg_id in msg_ids:
                res, data = mail.fetch(msg_id, "(RFC822)")
                if res != "OK":
                    continue

                raw_email = data[0][1]
                msg = email.message_from_bytes(raw_email)

                subject = decode_mime_words(msg.get("Subject", ""))
                from_addr = decode_mime_words(msg.get("From", ""))
                to_addr = decode_mime_words(msg.get("To", ""))

                attachments = []
                body_text = ""

                if msg.is_multipart():
                    for part in msg.walk():
                        content_type = part.get_content_type()
                        content_disposition = str(part.get("Content-Disposition") or "")
                        filename = part.get_filename()

                        if filename:
                            filename = decode_mime_words(filename)
                            ext = Path(filename).suffix.lower()
                            if ext in [".pdf", ".png", ".jpg", ".jpeg"]:
                                safe_name = f"gmail_{uuid.uuid4().hex[:8]}_{filename}"
                                save_path = Path(settings.DATA_DIR) / safe_name
                                payload_bytes = part.get_payload(decode=True)
                                if payload_bytes:
                                    with open(save_path, "wb") as f:
                                        f.write(payload_bytes)
                                    attachments.append({
                                        "filename": filename,
                                        "path": str(save_path),
                                        "content_type": content_type
                                    })
                        elif content_type == "text/plain" and "attachment" not in content_disposition:
                            payload_bytes = part.get_payload(decode=True)
                            if payload_bytes:
                                body_text = payload_bytes.decode("utf-8", errors="replace")
                else:
                    payload_bytes = msg.get_payload(decode=True)
                    if payload_bytes:
                        body_text = payload_bytes.decode("utf-8", errors="replace")

                emails.append({
                    "id": f"gmail_{msg_id.decode()}",
                    "from_addr": from_addr,
                    "to_addr": to_addr,
                    "subject": subject,
                    "body": body_text,
                    "attachments": attachments,
                    "received_at": datetime.now(timezone.utc).isoformat(),
                    "is_read": False,
                    "is_live_gmail": True,
                    "raw_msg_id": msg_id
                })

            mail.close()
            mail.logout()
        except Exception as e:
            logger.error("Live Gmail IMAP fetch failed: %s", e)
        return emails

    def mark_email_as_read(self, email_id: str, invoice_id: Optional[str] = None):
        """Marks an email as read and records the created invoice ID."""
        for eml in PROTOTYPE_INBOX:
            if eml["id"] == email_id:
                eml["is_read"] = True
                eml["processed_invoice_id"] = invoice_id
                return

    def send_email_reply(
        self,
        to_addr: str,
        subject: str,
        body_text: str,
        in_reply_to_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Sends an automated reply email back to the supplier/client.
        Dispatches via real SMTP if live_gmail, otherwise records in prototype sent box.
        """
        reply_id = f"eml_sent_{uuid.uuid4().hex[:10]}"
        now_iso = datetime.now(timezone.utc).isoformat()

        reply_record = {
            "id": reply_id,
            "from_addr": self.username or "agent@ledgergraph.ai",
            "to_addr": to_addr,
            "subject": f"Re: {subject}" if not subject.startswith("Re:") else subject,
            "body": body_text,
            "sent_at": now_iso,
            "in_reply_to_id": in_reply_to_id,
            "status": "SENT"
        }

        # If configured with live credentials, dispatch via SMTP
        if self.mode == "live_gmail" and self.username and self.password:
            try:
                msg = MIMEMultipart()
                msg["From"] = self.username
                msg["To"] = to_addr
                msg["Subject"] = reply_record["subject"]
                msg.attach(MIMEText(body_text, "plain"))

                with smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=10) as server:
                    server.starttls()
                    server.login(self.username, self.password)
                    server.send_message(msg)
                reply_record["status"] = "DELIVERED_SMTP"
            except Exception as e:
                logger.error("Failed to send live Gmail SMTP reply: %s", e)
                reply_record["status"] = f"SMTP_ERROR: {str(e)}"

        PROTOTYPE_SENT.append(reply_record)
        return reply_record

    def simulate_incoming_email(
        self,
        from_addr: str,
        subject: str,
        body_text: str,
        fixture_name: Optional[str] = None,
        custom_file_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Simulates an incoming email with an invoice attachment landing in the watched inbox.
        The autonomous background agent will automatically pick this up on its cycle!
        """
        attachments = []
        target_path = None

        if custom_file_path and os.path.exists(custom_file_path):
            target_path = custom_file_path
            filename = Path(custom_file_path).name
        elif fixture_name:
            p = Path(settings.FIXTURES_DIR) / "bills" / f"{fixture_name}.pdf"
            if not p.exists():
                p = Path(settings.FIXTURES_DIR) / "bills" / "golden" / f"{fixture_name}.json"
            if p.exists():
                target_path = str(p)
                filename = p.name
        else:
            # Default sample
            p = Path(settings.FIXTURES_DIR) / "bills" / "clean_intrastate.pdf"
            target_path = str(p)
            filename = "clean_intrastate.pdf"

        if target_path:
            attachments.append({
                "filename": filename,
                "path": target_path,
                "content_type": "application/pdf"
            })

        eml_id = f"eml_{uuid.uuid4().hex[:10]}"
        new_email = {
            "id": eml_id,
            "from_addr": from_addr,
            "to_addr": "invoices@apexautoparts.com",
            "subject": subject,
            "body": body_text,
            "attachments": attachments,
            "received_at": datetime.now(timezone.utc).isoformat(),
            "is_read": False,
            "processed_invoice_id": None
        }

        PROTOTYPE_INBOX.append(new_email)
        logger.info("[Email Service] Simulated new incoming email %s from %s", eml_id, from_addr)
        return new_email

    def get_all_emails(self) -> Dict[str, Any]:
        """Returns inbox and sent message lists."""
        return {
            "inbox": list(reversed(PROTOTYPE_INBOX)),
            "sent": list(reversed(PROTOTYPE_SENT)),
            "unread_count": len([e for e in PROTOTYPE_INBOX if not e.get("is_read")])
        }

email_service = EmailService()
