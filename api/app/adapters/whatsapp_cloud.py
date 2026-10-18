import hmac
import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
import httpx

from app.adapters.whatsapp_port import WhatsAppPort
from app.adapters.whatsapp_mock import MockWhatsAppAdapter
from app.core.config import settings

logger = logging.getLogger(__name__)

class MetaWhatsAppCloudAdapter(WhatsAppPort):
    def __init__(self):
        self.phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID
        self.access_token = settings.WHATSAPP_ACCESS_TOKEN
        self.verify_token = settings.WHATSAPP_VERIFY_TOKEN
        self.app_secret = settings.WHATSAPP_APP_SECRET
        self.mock_fallback = MockWhatsAppAdapter()

    def verify_webhook_token(self, mode: str, token: str) -> bool:
        """Verifies Meta webhook setup challenge."""
        return mode == "subscribe" and token == self.verify_token

    def verify_signature(self, raw_body: bytes, signature_header: Optional[str]) -> bool:
        """Validates X-Hub-Signature-256 header using app secret."""
        if not self.app_secret:
            return True # Skip verification if not configured in dev
        if not signature_header or not signature_header.startswith("sha256="):
            return False
        
        expected_sig = signature_header.split("=")[1]
        computed_sig = hmac.new(
            self.app_secret.encode("utf-8"),
            raw_body,
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected_sig, computed_sig)

    def parse_webhook(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parses incoming Meta WhatsApp Cloud API webhook JSON payload.
        Handles both real Meta JSON schema and simulated test schema.
        """
        # If simulated simple payload
        if "phone" in payload or "media_path" in payload:
            return self.mock_fallback.parse_webhook(payload)

        try:
            entries = payload.get("entry", [])
            if not entries:
                return {}
            
            changes = entries[0].get("changes", [])
            if not changes:
                return {}
            
            value = changes[0].get("value", {})
            messages = value.get("messages", [])
            if not messages:
                return {}
            
            msg = messages[0]
            from_wa = msg.get("from", "")
            # Ensure Indian +91 format
            clean_phone = f"+{from_wa}" if not from_wa.startswith("+") else from_wa
            msg_type = msg.get("type", "text")
            msg_id = msg.get("id", "")
            timestamp = msg.get("timestamp", "")
            
            media_id = None
            media_filename = None
            caption = ""
            
            if msg_type == "document":
                doc = msg.get("document", {})
                media_id = doc.get("id")
                media_filename = doc.get("filename", f"wa_doc_{media_id}.pdf")
                caption = doc.get("caption", "")
            elif msg_type == "image":
                img = msg.get("image", {})
                media_id = img.get("id")
                media_filename = f"wa_img_{media_id}.jpg"
                caption = img.get("caption", "")
            elif msg_type == "text":
                caption = msg.get("text", {}).get("body", "")

            # If media attachment exists, download to data dir
            downloaded_path = None
            if media_id:
                downloaded_path = self.download_media(media_id, media_filename)

            return {
                "id": msg_id,
                "sender_phone": clean_phone,
                "media_path": downloaded_path,
                "text": caption,
                "type": msg_type,
                "timestamp": timestamp,
                "media_id": media_id
            }
        except Exception as e:
            logger.error("Error parsing WhatsApp webhook: %s", e)
            return {}

    def download_media(self, media_id: str, filename: str) -> Optional[str]:
        """Downloads media file from Meta Graph API."""
        if not self.access_token:
            logger.warning("No WHATSAPP_ACCESS_TOKEN configured; cannot download media %s", media_id)
            return None

        try:
            headers = {"Authorization": f"Bearer {self.access_token}"}
            with httpx.Client(timeout=30.0) as client:
                # Step 1: Get media URL
                info_res = client.get(f"https://graph.facebook.com/v19.0/{media_id}", headers=headers)
                info_res.raise_for_status()
                media_url = info_res.json().get("url")
                
                if not media_url:
                    return None
                
                # Step 2: Download file bytes
                dl_res = client.get(media_url, headers=headers)
                dl_res.raise_for_status()
                
                save_dir = Path(settings.DATA_DIR)
                save_dir.mkdir(parents=True, exist_ok=True)
                save_path = save_dir / f"{media_id}_{filename}"
                
                with open(save_path, "wb") as f:
                    f.write(dl_res.content)
                    
                return str(save_path)
        except Exception as e:
            logger.error("Failed to download WhatsApp media %s: %s", media_id, e)
            return None

    def send_text(self, to_phone: str, text: str) -> Dict[str, Any]:
        """Sends plain text message via Meta Cloud API or mock fallback."""
        if not self.access_token or not self.phone_number_id:
            return self.mock_fallback.send_text(to_phone, text)

        try:
            clean_phone = to_phone.replace("+", "").replace(" ", "").replace("-", "")
            url = f"https://graph.facebook.com/v19.0/{self.phone_number_id}/messages"
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"
            }
            body = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": clean_phone,
                "type": "text",
                "text": {"preview_url": False, "body": text}
            }
            with httpx.Client(timeout=10.0) as client:
                res = client.post(url, json=body, headers=headers)
                res.raise_for_status()
                return {"status": "sent", "response": res.json(), "cost_inr": 0.0}
        except Exception as e:
            logger.error("Meta WhatsApp send_text failed: %s. Falling back to mock.", e)
            return self.mock_fallback.send_text(to_phone, text)

    def send_template(self, to_phone: str, template_name: str, params: Dict[str, Any], lang: str = "en") -> Dict[str, Any]:
        """Sends pre-approved utility template via Meta Cloud API or mock fallback."""
        if not self.access_token or not self.phone_number_id:
            return self.mock_fallback.send_template(to_phone, template_name, params, lang)

        try:
            clean_phone = to_phone.replace("+", "").replace(" ", "").replace("-", "")
            url = f"https://graph.facebook.com/v19.0/{self.phone_number_id}/messages"
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"
            }
            
            parameters = []
            for k, v in params.items():
                parameters.append({"type": "text", "text": str(v)})
                
            body = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": clean_phone,
                "type": "template",
                "template": {
                    "name": template_name,
                    "language": {"code": lang},
                    "components": [
                        {
                            "type": "body",
                            "parameters": parameters
                        }
                    ]
                }
            }
            with httpx.Client(timeout=10.0) as client:
                res = client.post(url, json=body, headers=headers)
                res.raise_for_status()
                return {"status": "sent", "response": res.json(), "cost_inr": 0.35}
        except Exception as e:
            logger.error("Meta WhatsApp send_template failed: %s. Falling back to mock.", e)
            return self.mock_fallback.send_template(to_phone, template_name, params, lang)
