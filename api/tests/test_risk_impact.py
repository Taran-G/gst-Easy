from datetime import date
import pytest
from app.graph.client import tenant_graph
from app.services.impact import seed_supply_chain_layer, find_impact_path
from app.services.risk import (
    calculate_vendor_risk_ranking,
    calculate_hold_advice,
    check_rule_37_aging,
    refresh_vendor_status
)
from app.services.chase import check_chase_eligibility, approve_and_send_chase

def test_impact_trace_sharma_steels():
    tenant_id = "test_risk_tenant"
    try:
        tenant_graph(tenant_id).delete()
    except Exception:
        pass
    g = tenant_graph(tenant_id)
    
    # 1. Seed Sharma Steels with invoice
    g.query(
        """
        MERGE (v:Vendor {gstin: "06AABCS1234S1Z4"})
        SET v.legal_name = "Sharma Steels", v.state_code = "06"
        
        CREATE (i:Invoice {
            id: "inv_sharma_impact",
            number: "INV-SH-101",
            taxable: 50000.0,
            cgst: 4500.0,
            sgst: 4500.0,
            igst: 0.0,
            total: 59000.0
        })
        CREATE (v)-[:ISSUED]->(i)
        """
    )
    
    seed_supply_chain_layer(tenant_id)
    
    # 2. Trace impact for Sharma Steels + 4 day delay
    res = find_impact_path(tenant_id, "06AABCS1234S1Z4", delay_days=4)
    
    assert res["delay_days"] == 4
    assert res["supplier_name"] == "Sharma Steels"
    assert res["itc_exposed"] == 9000.0 # 4500 + 4500
    
    order_numbers = [o["order_number"] for o in res["orders_affected"]]
    assert "Maruti-504" in order_numbers
    assert "Maruti-511" in order_numbers
    assert "Vendor_06AABCS1234S1Z4" in res["graph_data"]["highlight_node_ids"]
    assert "CustomerOrder_Maruti-504" in res["graph_data"]["highlight_node_ids"]

def test_pagerank_vendor_risk_ranking():
    tenant_id = "test_risk_tenant"
    
    refresh_vendor_status(tenant_id, "06AABCS1234S1Z4") # Sharma (Filed, Active)
    refresh_vendor_status(tenant_id, "06AABCD9012D1Z6") # Delta (Not filed, Suspended)
    
    ranking = calculate_vendor_risk_ranking(tenant_id, top_n=5)
    assert len(ranking) >= 2
    
    # Delta Fasteners must be ranked above Sharma Steels in risk!
    delta_idx = next(i for i, v in enumerate(ranking) if v["gstin"] == "06AABCD9012D1Z6")
    sharma_idx = next(i for i, v in enumerate(ranking) if v["gstin"] == "06AABCS1234S1Z4")
    
    assert delta_idx < sharma_idx, f"Delta ({delta_idx}) should be ranked riskier than Sharma ({sharma_idx})"
    assert ranking[delta_idx]["risk_level"] == "High"

def test_rule_37_aging_alert():
    tenant_id = "test_r37_tenant"
    try:
        tenant_graph(tenant_id).delete()
    except Exception:
        pass
    g = tenant_graph(tenant_id)
    
    # Invoice dated 150 days before 2026-10-18 (approx 2026-05-21)
    g.query(
        """
        MERGE (v:Vendor {gstin: "06AABCS1234S1Z4"})
        SET v.legal_name = "Sharma Steels"
        CREATE (i:Invoice {
            id: "inv_old_150",
            number: "INV-OLD-150",
            date: "2026-05-20",
            total: 23600.0,
            cgst: 1800.0,
            sgst: 1800.0,
            igst: 0.0,
            state: "POSTED",
            hold_status: "NONE"
        })
        CREATE (v)-[:ISSUED]->(i)
        """
    )
    
    alerts = check_rule_37_aging(tenant_id, today_date=date(2026, 10, 18))
    assert len(alerts) >= 1
    target = next(a for a in alerts if a["invoice_id"] == "inv_old_150")
    assert target["age_days"] >= 150
    assert target["severity"] in ["WARNING", "DANGER"]

def test_chase_rate_limit_and_optout():
    tenant_id = "test_chase_tenant"
    try:
        tenant_graph(tenant_id).delete()
    except Exception:
        pass
    g = tenant_graph(tenant_id)
    
    g.query(
        """
        MERGE (v:Vendor {gstin: "06AABCK9999K1ZO"})
        SET v.legal_name = "Opted Out Vendor",
            v.opted_out = true
        """
    )
    
    eligibility = check_chase_eligibility(tenant_id, "06AABCK9999K1ZO")
    assert eligibility["allowed"] is False
    assert "opted out" in eligibility["reason"].lower()
