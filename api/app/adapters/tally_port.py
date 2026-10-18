from abc import ABC, abstractmethod
from typing import Any, Dict, List

class TallyPort(ABC):
    @abstractmethod
    def export_vouchers(self, tenant_id: str, vouchers: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Export vouchers as Tally-compliant XML or send to bridge."""
        pass

    @abstractmethod
    def import_masters(self, tenant_id: str, raw_content: str, file_type: str = "csv") -> Dict[str, Any]:
        """Import chart of accounts / masters (ledgers, stock items)."""
        pass
