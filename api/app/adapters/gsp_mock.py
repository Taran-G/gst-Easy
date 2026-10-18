import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from app.adapters.gsp_port import GspPort
from app.core.config import settings

class MockGspAdapter(GspPort):
    def __init__(self, fixtures_dir: Optional[str] = None):
        self.fixtures_dir = Path(fixtures_dir or settings.FIXTURES_DIR)

    def get_gstr2b(self, gstin: str, period: str) -> List[Dict[str, Any]]:
        target_file = self.fixtures_dir / "gstr2b" / f"{period}.json"
        if target_file.exists():
            with open(target_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    def get_filing_status(self, gstin: str) -> Dict[str, Any]:
        target_file = self.fixtures_dir / "gstr3b_status" / f"{gstin}.json"
        if target_file.exists():
            with open(target_file, "r", encoding="utf-8") as f:
                return json.load(f)
        # Default fallback
        return {
            "gstin": gstin,
            "status": "Active",
            "filing_freq": "Monthly",
            "filings": []
        }

    def get_gstin_details(self, gstin: str) -> Dict[str, Any]:
        status_data = self.get_filing_status(gstin)
        return {
            "gstin": gstin,
            "legal_name": status_data.get("legal_name", "Mock Taxpayer"),
            "trade_name": status_data.get("trade_name", "Mock Taxpayer"),
            "status": status_data.get("status", "Active"),
            "filing_freq": status_data.get("filing_freq", "Monthly"),
            "state_code": gstin[:2]
        }
