import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from app.graph.client import tenant_graph, query

def resolve_vendor_and_items(
    tenant_id: str,
    gstin: str,
    inv_no_norm: str,
    fy: str,
    raw_item_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    Executes Q1 parameterised query to resolve:
    - Ledger mapping
    - Stock item mapping
    - Applicable procedural memory ApprovalRules
    - Duplicate detection
    """
    g = tenant_graph(tenant_id)
    raw_item = raw_item_name or ""
    
    q_res = query(
        g,
        "resolve_vendor_items.cypher",
        {
            "gstin": gstin,
            "inv_no": inv_no_norm,
            "fy": fy,
            "raw_item": raw_item
        }
    )
    
    rows = q_res["rows"]
    if rows and len(rows) > 0:
        is_dup, ledger, stock_item, uom, raw_rules = rows[0]
        # Parse rules
        parsed_rules = []
        if raw_rules:
            for r in raw_rules:
                if isinstance(r, str):
                    try:
                        parsed_rules.append(json.loads(r))
                    except Exception:
                        parsed_rules.append({"rule": r})
                elif isinstance(r, dict):
                    parsed_rules.append(r)
                    
        needs_vendor_master = (ledger is None)
        needs_item_master = (stock_item is None) if raw_item else False
        
        return {
            "is_duplicate": bool(is_dup),
            "ledger": ledger,
            "stock_item": stock_item,
            "uom": uom,
            "applied_rules": parsed_rules,
            "needs_master_request": needs_vendor_master or needs_item_master,
            "needs_vendor_master": needs_vendor_master,
            "needs_item_master": needs_item_master,
            "cypher": q_res["cypher"],
            "params": q_res["params"]
        }
        
    return {
        "is_duplicate": False,
        "ledger": None,
        "stock_item": None,
        "uom": None,
        "applied_rules": [],
        "needs_master_request": True,
        "needs_vendor_master": True,
        "needs_item_master": bool(raw_item),
        "cypher": q_res["cypher"],
        "params": q_res["params"]
    }

def create_or_update_vendor_mapping(
    tenant_id: str,
    vendor_gstin: str,
    tally_ledger_name: str,
    approved_by_user: str
) -> Dict[str, Any]:
    """
    Maps a Vendor GSTIN to a TallyLedger and stores procedural memory ApprovalRule.
    """
    g = tenant_graph(tenant_id)
    now_iso = datetime.now(timezone.utc).isoformat()
    rule_id = f"rule_map_{vendor_gstin}_{int(datetime.now().timestamp())}"
    
    rule_params = json.dumps({
        "kind": "VENDOR_MAP",
        "gstin": vendor_gstin,
        "ledger": tally_ledger_name,
        "approved_by": approved_by_user,
        "approved_at": now_iso
    })
    
    # Write mapping and ApprovalRule
    g.query(
        """
        MERGE (v:Vendor {gstin: $gstin})
        MERGE (tl:TallyLedger {name: $ledger_name})
        MERGE (v)-[m:MAPS_TO_LEDGER]->(tl)
        SET m.approved_by = $user,
            m.approved_at = $timestamp
            
        CREATE (r:ApprovalRule {
            id: $rule_id,
            kind: "VENDOR_MAP",
            params: $rule_params,
            created_by: $user,
            created_at: $timestamp,
            active: true
        })
        MERGE (r)-[:GOVERNS]->(v)
        """,
        {
            "gstin": vendor_gstin,
            "ledger_name": tally_ledger_name,
            "user": approved_by_user,
            "timestamp": now_iso,
            "rule_id": rule_id,
            "rule_params": rule_params
        }
    )
    
    return {
        "rule_id": rule_id,
        "gstin": vendor_gstin,
        "ledger": tally_ledger_name,
        "approved_by": approved_by_user,
        "approved_at": now_iso
    }
