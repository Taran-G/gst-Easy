import json
import logging
from pathlib import Path
from typing import Optional
from app.adapters.extractor_port import ExtractorPort, ExtractionResult, ExtractionLineItem
from app.core.config import settings

logger = logging.getLogger(__name__)

class GeminiExtractorAdapter(ExtractorPort):
    def __init__(self, mode: Optional[str] = None):
        self.mode = mode or settings.MODE

    def extract(self, file_path: str) -> ExtractionResult:
        p = Path(file_path)
        stem = p.stem.lower()

        # Check for matching fixture golden JSON first (fixture-replay mode)
        golden_file = Path(settings.FIXTURES_DIR) / "bills" / "golden" / f"{stem}.json"
        if not golden_file.exists():
            # Try alternate naming
            for gf in (Path(settings.FIXTURES_DIR) / "bills" / "golden").glob("*.json"):
                if gf.stem.lower() in stem or stem in gf.stem.lower():
                    golden_file = gf
                    break

        if (self.mode == "mock" or not settings.GEMINI_API_KEY) and golden_file.exists():
            logger.info("Using fixture-replay extraction from: %s", golden_file)
            with open(golden_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return ExtractionResult(**data)

        if not settings.GEMINI_API_KEY:
            if golden_file.exists():
                with open(golden_file, "r", encoding="utf-8") as f:
                    return ExtractionResult(**json.load(f))
            raise ValueError("GEMINI_API_KEY is not set and no fixture match found for file.")

        # Live Gemini structured extraction
        try:
            from google import genai
            from google.genai import types
            
            client = genai.Client(api_key=settings.GEMINI_API_KEY)
            
            # Read file bytes
            with open(p, "rb") as f:
                file_bytes = f.read()

            prompt = (
                "Extract all GST tax invoice fields into strict structured JSON. "
                "Output strictly valid JSON matching the schema: "
                "supplier_name, supplier_gstin, buyer_name, buyer_gstin, invoice_number, "
                "invoice_date (YYYY-MM-DD), place_of_supply (2-digit state code), "
                "taxable_amount, cgst_amount, sgst_amount, igst_amount, round_off, total_amount, "
                "lines: [{description, hsn_sac, qty, uom, rate, taxable_value, gst_rate, cgst_amount, sgst_amount, igst_amount}], "
                "confidences: {field_name: confidence_0_to_1}. Temperature: 0."
            )

            # Determine mime type
            mime = "application/pdf" if p.suffix.lower() == ".pdf" else "image/png"
            if p.suffix.lower() in [".jpg", ".jpeg"]:
                mime = "image/jpeg"

            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    types.Part.from_bytes(data=file_bytes, mime_type=mime),
                    prompt
                ],
                config=types.GenerateContentConfig(
                    temperature=0.0,
                    response_mime_type="application/json",
                    response_schema=ExtractionResult
                )
            )

            result_json = json.loads(response.text)
            return ExtractionResult(**result_json)
        except Exception as e:
            logger.warning("Gemini extraction failed: %s. Falling back to golden if exists.", e)
            if golden_file.exists():
                with open(golden_file, "r", encoding="utf-8") as f:
                    return ExtractionResult(**json.load(f))
            raise
