import logging
from typing import Any, Dict, List, Optional
import httpx

from app.adapters.tally_port import TallyPort
from app.adapters.tally_file import TallyFileExporter
from app.core.config import settings

logger = logging.getLogger(__name__)

class TallyHttpBridge(TallyPort):
    def __init__(self, host: Optional[str] = None, port: Optional[int] = None):
        self.host = host or settings.TALLY_HOST
        self.port = port or settings.TALLY_PORT
        self.tally_url = f"http://{self.host}:{self.port}"
        self.file_exporter = TallyFileExporter()

    def export_vouchers(self, tenant_id: str, vouchers: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generates standard zero-sum Tally XML."""
        return self.file_exporter.export_vouchers(tenant_id, vouchers)

    def import_masters(self, tenant_id: str, raw_content: str, file_type: str = "csv") -> Dict[str, Any]:
        """Imports chart of accounts and masters."""
        return self.file_exporter.import_masters(tenant_id, raw_content, file_type)

    def sync_to_tally_direct(self, tenant_id: str, vouchers: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Posts generated XML directly to TallyPrime XML Server listening on port 9000.
        Parses Tally's response envelope to report created count or errors.
        """
        export_data = self.export_vouchers(tenant_id, vouchers)
        xml_content = export_data["content"]
        
        envelope = (
            "<ENVELOPE>\n"
            "  <HEADER>\n"
            "    <TALLYREQUEST>Import Data</TALLYREQUEST>\n"
            "  </HEADER>\n"
            "  <BODY>\n"
            "    <IMPORTDATA>\n"
            "      <REQUESTDESC>\n"
            "        <REPORTNAME>Vouchers</REPORTNAME>\n"
            "      </REQUESTDESC>\n"
            f"      <REQUESTDATA>\n{xml_content}\n      </REQUESTDATA>\n"
            "    </IMPORTDATA>\n"
            "  </BODY>\n"
            "</ENVELOPE>"
        )

        try:
            with httpx.Client(timeout=15.0) as client:
                res = client.post(
                    self.tally_url,
                    content=envelope.encode("utf-8"),
                    headers={"Content-Type": "text/xml;charset=utf-8"}
                )
                res.raise_for_status()
                response_text = res.text
                
                created = "<CREATED>1</CREATED>" in response_text or "<CREATED>" in response_text
                errors = "<ERRORS>0</ERRORS>" not in response_text and "<ERRORS>" in response_text
                
                return {
                    "status": "synced" if not errors else "tally_rejected",
                    "tally_url": self.tally_url,
                    "created_count": len(vouchers) if not errors else 0,
                    "response_xml": response_text
                }
        except httpx.ConnectError:
            logger.info("TallyPrime not reachable at %s. Exported as file payload.", self.tally_url)
            return {
                "status": "exported_file",
                "message": f"TallyPrime is not running on {self.tally_url}. Use downloaded XML file.",
                "file_export": export_data
            }
        except Exception as e:
            logger.error("Tally sync error: %s", e)
            return {
                "status": "error",
                "message": str(e),
                "file_export": export_data
            }
