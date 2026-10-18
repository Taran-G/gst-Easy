import logging
from typing import Any, Dict, List
from app.adapters.whatsapp_port import WhatsAppPort

logger = logging.getLogger(__name__)

class MockWhatsAppAdapter(WhatsAppPort):
    def __init__(self):
        self.sent_messages: List[Dict[str, Any]] = []

    def parse_webhook(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        # Support simulated webhook payload: {"phone": "...", "media_path": "...", "text": "..."}
        phone = payload.get("phone", "+919876543210")
        media_path = payload.get("media_path")
        text = payload.get("text", "")
        msg_id = payload.get("id", f"sim_wa_{len(self.sent_messages)+1}")
        return {
            "id": msg_id,
            "sender_phone": phone,
            "media_path": media_path,
            "text": text,
            "timestamp": payload.get("timestamp")
        }

    def send_text(self, to_phone: str, text: str) -> Dict[str, Any]:
        msg_record = {
            "type": "text",
            "to": to_phone,
            "content": text,
            "status": "delivered_mock",
            "cost_inr": 0.0
        }
        self.sent_messages.append(msg_record)
        logger.info("[Mock WhatsApp] Sent text to %s: %s", to_phone, text)
        return msg_record

    def send_template(self, to_phone: str, template_name: str, params: Dict[str, Any], lang: str = "en") -> Dict[str, Any]:
        msg_record = {
            "type": "template",
            "template": template_name,
            "to": to_phone,
            "params": params,
            "lang": lang,
            "status": "delivered_mock",
            "cost_inr": 0.35  # Standard utility cost per rules.yaml
        }
        self.sent_messages.append(msg_record)
        logger.info("[Mock WhatsApp] Sent template '%s' (%s) to %s with params %s", template_name, lang, to_phone, params)
        return msg_record
