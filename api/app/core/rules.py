from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml
from app.core.config import settings

class RulesConfig:
    _instance: Optional["RulesConfig"] = None
    _data: Dict[str, Any] = {}

    def __init__(self, path: Optional[str] = None):
        rules_file = Path(path or settings.RULES_PATH)
        if not rules_file.exists():
            # Fallback search
            alt_path = Path("rules/rules.yaml")
            if alt_path.exists():
                rules_file = alt_path
            else:
                rules_file = Path(__file__).resolve().parent.parent.parent.parent / "rules" / "rules.yaml"

        with open(rules_file, "r", encoding="utf-8") as f:
            self._data = yaml.safe_load(f) or {}

    @classmethod
    def get_instance(cls) -> "RulesConfig":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def raw_data(self) -> Dict[str, Any]:
        return self._data

    @property
    def gst_rates(self) -> List[int]:
        return self._data.get("statutory", {}).get("gst_rates", [0, 5, 12, 18, 28])

    @property
    def fy_start_month(self) -> int:
        return self._data.get("statutory", {}).get("fy_start_month", 4)

    @property
    def confidence_threshold(self) -> float:
        return self._data.get("validation", {}).get("confidence_threshold", 0.85)

    @property
    def tolerance_rupees(self) -> float:
        return self._data.get("validation", {}).get("tolerance_rupees", 1.0)

    @property
    def rule_37_alert_days(self) -> List[int]:
        return self._data.get("rules", {}).get("rule_37", {}).get("alert_days", [120, 150, 170])

    @property
    def rule_37a_cutoff(self) -> Dict[str, int]:
        r = self._data.get("rules", {}).get("rule_37a", {})
        return {
            "month": r.get("reversal_cut_off_month", 11),
            "day": r.get("reversal_cut_off_day", 30)
        }

    @property
    def chase_limits(self) -> Dict[str, Any]:
        return self._data.get("chase", {})

    @property
    def state_codes(self) -> Dict[str, str]:
        return self._data.get("state_codes", {})

def get_rules() -> RulesConfig:
    return RulesConfig.get_instance()
