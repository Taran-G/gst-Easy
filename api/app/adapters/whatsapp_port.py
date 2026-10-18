from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

class WhatsAppPort(ABC):
    @abstractmethod
    def parse_webhook(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Parses an incoming WhatsApp webhook payload into normalized event data."""
        pass

    @abstractmethod
    def send_text(self, to_phone: str, text: str) -> Dict[str, Any]:
        """Sends a consolidated plain-text message."""
        pass

    @abstractmethod
    def send_template(self, to_phone: str, template_name: str, params: Dict[str, Any], lang: str = "en") -> Dict[str, Any]:
        """Sends a pre-approved utility-category template."""
        pass
