from typing import Any, Dict, List
from app.adapters.tally_port import TallyPort

class TallyFileExporter(TallyPort):
    def export_vouchers(self, tenant_id: str, vouchers: List[Dict[str, Any]]) -> Dict[str, Any]:
        from app.services.tally_xml import generate_tally_xml_batch
        xml_content = generate_tally_xml_batch(tenant_id, vouchers)
        return {
            "format": "xml",
            "content": xml_content,
            "filename": f"tally_vouchers_{tenant_id}.xml",
            "count": len(vouchers)
        }

    def import_masters(self, tenant_id: str, raw_content: str, file_type: str = "csv") -> Dict[str, Any]:
        from app.services.tally_xml import parse_and_import_masters_csv
        return parse_and_import_masters_csv(tenant_id, raw_content)
