from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel

class ExtractionLineItem(BaseModel):
    description: str
    hsn_sac: Optional[str] = None
    qty: Optional[float] = None
    uom: Optional[str] = None
    rate: Optional[float] = None
    taxable_value: float
    gst_rate: float
    cgst_amount: Optional[float] = 0.0
    sgst_amount: Optional[float] = 0.0
    igst_amount: Optional[float] = 0.0

class ExtractionResult(BaseModel):
    supplier_name: str
    supplier_gstin: str
    buyer_name: str
    buyer_gstin: str
    invoice_number: str
    invoice_date: str
    place_of_supply: str
    lines: List[ExtractionLineItem]
    taxable_amount: float
    cgst_amount: float = 0.0
    sgst_amount: float = 0.0
    igst_amount: float = 0.0
    round_off: float = 0.0
    total_amount: float
    confidences: Dict[str, float] = {}
    irn: Optional[str] = None
    supplier_phone: Optional[str] = None
    supplier_email: Optional[str] = None
    raw: Optional[Dict[str, Any]] = None

class ExtractorPort(ABC):
    @abstractmethod
    def extract(self, file_path: str) -> ExtractionResult:
        """Extract invoice data from document image/PDF."""
        pass
