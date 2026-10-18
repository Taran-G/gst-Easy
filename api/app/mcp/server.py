import json
from typing import Any, Dict, List, Optional
from app.graph.client import tenant_graph, query
from app.services.resolve import resolve_vendor_and_items, create_or_update_vendor_mapping
from app.services.impact import find_impact_path
from app.services.risk import calculate_vendor_risk_ranking, calculate_hold_advice
from app.services.reconcile import run_reconciliation
from app.services.chase import draft_vendor_chase

WHITELISTED_TEMPLATES = {
    "resolve_vendor_items": "resolve_vendor_items.cypher",
    "check_duplicate": "check_duplicate.cypher",
    "impact_trace": "impact_trace.cypher",
    "vendor_pagerank": "vendor_pagerank.cypher",
    "reconcile_period": "reconcile_period.cypher",
    "hold_advice": "hold_advice.cypher",
    "rule37_aging": "rule37_aging.cypher",
    "rule37a_candidates": "rule37a_candidates.cypher",
}

MCP_TOOL_DEFINITIONS = [
    {
        "name": "resolve_vendor",
        "description": "Resolves supplier GSTIN to TallyLedger and stock item mappings using FalkorDB graph.",
        "parameters": {
            "type": "object",
            "properties": {
                "tenant_id": {"type": "string"},
                "gstin": {"type": "string"},
                "invoice_number": {"type": "string"},
                "fy": {"type": "string", "default": "2026-27"}
            },
            "required": ["tenant_id", "gstin"]
        }
    },
    {
        "name": "find_impact_path",
        "description": "Multi-hop graph traversal returning downstream customer deliveries and ITC exposed by supplier delay.",
        "parameters": {
            "type": "object",
            "properties": {
                "tenant_id": {"type": "string"},
                "vendor_gstin": {"type": "string"},
                "delay_days": {"type": "integer", "default": 4}
            },
            "required": ["tenant_id", "vendor_gstin"]
        }
    },
    {
        "name": "score_vendor_risk",
        "description": "Computes FalkorDB PageRank algorithm blended with ITC risk and return filing status.",
        "parameters": {
            "type": "object",
            "properties": {
                "tenant_id": {"type": "string"},
                "top_n": {"type": "integer", "default": 10}
            },
            "required": ["tenant_id"]
        }
    },
    {
        "name": "reconcile_period",
        "description": "Reconciles purchase ledger invoices against GSTR-2B government statement.",
        "parameters": {
            "type": "object",
            "properties": {
                "tenant_id": {"type": "string"},
                "period": {"type": "string", "default": "092026"}
            },
            "required": ["tenant_id"]
        }
    },
    {
        "name": "run_cypher_readonly",
        "description": "Executes whitelisted parameterised Cypher templates safely. No free-form Cypher writes.",
        "parameters": {
            "type": "object",
            "properties": {
                "tenant_id": {"type": "string"},
                "template_id": {"type": "string", "enum": list(WHITELISTED_TEMPLATES.keys())},
                "params": {"type": "object"}
            },
            "required": ["tenant_id", "template_id"]
        }
    },
    {
        "name": "commit_decision_to_memory",
        "description": "Stores procedural memory ApprovalRule on supplier in FalkorDB graph.",
        "parameters": {
            "type": "object",
            "properties": {
                "tenant_id": {"type": "string"},
                "vendor_gstin": {"type": "string"},
                "ledger_name": {"type": "string"},
                "approved_by": {"type": "string"}
            },
            "required": ["tenant_id", "vendor_gstin", "ledger_name"]
        }
    },
    {
        "name": "draft_chase",
        "description": "Drafts an automated transactional WhatsApp utility message with cost calculation.",
        "parameters": {
            "type": "object",
            "properties": {
                "tenant_id": {"type": "string"},
                "invoice_id": {"type": "string"},
                "type": {"type": "string", "default": "missing_2b"},
                "language": {"type": "string", "default": "en"}
            },
            "required": ["tenant_id", "invoice_id"]
        }
    }
]

def handle_mcp_tool_call(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
    Dispatcher for MCP tool calls.
    Returns: { "result": Any, "cypher": str, "path_ids": List[str] }
    """
    tenant_id = arguments.get("tenant_id", "apex")
    
    if tool_name == "resolve_vendor":
        res = resolve_vendor_and_items(
            tenant_id=tenant_id,
            gstin=arguments["gstin"],
            inv_no_norm=arguments.get("invoice_number", ""),
            fy=arguments.get("fy", "2026-27")
        )
        return {
            "result": res,
            "cypher": res.get("cypher", ""),
            "path_ids": [f"Vendor_{arguments['gstin']}"]
        }
        
    elif tool_name == "find_impact_path":
        res = find_impact_path(
            tenant_id=tenant_id,
            gstin=arguments["vendor_gstin"],
            delay_days=arguments.get("delay_days", 4)
        )
        return {
            "result": res,
            "cypher": res["cypher"],
            "path_ids": res["graph_data"]["highlight_node_ids"]
        }
        
    elif tool_name == "score_vendor_risk":
        ranking = calculate_vendor_risk_ranking(tenant_id, top_n=arguments.get("top_n", 10))
        return {
            "result": ranking,
            "cypher": "CALL algo.pageRank('Vendor', 'SUPPLIES') YIELD node, score RETURN node.gstin, score",
            "path_ids": [f"Vendor_{r['gstin']}" for r in ranking]
        }
        
    elif tool_name == "reconcile_period":
        res = run_reconciliation(tenant_id, period=arguments.get("period", "092026"))
        return {
            "result": res["counts"],
            "cypher": "MATCH (v:Vendor)-[:ISSUED]->(i:Invoice) OPTIONAL MATCH (i)-[:REFLECTED_IN]->(e:GSTR2BEntry) RETURN count(i)",
            "path_ids": []
        }
        
    elif tool_name == "run_cypher_readonly":
        tmpl_id = arguments["template_id"]
        if tmpl_id not in WHITELISTED_TEMPLATES:
            raise ValueError(f"Template '{tmpl_id}' not allowed. Whitelisted: {list(WHITELISTED_TEMPLATES.keys())}")
        g = tenant_graph(tenant_id)
        q_res = query(g, WHITELISTED_TEMPLATES[tmpl_id], arguments.get("params", {}))
        return {
            "result": q_res["rows"],
            "cypher": q_res["cypher"],
            "path_ids": []
        }
        
    elif tool_name == "commit_decision_to_memory":
        res = create_or_update_vendor_mapping(
            tenant_id=tenant_id,
            vendor_gstin=arguments["vendor_gstin"],
            tally_ledger_name=arguments["ledger_name"],
            approved_by_user=arguments.get("approved_by", "Agent")
        )
        return {
            "result": res,
            "cypher": "MERGE (v:Vendor)-[:MAPS_TO_LEDGER]->(tl:TallyLedger) CREATE (r:ApprovalRule)-[:GOVERNS]->(v)",
            "path_ids": [f"Vendor_{arguments['vendor_gstin']}"]
        }
        
    elif tool_name == "draft_chase":
        draft = draft_vendor_chase(
            tenant_id=tenant_id,
            invoice_id=arguments["invoice_id"],
            chase_type=arguments.get("type", "missing_2b"),
            lang=arguments.get("language", "en")
        )
        return {
            "result": draft,
            "cypher": "MATCH (v:Vendor)-[:ISSUED]->(i:Invoice) RETURN v.phone, i.total",
            "path_ids": [f"Invoice_{arguments['invoice_id']}"]
        }
        
    raise ValueError(f"Unknown MCP tool: {tool_name}")
