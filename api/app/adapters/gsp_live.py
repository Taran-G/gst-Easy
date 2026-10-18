import logging
from typing import Any, Dict, List, Optional
import httpx

from app.adapters.gsp_port import GspPort
from app.adapters.gsp_mock import MockGspAdapter
from app.core.config import settings

logger = logging.getLogger(__name__)

class LiveGspAdapter(GspPort):
    def __init__(self):
        self.base_url = settings.GSP_BASE_URL.rstrip("/")
        self.client_id = settings.GSP_CLIENT_ID
        self.client_secret = settings.GSP_CLIENT_SECRET
        self.auth_token = settings.GSP_AUTH_TOKEN
        self.mock_fallback = MockGspAdapter()

    def _get_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.client_id:
            headers["client-id"] = self.client_id
        if self.client_secret:
            headers["client-secret"] = self.client_secret
        if self.auth_token:
            headers["auth-token"] = self.auth_token
            headers["Authorization"] = f"Bearer {self.auth_token}"
        return headers

    def get_gstr2b(self, gstin: str, period: str) -> List[Dict[str, Any]]:
        """Fetch GSTR-2B data from live GSP API with automatic mock fallback."""
        if not self.client_id or not self.auth_token or settings.MODE == "mock":
            return self.mock_fallback.get_gstr2b(gstin, period)

        try:
            url = f"{self.base_url}/returns/gstr2b"
            params = {"gstin": gstin, "period": period}
            with httpx.Client(timeout=20.0) as client:
                res = client.get(url, params=params, headers=self._get_headers())
                res.raise_for_status()
                data = res.json()
                # Parse GSP specific schema into standardized list of entries
                if isinstance(data, list):
                    return data
                return data.get("b2b", []) or data.get("invoices", []) or []
        except Exception as e:
            logger.warning("Live GSP get_gstr2b failed: %s. Using fixture fallback.", e)
            return self.mock_fallback.get_gstr2b(gstin, period)

    def get_filing_status(self, gstin: str) -> Dict[str, Any]:
        """Fetch supplier return filing history from GSP API with automatic mock fallback."""
        if not self.client_id or not self.auth_token or settings.MODE == "mock":
            return self.mock_fallback.get_filing_status(gstin)

        try:
            url = f"{self.base_url}/taxpayer/filing-status"
            params = {"gstin": gstin}
            with httpx.Client(timeout=15.0) as client:
                res = client.get(url, params=params, headers=self._get_headers())
                res.raise_for_status()
                return res.json()
        except Exception as e:
            logger.warning("Live GSP get_filing_status failed: %s. Using fixture fallback.", e)
            return self.mock_fallback.get_filing_status(gstin)

    def get_gstin_details(self, gstin: str) -> Dict[str, Any]:
        """Fetch taxpayer details and status from GSP API with automatic mock fallback."""
        if not self.client_id or not self.auth_token or settings.MODE == "mock":
            return self.mock_fallback.get_gstin_details(gstin)

        try:
            url = f"{self.base_url}/taxpayer/search"
            params = {"gstin": gstin}
            with httpx.Client(timeout=15.0) as client:
                res = client.get(url, params=params, headers=self._get_headers())
                res.raise_for_status()
                data = res.json()
                return {
                    "gstin": gstin,
                    "legal_name": data.get("lgnm", "Taxpayer"),
                    "trade_name": data.get("tradeNam", data.get("lgnm", "Taxpayer")),
                    "status": data.get("sts", "Active"),
                    "filing_freq": data.get("dty", "Monthly"),
                    "state_code": gstin[:2]
                }
        except Exception as e:
            logger.warning("Live GSP get_gstin_details failed: %s. Using fixture fallback.", e)
            return self.mock_fallback.get_gstin_details(gstin)
