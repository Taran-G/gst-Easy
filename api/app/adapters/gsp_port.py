from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

class GspPort(ABC):
    @abstractmethod
    def get_gstr2b(self, gstin: str, period: str) -> List[Dict[str, Any]]:
        """Fetch GSTR-2B entries for a period (e.g. '092026')."""
        pass

    @abstractmethod
    def get_filing_status(self, gstin: str) -> Dict[str, Any]:
        """Fetch GSTR-1 and GSTR-3B return filing history for a supplier GSTIN."""
        pass

    @abstractmethod
    def get_gstin_details(self, gstin: str) -> Dict[str, Any]:
        """Fetch registered taxpayer details (trade name, status, filing frequency)."""
        pass
